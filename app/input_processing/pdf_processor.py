"""PDF-specific input processing boundary."""

from enum import StrEnum
from io import BytesIO
from typing import Protocol

from pypdf import PdfReader
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.contracts.normalized_input import PDFContent
from app.input_processing.errors import InputProcessingError, InputProcessingErrorCode
from app.input_processing.ocr_provider import OCRProvider, OCRResult, OCRStatus
from app.input_processing.preview import build_pdf_preview
from app.input_processing.schemas import (
    AttachmentProcessingError,
    InputModality,
    ValidatedAttachment,
)


# Input Processor PDF limit. Keep this as the single configurable value used
# before any extraction or OCR work.
MAX_PDF_PAGE_COUNT = 5


class PDFDocumentType(StrEnum):
    """Internal PDF content classifications."""

    TEXT_BASED = "text_based"
    SCANNED = "scanned"
    MIXED = "mixed"


class PDFExtractionStatus(StrEnum):
    """Provider-independent PDF inspection/extraction outcomes."""

    SUCCESS = "success"
    EXTRACTION_FAILURE = "extraction_failure"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    MALFORMED_RESPONSE = "malformed_response"
    CORRUPT_PDF = "corrupt_pdf"


class PDFPageText(BaseModel):
    """Provider-independent text extracted for one PDF page."""

    model_config = ConfigDict(extra="forbid", strict=True)

    page_number: int
    text: str = ""

    @field_validator("page_number")
    @classmethod
    def validate_page_number(cls, value: int) -> int:
        if value < 1:
            raise ValueError("page_number must be 1 or greater")
        return value


class PDFPageImage(BaseModel):
    """Provider-independent rendered image bytes for one PDF page."""

    model_config = ConfigDict(extra="forbid", strict=True)

    page_number: int
    image_content: bytes

    @field_validator("page_number")
    @classmethod
    def validate_page_number(cls, value: int) -> int:
        if value < 1:
            raise ValueError("page_number must be 1 or greater")
        return value

    @field_validator("image_content")
    @classmethod
    def validate_image_content(cls, value: bytes) -> bytes:
        if not value:
            raise ValueError("image_content must not be empty")
        return value


class PDFExtractionResult(BaseModel):
    """Provider-independent PDF extraction result."""

    model_config = ConfigDict(extra="forbid", strict=True)

    status: PDFExtractionStatus
    document_type: PDFDocumentType | None = None
    pages: list[PDFPageText] = Field(default_factory=list)
    message: str | None = None

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("message must not be empty")
        return value

    @model_validator(mode="after")
    def validate_status_shape(self) -> "PDFExtractionResult":
        if self.status == PDFExtractionStatus.SUCCESS:
            if self.document_type is None:
                raise ValueError("successful PDF extraction requires document_type")
            if not self.pages:
                raise ValueError("successful PDF extraction requires page results")
            return self

        if self.document_type is not None or self.pages:
            raise ValueError("failed PDF extraction cannot include extracted content")
        if self.message is None:
            raise ValueError("failed PDF extraction requires a safe message")
        return self


class PDFClassificationResult(BaseModel):
    """Internal PDF classification from machine-readable page inspection."""

    model_config = ConfigDict(extra="forbid", strict=True)

    document_type: PDFDocumentType
    pages: list[PDFPageText]

    @model_validator(mode="after")
    def validate_pages_present(self) -> "PDFClassificationResult":
        if not self.pages:
            raise ValueError("PDF classification requires page results")
        return self


class PDFProcessingResult(BaseModel):
    """PDF processor outcome with normalized content or a safe failure."""

    model_config = ConfigDict(extra="forbid", strict=True)

    pdf_content: PDFContent | None = None
    extraction_result: PDFExtractionResult | None = None
    error: AttachmentProcessingError | None = None

    @model_validator(mode="after")
    def validate_result_shape(self) -> "PDFProcessingResult":
        populated_fields = [
            self.pdf_content is not None,
            self.extraction_result is not None,
            self.error is not None,
        ]
        if sum(populated_fields) != 1:
            raise ValueError(
                "PDF processing result requires exactly one outcome field"
            )
        return self


def classify_pdf_page_texts(page_texts: list[PDFPageText]) -> PDFDocumentType:
    """Classify a PDF from page-level machine-readable text presence."""

    if not page_texts:
        raise InputProcessingError(
            InputProcessingErrorCode.UNREADABLE_CONTENT,
            "This PDF could not be inspected for classification.",
        )

    has_text_by_page = [bool(page.text.strip()) for page in page_texts]
    if all(has_text_by_page):
        return PDFDocumentType.TEXT_BASED
    if not any(has_text_by_page):
        return PDFDocumentType.SCANNED
    return PDFDocumentType.MIXED


