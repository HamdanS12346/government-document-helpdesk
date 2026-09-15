"""Output guardrails for the Response Node.

These run AFTER the LLM generates a response and BEFORE it is returned to the user.
All checks are deterministic — no LLM calls. Each guardrail is independently testable.

PIPELINE ORDER (applied by run_response_guardrails):
  1. CitationGroundingGuardrail  — strip/reject hallucinated [Document N] references
  2. ResponsePIIScanner          — redact PII echoed back in the response
  3. ResponseLengthGuardrail     — truncate or reject responses that are too long
  4. ResponseScopeGuardrail      — redirect off-topic general_chat responses

DESIGN PRINCIPLES:
  - Fail-closed: exceptions produce REJECT, never silent pass-through.
  - No LLM calls: all logic is regex / arithmetic / set membership.
  - Composable: each guardrail exposes a single .check() or .scan() method.
  - Reuse: ResponsePIIScanner imports PII_PATTERNS from input_processor — no duplication.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Optional

from app.contracts.response import RetrievedContext
from guardrails.input_processor import PII_MASK, PII_PATTERNS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Decision enum
# ---------------------------------------------------------------------------

class ResponseGuardrailDecision(StrEnum):
    """Possible outcomes from a response-layer guardrail check."""

    ALLOW = "allow"
    STRIP_INVALID_CITATIONS = "strip_invalid_citations"
    REDACT_AND_CONTINUE = "redact_and_continue"
    TRUNCATE = "truncate"
    REPLACE_WITH_REDIRECT = "replace_with_redirect"
    REJECT = "reject"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CITATION_PATTERN = re.compile(r"\[Document\s+(\d+)\]", re.IGNORECASE)

MAX_RESPONSE_CHARS = 3_000   # ~600 words — sufficient for a detailed procedure
HARD_REJECT_CHARS = 8_000    # above this, something is clearly wrong

# Sentence-ending characters used by the truncation logic.
_SENTENCE_ENDS = frozenset(".?!")

_CITATION_REJECT_FALLBACK = (
    "I was not able to verify the sources for this response. "
    "Please check the official government portals directly or visit a "
    "helpdesk centre for accurate information."
)

_LENGTH_REJECT_FALLBACK = (
    "The response could not be prepared safely. "
    "Please try again or visit the concerned department directly."
)

_TRUNCATION_SUFFIX = (
    "\n\n[Response was shortened. "
    "Visit the relevant portal for full details.]"
)

_SCOPE_REDIRECT = (
    "That is a bit outside what I can help with here. "
    "If you have any questions about government documents, applications, "
    "or services, I am here for that."
)

FORBIDDEN_DOMAIN_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"\b(cricket|football|IPL|match score|scorecard)\b", re.I),
    re.compile(r"\b(stock price|sensex|nifty|share market|trading)\b", re.I),
    re.compile(r"\b(movie|film|bollywood|OTT|Netflix|recipe|cooking)\b", re.I),
    re.compile(r"\b(horoscope|astrology|zodiac|lottery|gambling)\b", re.I),
)

GOVERNMENT_SIGNAL_PATTERN = re.compile(
    r"\b(ministry|department|portal|aadhaar|pan card|ration|passport|"
    r"income tax|gst|voter id|birth certificate|driving licence|property|"
    r"land record|municipality|helpdesk|services\.india\.gov\.in|uidai|nsdl)\b",
    re.I,
)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class CitationGroundingResult:
    decision: ResponseGuardrailDecision
    cleaned_text: str
    invalid_citation_indices: list[int]
    total_citations_found: int


@dataclass
class ResponsePIIScanResult:
    decision: ResponseGuardrailDecision
    cleaned_text: str
    redaction_count: int


@dataclass
class ResponseLengthResult:
    decision: ResponseGuardrailDecision
    cleaned_text: str
    original_length: int
    final_length: int


@dataclass
class ResponseScopeResult:
    decision: ResponseGuardrailDecision
    cleaned_text: str
    forbidden_matches: list[str]
    government_signals_found: int


@dataclass
class ResponseGuardrailReport:
    final_text: str
    citation_result: CitationGroundingResult
    pii_result: ResponsePIIScanResult
    length_result: ResponseLengthResult
    scope_result: ResponseScopeResult
    any_triggered: bool


# ---------------------------------------------------------------------------
# Guardrail 1 — Citation Grounding Verifier
# ---------------------------------------------------------------------------

class CitationGroundingGuardrail:
    """Verify that every [Document N] reference in the response exists in the
    retrieved context. Strip invalid citations; reject if hallucination is severe.

    Skipped when retrieved_context is None (general_chat path has no context).
    """

    MAX_INVALID_CITATION_FRACTION: float = 0.50

    def check(
        self,
        response_text: str,
        retrieved_context: Optional[RetrievedContext],
    ) -> CitationGroundingResult:
        try:
            return self._check(response_text, retrieved_context)
        except Exception as exc:
            logger.error(
                "CitationGroundingGuardrail: unexpected error — failing closed. %s",
                exc,
                exc_info=True,
            )
            return CitationGroundingResult(
                decision=ResponseGuardrailDecision.REJECT,
                cleaned_text=_CITATION_REJECT_FALLBACK,
                invalid_citation_indices=[],
                total_citations_found=0,
            )

    def _check(
        self,
        response_text: str,
        retrieved_context: Optional[RetrievedContext],
    ) -> CitationGroundingResult:
        # No context available (general_chat path) — skip check.
        if retrieved_context is None:
            return CitationGroundingResult(
                decision=ResponseGuardrailDecision.ALLOW,
                cleaned_text=response_text,
                invalid_citation_indices=[],
                total_citations_found=0,
            )

        cited_indices = [
            int(m) for m in CITATION_PATTERN.findall(response_text)
        ]
        total = len(cited_indices)

        if total == 0:
            return CitationGroundingResult(
                decision=ResponseGuardrailDecision.ALLOW,
                cleaned_text=response_text,
                invalid_citation_indices=[],
                total_citations_found=0,
            )

        valid_indices = {src.index for src in retrieved_context.sources}
        invalid = [n for n in cited_indices if n not in valid_indices]

        if not invalid:
            return CitationGroundingResult(
                decision=ResponseGuardrailDecision.ALLOW,
                cleaned_text=response_text,
                invalid_citation_indices=[],
                total_citations_found=total,
            )

        invalid_fraction = len(invalid) / total

        if invalid_fraction > self.MAX_INVALID_CITATION_FRACTION:
            logger.error(
                "CitationGroundingGuardrail: REJECT — %.0f%% of %d citations are "
                "hallucinated (invalid indices: %s).",
                invalid_fraction * 100,
                total,
                invalid,
            )
            return CitationGroundingResult(
                decision=ResponseGuardrailDecision.REJECT,
                cleaned_text=_CITATION_REJECT_FALLBACK,
                invalid_citation_indices=invalid,
                total_citations_found=total,
            )

        # Strip the invalid citations from the text.
        def _replace_citation(match: re.Match) -> str:
            if int(match.group(1)) not in valid_indices:
                return "[source unavailable]"
            return match.group(0)

        cleaned = CITATION_PATTERN.sub(_replace_citation, response_text)
        logger.warning(
            "CitationGroundingGuardrail: STRIP — removed %d invalid citation(s): %s.",
            len(invalid),
            invalid,
        )
        return CitationGroundingResult(
            decision=ResponseGuardrailDecision.STRIP_INVALID_CITATIONS,
            cleaned_text=cleaned,
            invalid_citation_indices=invalid,
            total_citations_found=total,
        )


# ---------------------------------------------------------------------------
# Guardrail 2 — Response PII Scanner
# ---------------------------------------------------------------------------

class ResponsePIIScanner:
    """Scan LLM-generated response text for PII and redact it.

    Reuses PII_PATTERNS from input_processor to avoid duplication.
    Fails closed: any exception causes REJECT.
    """

    def scan(self, response_text: str) -> ResponsePIIScanResult:
        try:
            return self._scan(response_text)
        except Exception as exc:
            logger.error(
                "ResponsePIIScanner: unexpected error — failing closed. %s",
                exc,
                exc_info=True,
            )
            return ResponsePIIScanResult(
                decision=ResponseGuardrailDecision.REJECT,
                cleaned_text=_CITATION_REJECT_FALLBACK,
                redaction_count=0,
            )

    def _scan(self, response_text: str) -> ResponsePIIScanResult:
        masked = response_text
        redaction_count = 0
        for pattern in PII_PATTERNS:
            new_text, count = pattern.subn(PII_MASK, masked)
            redaction_count += count
            masked = new_text

        if redaction_count == 0:
            return ResponsePIIScanResult(
                decision=ResponseGuardrailDecision.ALLOW,
                cleaned_text=response_text,
                redaction_count=0,
            )

        logger.warning(
            "ResponsePIIScanner: REDACT — %d PII instance(s) removed from response.",
            redaction_count,
        )
        return ResponsePIIScanResult(
            decision=ResponseGuardrailDecision.REDACT_AND_CONTINUE,
            cleaned_text=masked,
            redaction_count=redaction_count,
        )


# ---------------------------------------------------------------------------
# Guardrail 3 — Response Length Cap
# ---------------------------------------------------------------------------

class ResponseLengthGuardrail:
    """Enforce a hard character limit on LLM response text.

    Truncates at the last sentence boundary below max_chars.
    Rejects entirely if the text exceeds hard_reject_chars.
    """

    def __init__(
        self,
        max_chars: int = MAX_RESPONSE_CHARS,
        hard_reject_chars: int = HARD_REJECT_CHARS,
    ) -> None:
        if max_chars >= hard_reject_chars:
            raise ValueError(
                "max_chars must be strictly less than hard_reject_chars"
            )
        self.max_chars = max_chars
        self.hard_reject_chars = hard_reject_chars

    def check(self, response_text: str) -> ResponseLengthResult:
        try:
            return self._check(response_text)
        except Exception as exc:
            logger.error(
                "ResponseLengthGuardrail: unexpected error — failing closed. %s",
                exc,
                exc_info=True,
            )
            return ResponseLengthResult(
                decision=ResponseGuardrailDecision.REJECT,
                cleaned_text=_LENGTH_REJECT_FALLBACK,
                original_length=len(response_text),
                final_length=len(_LENGTH_REJECT_FALLBACK),
            )

    def _check(self, response_text: str) -> ResponseLengthResult:
        original_length = len(response_text)

        if original_length <= self.max_chars:
            return ResponseLengthResult(
                decision=ResponseGuardrailDecision.ALLOW,
                cleaned_text=response_text,
                original_length=original_length,
                final_length=original_length,
            )

        if original_length > self.hard_reject_chars:
            logger.error(
                "ResponseLengthGuardrail: REJECT — response length %d exceeds hard "
                "limit %d.",
                original_length,
                self.hard_reject_chars,
            )
            return ResponseLengthResult(
                decision=ResponseGuardrailDecision.REJECT,
                cleaned_text=_LENGTH_REJECT_FALLBACK,
                original_length=original_length,
                final_length=len(_LENGTH_REJECT_FALLBACK),
            )

        # Truncate at last sentence boundary before max_chars.
        cut_point = self.max_chars
        for i in range(self.max_chars - 1, max(0, self.max_chars - 200), -1):
            if response_text[i] in _SENTENCE_ENDS:
                cut_point = i + 1
                break

        truncated = response_text[:cut_point].rstrip() + _TRUNCATION_SUFFIX
        logger.warning(
            "ResponseLengthGuardrail: TRUNCATE — original length %d truncated to %d.",
            original_length,
            len(truncated),
        )
        return ResponseLengthResult(
            decision=ResponseGuardrailDecision.TRUNCATE,
            cleaned_text=truncated,
            original_length=original_length,
            final_length=len(truncated),
        )


# ---------------------------------------------------------------------------
# Guardrail 4 — Off-Topic Scope Enforcer
# ---------------------------------------------------------------------------

class ResponseScopeGuardrail:
    """Detect genuinely off-topic responses in the general_chat path and replace
    them with a polite government-helpdesk redirect.

    Skipped for document_info intent — government documents legitimately reference
    a wide range of topics (film certification, sports stadia permits, etc.).

    Trigger condition: >= 2 forbidden domain matches AND 0 government signal matches.
    This prevents false positives from a single incidental keyword.
    """

    MIN_FORBIDDEN_MATCHES = 2

    def check(
        self,
        response_text: str,
        intent_type: str,
    ) -> ResponseScopeResult:
        try:
            return self._check(response_text, intent_type)
        except Exception as exc:
            logger.error(
                "ResponseScopeGuardrail: unexpected error — allowing through. %s",
                exc,
                exc_info=True,
            )
            # Fail-open for scope enforcer — wrong redirect is worse than no redirect.
            return ResponseScopeResult(
                decision=ResponseGuardrailDecision.ALLOW,
                cleaned_text=response_text,
                forbidden_matches=[],
                government_signals_found=0,
            )

    def _check(
        self,
        response_text: str,
        intent_type: str,
    ) -> ResponseScopeResult:
        # Only applies to general_chat.
        if str(intent_type).lower() != "general_chat":
            return ResponseScopeResult(
                decision=ResponseGuardrailDecision.ALLOW,
                cleaned_text=response_text,
                forbidden_matches=[],
                government_signals_found=0,
            )

        forbidden_matches: list[str] = []
        for pattern in FORBIDDEN_DOMAIN_PATTERNS:
            matches = pattern.findall(response_text)
            forbidden_matches.extend(matches)

        government_signals = GOVERNMENT_SIGNAL_PATTERN.findall(response_text)

        if (
            len(forbidden_matches) >= self.MIN_FORBIDDEN_MATCHES
            and len(government_signals) == 0
        ):
            logger.warning(
                "ResponseScopeGuardrail: REPLACE — %d forbidden domain match(es), "
                "0 government signals. Matches: %s.",
                len(forbidden_matches),
                forbidden_matches[:5],  # log up to 5 for brevity
            )
            return ResponseScopeResult(
                decision=ResponseGuardrailDecision.REPLACE_WITH_REDIRECT,
                cleaned_text=_SCOPE_REDIRECT,
                forbidden_matches=forbidden_matches,
                government_signals_found=0,
            )

        return ResponseScopeResult(
            decision=ResponseGuardrailDecision.ALLOW,
            cleaned_text=response_text,
            forbidden_matches=forbidden_matches,
            government_signals_found=len(government_signals),
        )


# ---------------------------------------------------------------------------
# Composite runner
# ---------------------------------------------------------------------------

# Module-level singleton instances — constructed once, reused on every call.
_citation_guardrail = CitationGroundingGuardrail()
_pii_scanner = ResponsePIIScanner()
_length_guardrail = ResponseLengthGuardrail()
_scope_guardrail = ResponseScopeGuardrail()


def run_response_guardrails(
    response_text: str,
    retrieved_context: Optional[RetrievedContext],
    intent_type: str,
) -> ResponseGuardrailReport:
    """Run all four response guardrails in sequence.

    Each guardrail receives the output text of the previous one.
    On REJECT, the pipeline short-circuits — later guardrails still run but on
    the safe fallback text, not the original.

    Args:
        response_text:      Raw text from the LLM AIMessage.
        retrieved_context:  RetrievedContext from state, or None for general_chat.
        intent_type:        String intent type ("document_info", "general_chat", etc.).

    Returns:
        ResponseGuardrailReport with the final cleaned text and per-guardrail results.
    """
    any_triggered = False

    # Step 1 — Citation Grounding
    citation_result = _citation_guardrail.check(response_text, retrieved_context)
    text = citation_result.cleaned_text
    if citation_result.decision != ResponseGuardrailDecision.ALLOW:
        any_triggered = True

    # Step 2 — PII Scan (operates on Step 1 output)
    pii_result = _pii_scanner.scan(text)
    text = pii_result.cleaned_text
    if pii_result.decision != ResponseGuardrailDecision.ALLOW:
        any_triggered = True

    # Step 3 — Length Cap (operates on Step 2 output)
    length_result = _length_guardrail.check(text)
    text = length_result.cleaned_text
    if length_result.decision != ResponseGuardrailDecision.ALLOW:
        any_triggered = True

    # Step 4 — Scope Enforcer (operates on Step 3 output)
    scope_result = _scope_guardrail.check(text, intent_type)
    text = scope_result.cleaned_text
    if scope_result.decision != ResponseGuardrailDecision.ALLOW:
        any_triggered = True

    return ResponseGuardrailReport(
        final_text=text,
        citation_result=citation_result,
        pii_result=pii_result,
        length_result=length_result,
        scope_result=scope_result,
        any_triggered=any_triggered,
    )


__all__ = [
    "CitationGroundingGuardrail",
    "CitationGroundingResult",
    "FORBIDDEN_DOMAIN_PATTERNS",
    "GOVERNMENT_SIGNAL_PATTERN",
    "HARD_REJECT_CHARS",
    "MAX_RESPONSE_CHARS",
    "ResponseGuardrailDecision",
    "ResponseGuardrailReport",
    "ResponseLengthGuardrail",
    "ResponseLengthResult",
    "ResponsePIIScanResult",
    "ResponsePIIScanner",
    "ResponseScopeGuardrail",
    "ResponseScopeResult",
    "run_response_guardrails",
]
