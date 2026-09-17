"""Input Processor orchestration boundary."""

from app.contracts.normalized_input import (
    ImageContent,
    NormalizedInput,
    PDFContent,
    SpreadsheetContent,
)
from app.graph.state import GraphState
from app.input_processing.errors import InputProcessingError, InputProcessingErrorCode
from app.input_processing.excel_processor import (
    OpenPyXLSpreadsheetParser,
    SpreadsheetParser,
    build_spreadsheet_text_projection,
    process_spreadsheet_attachment,
)
from app.input_processing.image_processor import process_image_attachment
from app.input_processing.ocr_provider import OCRProvider, TesseractOCRProvider
from app.input_processing.pdf_processor import (
    PDFExtractor,
    PDFPageImageExtractor,
    PendingPDFExtractor,
    process_pdf_attachment,
)
from app.input_processing.schemas import (
    Attachment,
    AttachmentProcessingError,
    AttachmentProcessingStatus,
    AttachmentProcessingWarning,
    InputModality,
    InputProcessingResult,
    InputRequest,
)
from guardrails.input_processor import (
    mark_document_text_untrusted,
    mask_pii_in_text,
    validate_attachment_modality,
    validate_input_presence,
    validate_post_extraction_boundary,
    validate_pre_processing_boundary,
)


def process_input(
    request: InputRequest,
    *,
    ocr_provider: OCRProvider | None = None,
    pdf_extractor: PDFExtractor | None = None,
    page_image_extractor: PDFPageImageExtractor | None = None,
    spreadsheet_parser: SpreadsheetParser | None = None,
) -> InputProcessingResult:
    """Process a public Input Processor request into normalized content."""

    try:
        validate_pre_processing_boundary(request)
    except InputProcessingError as exc:
        return InputProcessingResult(
            success=False,
            attachment_statuses=[
                AttachmentProcessingStatus(
                    filename="request",
                    status="failed",
                    error=AttachmentProcessingError(
                        filename="request",
                        code=exc.code,
                        message=exc.message,
                    ),
                )
            ],
        )

    active_ocr_provider = ocr_provider or TesseractOCRProvider()
    active_pdf_extractor = pdf_extractor or PendingPDFExtractor()
    active_spreadsheet_parser = spreadsheet_parser or OpenPyXLSpreadsheetParser()

    image_content: list[ImageContent] = []
    pdf_content: list[PDFContent] = []
    spreadsheet_content: list[SpreadsheetContent] = []
    attachment_statuses: list[AttachmentProcessingStatus] = []

    for attachment in request.attachments:
        (
            status,
            processed_image_content,
            processed_pdf_content,
            processed_spreadsheet_content,
        ) = _process_attachment(
            attachment,
            active_ocr_provider=active_ocr_provider,
            active_pdf_extractor=active_pdf_extractor,
            page_image_extractor=page_image_extractor,
            active_spreadsheet_parser=active_spreadsheet_parser,
        )
        attachment_statuses.append(status)
        if processed_image_content is not None:
            image_content.append(processed_image_content)
        if processed_pdf_content is not None:
            pdf_content.append(processed_pdf_content)
        if processed_spreadsheet_content is not None:
            spreadsheet_content.append(processed_spreadsheet_content)

    try:
        user_query, user_query_warnings = _process_user_query(request.user_query)
    except InputProcessingError as exc:
        return InputProcessingResult(
            success=False,
            attachment_statuses=[
                AttachmentProcessingStatus(
                    filename="request",
                    status="failed",
                    error=AttachmentProcessingError(
                        filename="request",
                        code=exc.code,
                        message=exc.message,
                    ),
                )
            ],
        )
    has_usable_content = bool(
        user_query.strip() or image_content or pdf_content or spreadsheet_content
    )
    if not has_usable_content:
        return InputProcessingResult(
            success=False,
            attachment_statuses=attachment_statuses,
        )

    return InputProcessingResult(
        success=True,
        normalized_input=NormalizedInput(
            user_query=user_query,
            image_content=image_content,
            pdf_content=pdf_content,
            spreadsheet_content=spreadsheet_content,
            combined_text=_build_combined_text(
                user_query=user_query,
                image_content=image_content,
                pdf_content=pdf_content,
                spreadsheet_content=spreadsheet_content,
            ),
        ),
        attachment_statuses=attachment_statuses,
        warnings=user_query_warnings,
    )