class PDFExtractor(Protocol):
    """Narrow replaceable PDF inspection/extraction capability."""

    def extract(self, pdf_content: bytes) -> PDFExtractionResult:
        """Inspect and extract supported PDF content from transient bytes."""


class PDFPageImageExtractor(Protocol):
    """Replaceable capability for rendering or extracting scanned PDF page images."""

    def extract_page_images(self, pdf_content: bytes) -> list[PDFPageImage]:
        """Return rendered page images in document order."""


class PendingPDFExtractor:
    """Placeholder PDF extractor until the concrete provider is finalized."""

    def extract(self, pdf_content: bytes) -> PDFExtractionResult:
        """Return a controlled unavailable outcome without exposing provider details."""

        return PDFExtractionResult(
            status=PDFExtractionStatus.UNAVAILABLE,
            message="PDF extraction provider is not configured.",
        )

    def extract_page_images(self, pdf_content: bytes) -> list[PDFPageImage]:
        """Return a controlled unavailable outcome for scanned PDF rendering."""

        raise InputProcessingError(
            InputProcessingErrorCode.EXTRACTION_FAILURE,
            "PDF page images could not be extracted.",
        )


def get_pdf_page_count(pdf_content: bytes) -> int:
    """Return the page count for a PDF from transient bytes."""

    try:
        with BytesIO(pdf_content) as stream:
            reader = PdfReader(stream)
            return len(reader.pages)
    except Exception as exc:
        raise InputProcessingError(
            InputProcessingErrorCode.UNREADABLE_CONTENT,
            "This PDF could not be read for validation.",
        ) from exc


def classify_pdf_content(pdf_content: bytes) -> PDFClassificationResult:
    """Classify a PDF as text-based, scanned, or mixed using page text presence."""

    try:
        with BytesIO(pdf_content) as stream:
            reader = PdfReader(stream)
            pages = [
                PDFPageText(
                    page_number=page_number,
                    text=(page.extract_text() or "").strip(),
                )
                for page_number, page in enumerate(reader.pages, start=1)
            ]
    except Exception as exc:
        raise InputProcessingError(
            InputProcessingErrorCode.UNREADABLE_CONTENT,
            "This PDF could not be inspected for classification.",
        ) from exc

    return PDFClassificationResult(
        document_type=classify_pdf_page_texts(pages),
        pages=pages,
    )


def build_text_based_pdf_content(
    *,
    pdf_name: str,
    pages: list[PDFPageText],
) -> PDFContent:
    """Build normalized PDF content from machine-readable PDF text."""

    return _build_pdf_content_from_page_texts(pdf_name=pdf_name, pages=pages)


def build_scanned_pdf_content(
    *,
    pdf_name: str,
    page_images: list[PDFPageImage],
    ocr_provider: OCRProvider,
) -> PDFContent:
    """Build normalized PDF content from page-level OCR over scanned pages."""

    if not page_images:
        raise InputProcessingError(
            InputProcessingErrorCode.UNREADABLE_CONTENT,
            "No PDF pages were available for OCR.",
        )

    page_texts: list[PDFPageText] = []
    for page_image in sorted(page_images, key=lambda page: page.page_number):
        try:
            ocr_result = ocr_provider.extract_text(page_image.image_content)
        except Exception as exc:
            raise InputProcessingError(
                InputProcessingErrorCode.OCR_FAILURE,
                "OCR could not be completed for this PDF.",
            ) from exc

        if not isinstance(ocr_result, OCRResult):
            raise InputProcessingError(
                InputProcessingErrorCode.OCR_FAILURE,
                "OCR provider returned an invalid result.",
            )

        if ocr_result.status == OCRStatus.SUCCESS:
            page_texts.append(
                PDFPageText(page_number=page_image.page_number, text=ocr_result.text)
            )
            continue

        if ocr_result.status in {OCRStatus.EMPTY, OCRStatus.LOW_CONFIDENCE}:
            page_texts.append(PDFPageText(page_number=page_image.page_number, text=""))
            continue

        raise InputProcessingError(
            InputProcessingErrorCode.OCR_FAILURE,
            ocr_result.message or "OCR could not be completed for this PDF.",
        )

    return _build_pdf_content_from_page_texts(pdf_name=pdf_name, pages=page_texts)


