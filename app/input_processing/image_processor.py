"""Image-specific input processing boundary."""

from io import BytesIO

from pydantic import BaseModel, ConfigDict, model_validator
from PIL import Image, UnidentifiedImageError

from app.contracts.normalized_input import ImageContent
from app.input_processing.errors import InputProcessingError, InputProcessingErrorCode
from app.input_processing.ocr_provider import OCRProvider, OCRResult, OCRStatus
from app.input_processing.preview import build_image_preview
from app.input_processing.schemas import (
    AttachmentProcessingError,
    InputModality,
    ValidatedAttachment,
)
from guardrails.input_processor import (
    mark_document_text_untrusted,
    mask_pii_in_text,
)


IMAGE_QUALITY_THRESHOLD = None
UNREADABLE_IMAGE_MESSAGE = "This image could not be inspected safely."
UNUSABLE_OCR_MESSAGE = "No reliable text could be extracted from this image."


class ImageProcessingResult(BaseModel):
    """Image processor outcome with either content or a safe failure."""

    model_config = ConfigDict(extra="forbid", strict=True)

    image_content: ImageContent | None = None
    error: AttachmentProcessingError | None = None

    @model_validator(mode="after")
    def validate_result_shape(self) -> "ImageProcessingResult":
        if (self.image_content is None) == (self.error is None):
            raise ValueError("image processing result requires content or error")
        return self


def process_image_attachment(
    validated_attachment: ValidatedAttachment,
    ocr_provider: OCRProvider,
) -> ImageProcessingResult:
    """Process already-validated image bytes into normalized image content."""

    attachment = validated_attachment.attachment
    if validated_attachment.modality not in {InputModality.PNG, InputModality.JPEG}:
        return ImageProcessingResult(
            error=AttachmentProcessingError(
                filename=attachment.filename,
                code=InputProcessingErrorCode.UNSUPPORTED_FORMAT,
                message="This attachment is not a supported image.",
            )
        )

    try:
        with Image.open(BytesIO(attachment.content)) as image:
            image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        return ImageProcessingResult(
            error=AttachmentProcessingError(
                filename=attachment.filename,
                code=InputProcessingErrorCode.UNREADABLE_CONTENT,
                message=UNREADABLE_IMAGE_MESSAGE,
            )
        )

    try:
        ocr_result = ocr_provider.extract_text(attachment.content)
    except Exception:
        return ImageProcessingResult(
            error=AttachmentProcessingError(
                filename=attachment.filename,
                code=InputProcessingErrorCode.OCR_FAILURE,
                message="OCR could not be completed for this image.",
            )
        )

    if not isinstance(ocr_result, OCRResult):
        return ImageProcessingResult(
            error=AttachmentProcessingError(
                filename=attachment.filename,
                code=InputProcessingErrorCode.OCR_FAILURE,
                message="OCR provider returned an invalid result.",
            )
        )

    if ocr_result.status == OCRStatus.SUCCESS:
        try:
            return _build_successful_image_content(
                image_name=attachment.filename,
                extracted_text=ocr_result.text,
            )
        except InputProcessingError as exc:
            return ImageProcessingResult(
                error=AttachmentProcessingError(
                    filename=attachment.filename,
                    code=exc.code,
                    message=exc.message,
                )
            )
        except Exception:
            return ImageProcessingResult(
                error=AttachmentProcessingError(
                    filename=attachment.filename,
                    code=InputProcessingErrorCode.INTERNAL_PROCESSING_ERROR,
                    message="Image content could not be processed safely.",
                )
            )

    if ocr_result.status in {OCRStatus.EMPTY, OCRStatus.LOW_CONFIDENCE}:
        return ImageProcessingResult(
            error=AttachmentProcessingError(
                filename=attachment.filename,
                code=InputProcessingErrorCode.UNREADABLE_CONTENT,
                message=UNUSABLE_OCR_MESSAGE,
            )
        )

    return ImageProcessingResult(
        error=AttachmentProcessingError(
            filename=attachment.filename,
            code=InputProcessingErrorCode.OCR_FAILURE,
            message=ocr_result.message or "OCR could not be completed for this image.",
        )
    )


def _build_successful_image_content(
    *,
    image_name: str,
    extracted_text: str,
) -> ImageProcessingResult:
    masked_text = mask_pii_in_text(extracted_text).text
    safe_document_text = mark_document_text_untrusted(masked_text).text
    return ImageProcessingResult(
        image_content=ImageContent(
            image_name=image_name,
            extracted_text=safe_document_text,
            preview=build_image_preview(safe_document_text),
        )
    )


__all__ = [
    "IMAGE_QUALITY_THRESHOLD",
    "ImageProcessingResult",
    "UNREADABLE_IMAGE_MESSAGE",
    "UNUSABLE_OCR_MESSAGE",
    "process_image_attachment",
]
