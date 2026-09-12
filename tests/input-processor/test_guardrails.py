"""Guardrail boundary tests for the Input Processor."""

import pytest

from app.input_processing.errors import InputProcessingError, InputProcessingErrorCode
from guardrails.input_processor import (
    InputGuardrailDecision,
    PIIMaskingResult,
    RegexPIIMasker,
    mask_pii_in_text,
)


def test_default_pii_masker_allows_text_without_detected_pii() -> None:
    result = mask_pii_in_text("Attach the completed form at the local office.")

    assert result.text == "Attach the completed form at the local office."
    assert result.decision == InputGuardrailDecision.ALLOW


def test_default_pii_masker_masks_and_continues_when_pii_like_text_is_detected() -> None:
    text = (
        "Applicant PAN ABCDE1234F, Aadhaar 1234 5678 9012, "
        "phone 9876543210, email citizen@example.test."
    )

    result = mask_pii_in_text(text)

    assert result.decision == InputGuardrailDecision.MASK_AND_CONTINUE
    assert result.text == (
        "Applicant PAN [REDACTED], Aadhaar [REDACTED], "
        "phone [REDACTED], email [REDACTED]."
    )
    assert "ABCDE1234F" not in result.text
    assert "1234 5678 9012" not in result.text
    assert "9876543210" not in result.text
    assert "citizen@example.test" not in result.text


def test_pii_boundary_accepts_replaceable_masker() -> None:
    class StaticMasker:
        def mask(self, text: str) -> PIIMaskingResult:
            return PIIMaskingResult(
                text=text.replace("fictional sensitive value", "[REDACTED]"),
                decision=InputGuardrailDecision.MASK_AND_CONTINUE,
            )

    result = mask_pii_in_text(
        "This contains a fictional sensitive value.",
        masker=StaticMasker(),
    )

    assert result.text == "This contains a [REDACTED]."
    assert result.decision == InputGuardrailDecision.MASK_AND_CONTINUE


def test_pii_boundary_does_not_treat_detector_failure_as_no_pii() -> None:
    class FailingMasker:
        def mask(self, text: str) -> PIIMaskingResult:
            raise RuntimeError("provider unavailable")

    with pytest.raises(InputProcessingError) as exc_info:
        mask_pii_in_text("Potentially sensitive extracted text.", masker=FailingMasker())

    assert exc_info.value.code == InputProcessingErrorCode.PII_PROCESSING_FAILURE
    assert exc_info.value.message == "PII processing could not be completed safely."


def test_regex_pii_masker_is_the_default_boundary_implementation() -> None:
    result = RegexPIIMasker().mask("Reference PAN ABCDE1234F.")

    assert result.text == "Reference PAN [REDACTED]."
    assert result.decision == InputGuardrailDecision.MASK_AND_CONTINUE