def build_mixed_pdf_content(
    *,
    pdf_name: str,
    classified_pages: list[PDFPageText],
    page_images: list[PDFPageImage],
    ocr_provider: OCRProvider,
) -> PDFContent:
    """Build normalized PDF content from mixed machine text and scanned pages."""

    page_images_by_number = {page.page_number: page for page in page_images}
    page_texts: list[PDFPageText] = []

    for page in sorted(classified_pages, key=lambda item: item.page_number):
        if page.text.strip():
            page_texts.append(page)
            continue

        page_image = page_images_by_number.get(page.page_number)
        if page_image is None:
            page_texts.append(PDFPageText(page_number=page.page_number, text=""))
            continue

        try:
            ocr_result = ocr_provider.extract_text(page_image.image_content)
        except Exception as exc:
            raise InputProcessingError(
                InputProcessingErrorCode.OCR_FAILURE,
                "OCR could not be completed for this PDF.",
            ) from exc

        if not isinstance(ocr_result, OCRResult):
            raise InputProcessingError(
                InputProcessingErrorCode.OCR_FAILURE,
                "OCR provider returned an invalid result.",
            )

        if ocr_result.status == OCRStatus.SUCCESS:
            page_texts.append(
                PDFPageText(page_number=page.page_number, text=ocr_result.text)
            )
            continue

        if ocr_result.status in {OCRStatus.EMPTY, OCRStatus.LOW_CONFIDENCE}:
            page_texts.append(PDFPageText(page_number=page.page_number, text=""))
            continue

        raise InputProcessingError(
            InputProcessingErrorCode.OCR_FAILURE,
            ocr_result.message or "OCR could not be completed for this PDF.",
        )

    return _build_pdf_content_from_page_texts(pdf_name=pdf_name, pages=page_texts)


def extract_pdf_page_images(
    *,
    pdf_content: bytes,
    page_image_extractor: PDFPageImageExtractor,
) -> list[PDFPageImage]:
    """Extract scanned page images through a controlled provider boundary."""

    try:
        page_images = page_image_extractor.extract_page_images(pdf_content)
    except InputProcessingError:
        raise
    except Exception as exc:
        raise InputProcessingError(
            InputProcessingErrorCode.EXTRACTION_FAILURE,
            "PDF page images could not be extracted.",
        ) from exc

    if not isinstance(page_images, list) or not all(
        isinstance(page_image, PDFPageImage) for page_image in page_images
    ):
        raise InputProcessingError(
            InputProcessingErrorCode.EXTRACTION_FAILURE,
            "PDF page image extractor returned an invalid result.",
        )

    return page_images


def _build_pdf_content_from_page_texts(
    *,
    pdf_name: str,
    pages: list[PDFPageText],
) -> PDFContent:
    """Build normalized PDF content from page-level text."""

    from guardrails.input_processor import (
        mark_document_text_untrusted,
        mask_pii_in_text,
    )

    extracted_text = "\n".join(page.text for page in pages).strip()
    if not extracted_text:
        raise InputProcessingError(
            InputProcessingErrorCode.UNREADABLE_CONTENT,
            "No readable text could be extracted from this PDF.",
        )

    masked_text = mask_pii_in_text(extracted_text).text
    safe_document_text = mark_document_text_untrusted(masked_text).text
    safe_page_texts = [
        mark_document_text_untrusted(mask_pii_in_text(page.text).text).text
        for page in pages
    ]

    return PDFContent(
        pdf_name=pdf_name,
        extracted_text=safe_document_text,
        preview=build_pdf_preview(safe_page_texts),
    )


def validate_pdf_page_count(
    pdf_content: bytes,
    *,
    max_page_count: int = MAX_PDF_PAGE_COUNT,
) -> None:
    """Reject PDFs that exceed the configured page limit before extraction/OCR."""

    if max_page_count <= 0:
        raise ValueError("max_page_count must be positive")

    page_count = get_pdf_page_count(pdf_content)
    if page_count <= max_page_count:
        return

    raise InputProcessingError(
        InputProcessingErrorCode.PDF_PAGE_LIMIT_EXCEEDED,
        f"This PDF has too many pages. Upload a PDF with {max_page_count} pages or fewer.",
    )


