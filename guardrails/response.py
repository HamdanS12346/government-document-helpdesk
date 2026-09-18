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
from guardrails.input_processor import PII_MASK, PII_PATTERNS, RegexPIIMasker

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
    REPLACE_WITH_FALLBACK = "replace_with_fallback"
    WARN_AND_APPEND = "warn_and_append"
    REJECT = "reject"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CITATION_PATTERN = re.compile(r"\[Document\s+(\d+)\]", re.IGNORECASE)

MAX_RESPONSE_CHARS = 3_000   # ~600 words — sufficient for a detailed procedure
HARD_REJECT_CHARS = 8_000    # above this, something is clearly wrong

# Sentence-ending characters used by the truncation logic.
_SENTENCE_ENDS = frozenset(".?!")

_HALLUCINATION_FALLBACK = (
    "I was not able to verify the specific fee, date, or requirement details for this query "
    "against official documents. Please check the official government portal directly for accurate figures."
)

_HALLUCINATION_NOTICE_SUFFIX = (
    "\n\n[Official Notice: Specific fee, deadline, or requirement figures in this response "
    "could not be verified against the retrieved source documents. Please verify directly on the official portal.]"
)

FEE_PATTERNS: tuple[re.Pattern, ...] = (
    # ₹ 500, Rs. 250, INR 1000
    re.compile(r"(?:₹|Rs\.?|INR)\s*([0-9]+(?:,[0-9]+)*(?:\.[0-9]{1,2})?)", re.IGNORECASE),
    # 500 rupees / 500 Rs
    re.compile(r"\b([0-9]+(?:,[0-9]+)*)\s*(?:rupees|lakhs?|crores?)\b", re.IGNORECASE),
)

DATE_DEADLINE_PATTERNS: tuple[re.Pattern, ...] = (
    # Explicit dates: 15th August 2024, 31 March, 01/04/2025
    re.compile(
        r"\b([0-9]{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)(?:\s+[0-9]{2,4})?)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})\b"),
    # Deadlines: within 30 days, within 6 months
    re.compile(r"\b(within\s+[0-9]+\s+(?:days?|weeks?|months?|years?))\b", re.IGNORECASE),
    # Validity: valid for 10 years, validity of 5 years
    re.compile(r"\b(valid\s+(?:for|of)\s+[0-9]+\s+(?:days?|weeks?|months?|years?))\b", re.IGNORECASE),
)

REQUIREMENT_PATTERNS: tuple[re.Pattern, ...] = (
    # Age requirements: minimum age of 18 years, at least 21 years
    re.compile(
        r"\b((?:minimum|maximum|at\s+least|above|below)\s+(?:age\s+(?:of\s+)?)?[0-9]+\s+(?:years?|yrs?))\b",
        re.IGNORECASE,
    ),
)

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


# Stop words for citation statement grounding checks
_CITATION_COMMON_STOP_WORDS: frozenset[str] = frozenset({
    "a", "about", "above", "after", "again", "against", "all", "also", "am", "an",
    "and", "any", "are", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "could", "did", "do", "does",
    "doing", "down", "during", "each", "few", "for", "from", "further", "had",
    "has", "have", "having", "he", "her", "here", "hers", "herself", "him",
    "himself", "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself",
    "just", "me", "more", "most", "my", "myself", "no", "nor", "not", "now",
    "of", "off", "on", "once", "only", "or", "other", "our", "ours", "ourselves",
    "out", "over", "own", "same", "she", "should", "so", "some", "such", "than",
    "that", "the", "their", "theirs", "them", "themselves", "then", "there",
    "these", "they", "this", "those", "through", "to", "too", "under", "until",
    "up", "very", "was", "we", "were", "what", "when", "where", "which", "while",
    "who", "whom", "why", "will", "with", "would", "you", "your", "yours",
    "yourself", "yourselves",
})

_CITATION_PROCEDURAL_WORDS: frozenset[str] = frozenset({
    "see", "refer", "details", "document", "documents", "content", "source",
    "sources", "url", "portal", "official", "please", "note", "per", "according",
    "given", "mentioned", "stated", "state", "states", "information", "info",
    "guidance", "visit", "website", "follow", "following", "step", "steps",
    "procedure", "process", "provide", "provides", "provided", "check", "online",
    "available", "link", "form", "forms", "application", "apply", "applying",
    "service", "services", "requirement", "requirements", "submit", "submitting",
    "submission",
})


# ---------------------------------------------------------------------------
# Citation grounding helper functions
# ---------------------------------------------------------------------------

