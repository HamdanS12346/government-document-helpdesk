"""Input Processor validation and safety guardrail boundary."""

from enum import StrEnum


class InputGuardrailDecision(StrEnum):
    """Conceptual guardrail outcomes for Input Processor checks."""

    ALLOW = "allow"
    MASK_AND_CONTINUE = "mask_and_continue"
    REJECT = "reject"
    FAIL = "fail"


def validate_pre_processing_boundary() -> InputGuardrailDecision:
    """Placeholder for structure, media type, signature, size, and page checks."""

    return InputGuardrailDecision.ALLOW


def validate_post_extraction_boundary() -> InputGuardrailDecision:
    """Placeholder for PII masking and document-content safety checks."""

    return InputGuardrailDecision.ALLOW


__all__ = [
    "InputGuardrailDecision",
    "validate_post_extraction_boundary",
    "validate_pre_processing_boundary",
]