def _process_attachment(
    attachment: Attachment,
    *,
    active_ocr_provider: OCRProvider,
    active_pdf_extractor: PDFExtractor,
    page_image_extractor: PDFPageImageExtractor | None,
    active_spreadsheet_parser: SpreadsheetParser,
) -> tuple[
    AttachmentProcessingStatus,
    ImageContent | None,
    PDFContent | None,
    SpreadsheetContent | None,
]:
    """Validate and process one attachment while returning only safe status."""

    try:
        validated_attachment = validate_attachment_modality(attachment)
    except InputProcessingError as exc:
        return (
            _failed_attachment_status(attachment.filename, exc.code, exc.message),
            None,
            None,
            None,
        )
    except Exception:
        return (
            _failed_attachment_status(
                attachment.filename,
                InputProcessingErrorCode.INTERNAL_PROCESSING_ERROR,
                "This attachment could not be processed safely.",
            ),
            None,
            None,
            None,
        )

    result_error: AttachmentProcessingError | None = None
    image_content: ImageContent | None = None
    pdf_content: PDFContent | None = None
    spreadsheet_content: SpreadsheetContent | None = None
    if validated_attachment.modality in {InputModality.PNG, InputModality.JPEG}:
        try:
            image_result = process_image_attachment(
                validated_attachment,
                active_ocr_provider,
            )
        except Exception:
            return (
                _failed_attachment_status(
                    attachment.filename,
                    InputProcessingErrorCode.INTERNAL_PROCESSING_ERROR,
                    "This attachment could not be processed safely.",
                ),
                None,
                None,
                None,
            )
        result_error = image_result.error
        image_content = image_result.image_content
    elif validated_attachment.modality == InputModality.PDF:
        try:
            pdf_result = process_pdf_attachment(
                validated_attachment,
                active_pdf_extractor,
                ocr_provider=active_ocr_provider,
                page_image_extractor=page_image_extractor,
            )
        except Exception:
            return (
                _failed_attachment_status(
                    attachment.filename,
                    InputProcessingErrorCode.INTERNAL_PROCESSING_ERROR,
                    "This attachment could not be processed safely.",
                ),
                None,
                None,
                None,
            )
        result_error = pdf_result.error
        pdf_content = pdf_result.pdf_content
    elif validated_attachment.modality == InputModality.XLSX:
        try:
            spreadsheet_result = process_spreadsheet_attachment(
                validated_attachment,
                active_spreadsheet_parser,
            )
        except Exception:
            return (
                _failed_attachment_status(
                    attachment.filename,
                    InputProcessingErrorCode.INTERNAL_PROCESSING_ERROR,
                    "This attachment could not be processed safely.",
                ),
                None,
                None,
                None,
            )
        result_error = spreadsheet_result.error
        spreadsheet_content = spreadsheet_result.spreadsheet_content
    else:
        result_error = AttachmentProcessingError(
            filename=attachment.filename,
            code=InputProcessingErrorCode.UNSUPPORTED_FORMAT,
            message="This attachment type is not supported.",
        )

    if result_error is not None:
        return (
            AttachmentProcessingStatus(
                filename=attachment.filename,
                status="failed",
                error=result_error,
            ),
            None,
            None,
            None,
        )

    return (
        AttachmentProcessingStatus(filename=attachment.filename, status="success"),
        image_content,
        pdf_content,
        spreadsheet_content,
    )


def _failed_attachment_status(
    filename: str,
    code: InputProcessingErrorCode,
    message: str,
) -> AttachmentProcessingStatus:
    return AttachmentProcessingStatus(
        filename=filename,
        status="failed",
        error=AttachmentProcessingError(
            filename=filename,
            code=code,
            message=message,
        ),
    )


def _process_user_query(
    user_query: str | None,
) -> tuple[str, list[AttachmentProcessingWarning]]:
    if user_query is None:
        return "", []

    masked_text = validate_post_extraction_boundary(
        user_query, is_user_query=True, strict_safety=False
    )
    untrusted_text = mark_document_text_untrusted(masked_text)
    warnings = []
    if untrusted_text.suspicious:
        warnings.append(
            AttachmentProcessingWarning(
                filename="request",
                code="SUSPICIOUS_INSTRUCTION",
                message=(
                    "The request contains instruction-like text and was treated as "
                    "untrusted user content."
                ),
            )
        )
    return untrusted_text.text, warnings


def _build_combined_text(
    *,
    user_query: str,
    image_content: list[ImageContent],
    pdf_content: list[PDFContent],
    spreadsheet_content: list[SpreadsheetContent],
) -> str:
    parts = []
    if user_query.strip():
        parts.append(f"<USER_QUERY>\n{user_query}")
    if image_content:
        image_text = "\n\n".join(content.extracted_text for content in image_content)
        parts.append(f"<IMAGE_CONTENT>\n{image_text}")
    if pdf_content:
        pdf_text = "\n\n".join(content.extracted_text for content in pdf_content)
        parts.append(f"<PDF_CONTENT>\n{pdf_text}")
    if spreadsheet_content:
        spreadsheet_text = "\n\n".join(
            build_spreadsheet_text_projection(content)
            for content in spreadsheet_content
        )
        parts.append(f"<SPREADSHEET_CONTENT>\n{spreadsheet_text}")
    return "\n\n".join(parts)


def build_graph_state_update(result: InputProcessingResult) -> GraphState:
    """Return the only graph-state update allowed from input processing."""

    if not result.success or result.normalized_input is None:
        return {}

    return {"normalized_input": result.normalized_input}


__all__ = ["build_graph_state_update", "process_input"]