def extract_document_chunks(formatted_context: str) -> dict[int, str]:
    """Parse formatted_context into a mapping of document index -> chunk text."""
    if not formatted_context or not isinstance(formatted_context, str):
        return {}
    chunks: dict[int, str] = {}
    pattern = re.compile(
        r"\[Document\s+(\d+)\](.*?)(?=(?:\[Document\s+\d+\]|\Z))",
        re.DOTALL | re.IGNORECASE,
    )
    for m in pattern.finditer(formatted_context):
        idx = int(m.group(1))
        body = m.group(2).strip()
        body = re.sub(r"\n*---\s*$", "", body).strip()
        chunks[idx] = body
    return chunks


def _find_boundary_backwards(text: str, start: int) -> int:
    pos = start
    while pos > 0:
        char = text[pos - 1]
        if char == "\n":
            break
        if char in ".?!":
            # Don't break on decimal numbers like 3.14 or abbreviations
            if char == "." and pos > 1 and text[pos - 2].isdigit() and pos < len(text) and text[pos].isdigit():
                pos -= 1
                continue
            if char == "." and pos >= 3 and text[pos - 3:pos - 1].lower() in {"rs", "no", "dr", "mr", "ms"}:
                pos -= 1
                continue
            break
        pos -= 1
    return pos


def _find_boundary_forwards(text: str, end: int) -> int:
    pos = end
    while pos < len(text):
        char = text[pos]
        if char == "\n":
            break
        if char in ".?!":
            if char == "." and pos + 1 < len(text) and text[pos - 1].isdigit() and text[pos + 1].isdigit():
                pos += 1
                continue
            pos += 1
            break
        pos += 1
    return pos


def extract_statement_tokens(statement: str) -> tuple[list[str], list[str]]:
    """Extract substantive and procedural tokens from statement text, stripping citations."""
    clean = CITATION_PATTERN.sub("", statement)
    clean = re.sub(r"\[source unavailable\]", "", clean, flags=re.I)
    raw_tokens = re.findall(r"\b[a-z0-9_-]{2,}\b", clean.lower())
    substantive = [
        t for t in raw_tokens
        if t not in _CITATION_COMMON_STOP_WORDS and t not in _CITATION_PROCEDURAL_WORDS
    ]
    procedural = [
        t for t in raw_tokens
        if t in _CITATION_PROCEDURAL_WORDS and t not in _CITATION_COMMON_STOP_WORDS
    ]
    return substantive, procedural


def extract_enclosing_statement(text: str, start: int, end: int) -> str:
    """Extract the sentence or clause enclosing the citation at text[start:end]."""
    left = _find_boundary_backwards(text, start)
    right = _find_boundary_forwards(text, end)
    statement = text[left:right].strip()

    substantive, _ = extract_statement_tokens(statement)
    # If the statement is too short to carry semantic claim content (e.g. "See [Document 1]."),
    # extend backwards to include the preceding sentence if available.
    if len(substantive) < 2 and left > 0:
        prev_left = _find_boundary_backwards(text, left - 1)
        extended = text[prev_left:right].strip()
        ext_substantive, _ = extract_statement_tokens(extended)
        if len(ext_substantive) >= len(substantive):
            statement = extended

    return statement


def is_statement_supported_by_chunk(
    statement: str,
    chunk_content: str,
    threshold: float = 0.30,
) -> bool:
    """Verify whether chunk_content provides textual evidence for the statement."""
    if not chunk_content or not chunk_content.strip():
        return False

    substantive, procedural = extract_statement_tokens(statement)
    chunk_lower = chunk_content.lower()

    if substantive:
        unique_substantive = set(substantive)
        matched = [
            t for t in unique_substantive
            if re.search(r"\b" + re.escape(t) + r"\b", chunk_lower)
        ]
        n = len(unique_substantive)
        if n <= 2:
            return len(matched) >= 1
        elif n == 3:
            return len(matched) >= 1 and (len(matched) / n) >= 0.25
        else:
            return len(matched) >= 2 and (len(matched) / n) >= threshold

    if procedural:
        unique_procedural = set(procedural)
        matched = [
            t for t in unique_procedural
            if re.search(r"\b" + re.escape(t) + r"\b", chunk_lower)
        ]
        return len(matched) >= 1

    # Neither substantive nor procedural words found (e.g. punctuation or empty)
    return True


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class CitationGroundingResult:
    decision: ResponseGuardrailDecision
    cleaned_text: str
    invalid_citation_indices: list[int]
    total_citations_found: int
    unsupported_citation_indices: list[int] = field(default_factory=list)
    supported_citations_found: int = 0


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
class HallucinationCheckResult:
    decision: ResponseGuardrailDecision
    cleaned_text: str
    unsupported_entities: list[str]
    supported_entities: list[str]
    total_entities_found: int