def process_pdf_attachment(
    validated_attachment: ValidatedAttachment,
    pdf_extractor: PDFExtractor,
    *,
    ocr_provider: OCRProvider | None = None,
    page_image_extractor: PDFPageImageExtractor | None = None,
    max_page_count: int = MAX_PDF_PAGE_COUNT,
) -> PDFProcessingResult:
    """Process an already-validated PDF through bounded PDF extraction."""

    attachment = validated_attachment.attachment
    if validated_attachment.modality != InputModality.PDF:
        return PDFProcessingResult(
            error=AttachmentProcessingError(
                filename=attachment.filename,
                code=InputProcessingErrorCode.UNSUPPORTED_FORMAT,
                message="This attachment is not a supported PDF.",
            )
        )

    try:
        validate_pdf_page_count(
            attachment.content,
            max_page_count=max_page_count,
        )
        classification = classify_pdf_content(attachment.content)
    except InputProcessingError as exc:
        return PDFProcessingResult(
            error=AttachmentProcessingError(
                filename=attachment.filename,
                code=exc.code,
                message=exc.message,
            )
        )

    if classification.document_type == PDFDocumentType.TEXT_BASED:
        try:
            return PDFProcessingResult(
                pdf_content=build_text_based_pdf_content(
                    pdf_name=attachment.filename,
                    pages=classification.pages,
                )
            )
        except InputProcessingError as exc:
            return PDFProcessingResult(
                error=AttachmentProcessingError(
                    filename=attachment.filename,
                    code=exc.code,
                    message=exc.message,
                )
            )
        except Exception:
            return PDFProcessingResult(
                error=AttachmentProcessingError(
                    filename=attachment.filename,
                    code=InputProcessingErrorCode.INTERNAL_PROCESSING_ERROR,
                    message="PDF content could not be processed safely.",
                )
            )

    if classification.document_type == PDFDocumentType.SCANNED:
        if ocr_provider is None or page_image_extractor is None:
            return PDFProcessingResult(
                error=AttachmentProcessingError(
                    filename=attachment.filename,
                    code=InputProcessingErrorCode.OCR_FAILURE,
                    message="Scanned PDF OCR is not configured.",
                )
            )

        try:
            page_images = extract_pdf_page_images(
                pdf_content=attachment.content,
                page_image_extractor=page_image_extractor,
            )
            return PDFProcessingResult(
                pdf_content=build_scanned_pdf_content(
                    pdf_name=attachment.filename,
                    page_images=page_images,
                    ocr_provider=ocr_provider,
                )
            )
        except InputProcessingError as exc:
            return PDFProcessingResult(
                error=AttachmentProcessingError(
                    filename=attachment.filename,
                    code=exc.code,
                    message=exc.message,
                )
            )
        except Exception:
            return PDFProcessingResult(
                error=AttachmentProcessingError(
                    filename=attachment.filename,
                    code=InputProcessingErrorCode.INTERNAL_PROCESSING_ERROR,
                    message="PDF content could not be processed safely.",
                )
            )

    if classification.document_type == PDFDocumentType.MIXED:
        if ocr_provider is None or page_image_extractor is None:
            return PDFProcessingResult(
                error=AttachmentProcessingError(
                    filename=attachment.filename,
                    code=InputProcessingErrorCode.OCR_FAILURE,
                    message="Mixed PDF OCR is not configured.",
                )
            )

        try:
            page_images = extract_pdf_page_images(
                pdf_content=attachment.content,
                page_image_extractor=page_image_extractor,
            )
            return PDFProcessingResult(
                pdf_content=build_mixed_pdf_content(
                    pdf_name=attachment.filename,
                    classified_pages=classification.pages,
                    page_images=page_images,
                    ocr_provider=ocr_provider,
                )
            )
        except InputProcessingError as exc:
            return PDFProcessingResult(
                error=AttachmentProcessingError(
                    filename=attachment.filename,
                    code=exc.code,
                    message=exc.message,
                )
            )
        except Exception:
            return PDFProcessingResult(
                error=AttachmentProcessingError(
                    filename=attachment.filename,
                    code=InputProcessingErrorCode.INTERNAL_PROCESSING_ERROR,
                    message="PDF content could not be processed safely.",
                )
            )

    return PDFProcessingResult(
        error=AttachmentProcessingError(
            filename=attachment.filename,
            code=InputProcessingErrorCode.UNREADABLE_CONTENT,
            message="This PDF could not be classified for processing.",
        )
    )


__all__ = [
    "MAX_PDF_PAGE_COUNT",
    "PDFClassificationResult",
    "PDFDocumentType",
    "PDFExtractionResult",
    "PDFExtractionStatus",
    "PDFExtractor",
    "PDFPageImage",
    "PDFPageImageExtractor",
    "PDFPageText",
    "PDFProcessingResult",
    "PendingPDFExtractor",
    "build_mixed_pdf_content",
    "build_scanned_pdf_content",
    "build_text_based_pdf_content",
    "classify_pdf_content",
    "classify_pdf_page_texts",
    "extract_pdf_page_images",
    "get_pdf_page_count",
    "process_pdf_attachment",
    "validate_pdf_page_count",
]
