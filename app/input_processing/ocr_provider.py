"""OCR provider boundary for image and scanned-document extraction."""

from enum import StrEnum
from io import BytesIO
from typing import Protocol

from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from PIL import Image, UnidentifiedImageError
import pytesseract


class OCRStatus(StrEnum):
    """Deterministic OCR outcome categories."""

    SUCCESS = "success"
    EMPTY = "empty"
    LOW_CONFIDENCE = "low_confidence"
    UNAVAILABLE = "unavailable"
    PROVIDER_ERROR = "provider_error"


class OCRResult(BaseModel):
    """Provider-independent OCR result."""

    model_config = ConfigDict(extra="forbid", strict=True)

    status: OCRStatus
    text: str = ""
    message: str | None = None

    @field_validator("text")
    @classmethod
    def reject_non_string_text(cls, value: str) -> str:
        return value

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("message must not be empty")
        return value

    @model_validator(mode="after")
    def validate_status_shape(self) -> "OCRResult":
        if self.status == OCRStatus.SUCCESS and not self.text.strip():
            raise ValueError("successful OCR result requires extracted text")
        if self.status == OCRStatus.EMPTY and self.text.strip():
            raise ValueError("empty OCR result cannot include extracted text")
        if self.status in {OCRStatus.UNAVAILABLE, OCRStatus.PROVIDER_ERROR}:
            if self.text.strip():
                raise ValueError("provider failure result cannot include extracted text")
            if self.message is None:
                raise ValueError("provider failure result requires a safe message")
        return self


class OCRProvider(Protocol):
    """Narrow replaceable OCR text-extraction capability."""

    def extract_text(self, image_content: bytes) -> OCRResult:
        """Extract text from supported image bytes."""


class TesseractOCRProvider:
    """Tesseract-backed OCR provider hidden behind the OCRProvider boundary."""

    def __init__(self, *, language: str = "eng", timeout_seconds: int = 10) -> None:
        if not language.strip():
            raise ValueError("language must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.language = language
        self.timeout_seconds = timeout_seconds

    def extract_text(self, image_content: bytes) -> OCRResult:
        """Extract text from image bytes using Tesseract."""

        try:
            with Image.open(BytesIO(image_content)) as image:
                text = pytesseract.image_to_string(
                    image,
                    lang=self.language,
                    timeout=self.timeout_seconds,
                )
        except pytesseract.TesseractNotFoundError:
            return OCRResult(
                status=OCRStatus.UNAVAILABLE,
                message="OCR provider is unavailable.",
            )
        except RuntimeError as exc:
            if "timeout" in str(exc).lower():
                return OCRResult(
                    status=OCRStatus.UNAVAILABLE,
                    message="OCR provider timed out.",
                )
            return OCRResult(
                status=OCRStatus.PROVIDER_ERROR,
                message="OCR provider could not process this image.",
            )
        except (UnidentifiedImageError, OSError):
            return OCRResult(
                status=OCRStatus.PROVIDER_ERROR,
                message="OCR provider could not inspect this image.",
            )
        except Exception:
            return OCRResult(
                status=OCRStatus.PROVIDER_ERROR,
                message="OCR provider could not process this image.",
            )

        normalized_text = text.strip()
        if not normalized_text:
            return OCRResult(
                status=OCRStatus.EMPTY,
                message="No readable text was found in this image.",
            )

        return OCRResult(status=OCRStatus.SUCCESS, text=normalized_text)


__all__ = ["OCRProvider", "OCRResult", "OCRStatus", "TesseractOCRProvider"]