@dataclass
class ResponseGuardrailReport:
    final_text: str
    citation_result: CitationGroundingResult
    pii_result: ResponsePIIScanResult
    length_result: ResponseLengthResult
    scope_result: ResponseScopeResult
    any_triggered: bool
    hallucination_result: Optional[HallucinationCheckResult] = None


# ---------------------------------------------------------------------------
# Guardrail 1 — Citation Grounding Verifier
# ---------------------------------------------------------------------------

class CitationGroundingGuardrail:
    """Verify that every [Document N] reference in the response exists in the
    retrieved context and that the cited document chunk actually supports the claim.
    Strip invalid/unsupported citations; reject if hallucination is severe.

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
                unsupported_citation_indices=[],
                supported_citations_found=0,
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
                unsupported_citation_indices=[],
                supported_citations_found=0,
            )

        matches = list(CITATION_PATTERN.finditer(response_text))
        total = len(matches)

        if total == 0:
            return CitationGroundingResult(
                decision=ResponseGuardrailDecision.ALLOW,
                cleaned_text=response_text,
                invalid_citation_indices=[],
                total_citations_found=0,
                unsupported_citation_indices=[],
                supported_citations_found=0,
            )

        sources = (
            retrieved_context.get("sources", [])
            if isinstance(retrieved_context, dict)
            else getattr(retrieved_context, "sources", [])
        ) or []
        valid_indices = {
            src.get("index") if isinstance(src, dict) else getattr(src, "index", None)
            for src in sources
        }
        valid_indices = {idx for idx in valid_indices if idx is not None}

        formatted_context = (
            retrieved_context.get("formatted_context", "")
            if isinstance(retrieved_context, dict)
            else getattr(retrieved_context, "formatted_context", "")
        ) or ""

        chunks = extract_document_chunks(formatted_context)

        invalid_indices: list[int] = []
        unsupported_indices: list[int] = []
        supported_count = 0
        replacements: list[tuple[int, int, str]] = []

        for match in matches:
            idx = int(match.group(1))
            if idx not in valid_indices:
                if idx not in invalid_indices:
                    invalid_indices.append(idx)
                replacements.append((match.start(), match.end(), "[source unavailable]"))
                continue

            # Index exists in sources. If chunks were parsed, verify statement support.
            if chunks and idx in chunks:
                statement = extract_enclosing_statement(response_text, match.start(), match.end())
                if is_statement_supported_by_chunk(statement, chunks[idx]):
                    supported_count += 1
                else:
                    if idx not in invalid_indices:
                        invalid_indices.append(idx)
                    if idx not in unsupported_indices:
                        unsupported_indices.append(idx)
                    replacements.append((match.start(), match.end(), "[source unavailable]"))
            else:
                # No chunk blocks parsed (e.g. minimal test fixtures) -> fallback to valid index check
                supported_count += 1

        if not replacements:
            return CitationGroundingResult(
                decision=ResponseGuardrailDecision.ALLOW,
                cleaned_text=response_text,
                invalid_citation_indices=[],
                total_citations_found=total,
                unsupported_citation_indices=[],
                supported_citations_found=supported_count,
            )

        invalid_fraction = len(replacements) / total

        if invalid_fraction > self.MAX_INVALID_CITATION_FRACTION:
            logger.error(
                "CitationGroundingGuardrail: REJECT — %.0f%% of %d citations are "
                "invalid or unsupported (invalid: %s, unsupported: %s).",
                invalid_fraction * 100,
                total,
                invalid_indices,
                unsupported_indices,
            )
            return CitationGroundingResult(
                decision=ResponseGuardrailDecision.REJECT,
                cleaned_text=_CITATION_REJECT_FALLBACK,
                invalid_citation_indices=invalid_indices,
                total_citations_found=total,
                unsupported_citation_indices=unsupported_indices,
                supported_citations_found=supported_count,
            )

        # Apply replacements in reverse order so character offsets remain valid
        cleaned = response_text
        for start, end, repl in reversed(replacements):
            cleaned = cleaned[:start] + repl + cleaned[end:]

        logger.warning(
            "CitationGroundingGuardrail: STRIP — removed %d invalid/unsupported citation(s): %s.",
            len(replacements),
            invalid_indices,
        )
        return CitationGroundingResult(
            decision=ResponseGuardrailDecision.STRIP_INVALID_CITATIONS,
            cleaned_text=cleaned,
            invalid_citation_indices=invalid_indices,
            total_citations_found=total,
            unsupported_citation_indices=unsupported_indices,
            supported_citations_found=supported_count,
        )


# ---------------------------------------------------------------------------
# Guardrail 2 — Factuality & Hallucination Check (Fees, Dates & Requirements)
# ---------------------------------------------------------------------------

class FactualityHallucinationGuardrail:
    """Verify that fees, application deadlines, and numerical requirements mentioned
    in the response are grounded in the retrieved context.

    Prevents hallucinating fabricated fees (e.g. claiming ₹2,500 when document says ₹200)
    or invalid application deadlines.
    """

    MAX_UNGROUNDED_FRACTION: float = 0.50

    def check(
        self,
        response_text: str,
        retrieved_context: Optional[RetrievedContext],
    ) -> HallucinationCheckResult:
        if not response_text or not response_text.strip():
            return HallucinationCheckResult(
                decision=ResponseGuardrailDecision.ALLOW,
                cleaned_text=response_text,
                unsupported_entities=[],
                supported_entities=[],
                total_entities_found=0,
            )

        try:
            return self._check(response_text, retrieved_context)
        except Exception as exc:
            logger.error(
                "FactualityHallucinationGuardrail: unexpected error — failing closed. %s",
                exc,
                exc_info=True,
            )
            return HallucinationCheckResult(
                decision=ResponseGuardrailDecision.REPLACE_WITH_FALLBACK,
                cleaned_text=_HALLUCINATION_FALLBACK,
                unsupported_entities=["error_fail_closed"],
                supported_entities=[],
                total_entities_found=1,
            )

    def _check(
        self,
        response_text: str,
        retrieved_context: Optional[RetrievedContext],
    ) -> HallucinationCheckResult:
        # If no context is available (general_chat path), skip verification
        if retrieved_context is None:
            return HallucinationCheckResult(
                decision=ResponseGuardrailDecision.ALLOW,
                cleaned_text=response_text,
                unsupported_entities=[],
                supported_entities=[],
                total_entities_found=0,
            )

        formatted_context = (
            retrieved_context.get("formatted_context", "")
            if isinstance(retrieved_context, dict)
            else getattr(retrieved_context, "formatted_context", "")
        ) or ""

        if not formatted_context:
            return HallucinationCheckResult(
                decision=ResponseGuardrailDecision.ALLOW,
                cleaned_text=response_text,
                unsupported_entities=[],
                supported_entities=[],
                total_entities_found=0,
            )

        context_text = formatted_context.lower()

        extracted: list[str] = []
        for pat in FEE_PATTERNS:
            for match in pat.finditer(response_text):
                extracted.append(match.group(0))

        for pat in DATE_DEADLINE_PATTERNS:
            for match in pat.finditer(response_text):
                extracted.append(match.group(0))

        for pat in REQUIREMENT_PATTERNS:
            for match in pat.finditer(response_text):
                extracted.append(match.group(0))

        # Deduplicate while preserving order
        unique_entities: list[str] = []
        for ent in extracted:
            clean = ent.strip()
            if clean and clean not in unique_entities:
                unique_entities.append(clean)

        if not unique_entities:
            return HallucinationCheckResult(
                decision=ResponseGuardrailDecision.ALLOW,
                cleaned_text=response_text,
                unsupported_entities=[],
                supported_entities=[],
                total_entities_found=0,
            )

        supported: list[str] = []
        unsupported: list[str] = []

        for entity in unique_entities:
            norm = entity.lower()
            # 1. Exact or direct substring match
            if norm in context_text:
                supported.append(entity)
                continue

            # 2. Check numeric value presence
            nums = re.findall(r"\d+", norm)
            words = [w for w in re.findall(r"[a-z]+", norm) if len(w) > 2]

            if nums and all(n in context_text for n in nums):
                if not words or any(w in context_text for w in words):
                    supported.append(entity)
                    continue

            unsupported.append(entity)

        total = len(unique_entities)
        if not unsupported:
            return HallucinationCheckResult(
                decision=ResponseGuardrailDecision.ALLOW,
                cleaned_text=response_text,
                unsupported_entities=[],
                supported_entities=supported,
                total_entities_found=total,
            )

        unsupported_fraction = len(unsupported) / total
        logger.warning(
            "FactualityHallucinationGuardrail: ungrounded entities detected: %s (total: %d, fraction: %.2f)",
            unsupported,
            total,
            unsupported_fraction,
        )

        if unsupported_fraction > self.MAX_UNGROUNDED_FRACTION:
            return HallucinationCheckResult(
                decision=ResponseGuardrailDecision.REPLACE_WITH_FALLBACK,
                cleaned_text=_HALLUCINATION_FALLBACK,
                unsupported_entities=unsupported,
                supported_entities=supported,
                total_entities_found=total,
            )

        cleaned = response_text.rstrip() + _HALLUCINATION_NOTICE_SUFFIX
        return HallucinationCheckResult(
            decision=ResponseGuardrailDecision.WARN_AND_APPEND,
            cleaned_text=cleaned,
            unsupported_entities=unsupported,
            supported_entities=supported,
            total_entities_found=total,
        )


EntityHallucinationGuardrail = FactualityHallucinationGuardrail


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
        result = RegexPIIMasker().mask(response_text)

        if result.redaction_count == 0:
            return ResponsePIIScanResult(
                decision=ResponseGuardrailDecision.ALLOW,
                cleaned_text=response_text,
                redaction_count=0,
            )

        logger.warning(
            "ResponsePIIScanner: REDACT — %d PII instance(s) removed from response.",
            result.redaction_count,
        )
        return ResponsePIIScanResult(
            decision=ResponseGuardrailDecision.REDACT_AND_CONTINUE,
            cleaned_text=result.text,
            redaction_count=result.redaction_count,
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
_factuality_guardrail = FactualityHallucinationGuardrail()
_pii_scanner = ResponsePIIScanner()
_length_guardrail = ResponseLengthGuardrail()
_scope_guardrail = ResponseScopeGuardrail()


def run_response_guardrails(
    response_text: str,
    retrieved_context: Optional[RetrievedContext],
    intent_type: str,
) -> ResponseGuardrailReport:
    """Run all response guardrails in sequence.

    Each guardrail receives the output text of the previous one.
    On REJECT or replacement, the pipeline continues on the safe fallback text,
    ensuring downstream checks (PII, Length, Scope) validate it.

    Args:
        response_text:      Raw text from the LLM AIMessage.
        retrieved_context:  RetrievedContext from state, or None for general_chat / clarification.
        intent_type:        String intent type ("document_info", "general_chat", "ambiguous", etc.).

    Returns:
        ResponseGuardrailReport with the final cleaned text and per-guardrail results.
    """
    any_triggered = False

    # Step 1 — Citation Grounding
    citation_result = _citation_guardrail.check(response_text, retrieved_context)
    text = citation_result.cleaned_text
    if citation_result.decision != ResponseGuardrailDecision.ALLOW:
        any_triggered = True

    # Step 2 — Factuality & Hallucination Check (Fees, Dates & Requirements)
    hallucination_result = _factuality_guardrail.check(text, retrieved_context)
    text = hallucination_result.cleaned_text
    if hallucination_result.decision != ResponseGuardrailDecision.ALLOW:
        any_triggered = True

    # Step 4 — PII Scan (operates on Step 3 output)
    pii_result = _pii_scanner.scan(text)
    text = pii_result.cleaned_text
    if pii_result.decision != ResponseGuardrailDecision.ALLOW:
        any_triggered = True

    # Step 5 — Length Cap (operates on Step 4 output)
    length_result = _length_guardrail.check(text)
    text = length_result.cleaned_text
    if length_result.decision != ResponseGuardrailDecision.ALLOW:
        any_triggered = True

    # Step 6 — Scope Enforcer (operates on Step 5 output)
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
        hallucination_result=hallucination_result,
    )


__all__ = [
    "CitationGroundingGuardrail",
    "CitationGroundingResult",
    "DATE_DEADLINE_PATTERNS",
    "EntityHallucinationGuardrail",
    "FEE_PATTERNS",
    "FORBIDDEN_DOMAIN_PATTERNS",
    "FactualityHallucinationGuardrail",
    "GOVERNMENT_SIGNAL_PATTERN",
    "HARD_REJECT_CHARS",
    "HallucinationCheckResult",
    "MAX_RESPONSE_CHARS",
    "REQUIREMENT_PATTERNS",
    "ResponseGuardrailDecision",
    "ResponseGuardrailReport",
    "ResponseLengthGuardrail",
    "ResponseLengthResult",
    "ResponsePIIScanResult",
    "ResponsePIIScanner",
    "ResponseScopeGuardrail",
    "ResponseScopeResult",
    "extract_document_chunks",
    "extract_enclosing_statement",
    "is_statement_supported_by_chunk",
    "run_response_guardrails",
]

