"""Retrieval-layer guardrails.

Two guardrails run inside the existing retriever and context builder nodes:

  QueryInjectionGuard  — applied BEFORE retrieval (inside RetrieverPipeline.execute)
                         Detects and neutralises hostile query patterns before they
                         reach ChromaDB or BM25.

  LowConfidenceGuard   — applied AFTER context builder (inside context_builder_node)
                         Flags turns where no relevant documents were found so that
                         monitoring systems can track ungrounded responses.

DESIGN NOTES:
  - No new LangGraph nodes are added — these are injected into existing nodes.
  - All pattern matching is deterministic regex; no LLM calls.
  - QueryInjectionGuard fails closed on REJECT (returns empty doc list).
  - LowConfidenceGuard fails open on integrity mismatch (logs but does not reject).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Dict, List, Optional

from app.contracts.response import RetrievedContext
from app.contracts.retrieval import ChunkMetadata, RetrievedDocument
from guardrails.input_processor import mask_pii_in_text

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Decision enums
# ---------------------------------------------------------------------------

class RetrievalGuardrailDecision(StrEnum):
    """Possible outcomes from a retrieval-layer guardrail check."""

    ALLOW = "allow"
    SANITIZE_AND_CONTINUE = "sanitize_and_continue"
    REJECT = "reject"
    UNGROUNDED_RESPONSE_REQUIRED = "ungrounded_response_required"


class IngestionGuardrailDecision(StrEnum):
    """Possible outcomes from document ingestion quality and safety checks."""

    ALLOW = "allow"
    SANITIZE_AND_INGEST = "sanitize_and_ingest"
    REJECT = "reject"


# ---------------------------------------------------------------------------
# Ingestion & Sanitization Constants & Patterns
# ---------------------------------------------------------------------------

MIN_CHUNK_CHARS: int = 10
MAX_CHUNK_CHARS: int = 8_000
MAX_BINARY_NON_PRINTABLE_RATIO: float = 0.15

FORBIDDEN_METADATA_KEYS: frozenset[str] = frozenset({
    "$where",
    "$eq",
    "$ne",
    "$in",
    "$nin",
    "$gt",
    "$gte",
    "$lt",
    "$lte",
    "$and",
    "$or",
    "$not",
    "__proto__",
    "constructor",
})

INGESTION_INJECTION_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(
        r"\b(ignore|disregard|forget)\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions|rules|prompts)\b",
        re.I,
    ),
    re.compile(
        r"\b(system\s+override|developer\s+mode|administrative\s+mode|god\s+mode)\b",
        re.I,
    ),
    re.compile(
        r"\b(you\s+are\s+now|act\s+as)\s+(?:an?\s+)?(?:unfiltered|jailbroken|evil|dan)\b",
        re.I,
    ),
    re.compile(
        r"\b(reveal|leak|exfiltrate|print|send)\s+(?:the\s+)?(?:system\s+prompt|secret\s+key|api\s+key|passwords?)\b",
        re.I,
    ),
    re.compile(r"\[SYSTEM(?:\s+NOTE|\s+DIRECTIVE|\s+PROMPT)?:", re.I),
    re.compile(r"<\|im_start\|>|<\|im_end\|>|<\|endoftext\|>", re.I),
)

RAW_CITATION_PATTERN: re.Pattern = re.compile(r"\[Document\s+(\d+)\]", re.IGNORECASE)
DELIMITER_INJECTION_PATTERN: re.Pattern = re.compile(
    r"(?:```system|<\|im_start\|>|<\|im_end\|>|<\|endoftext\|>)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Query injection patterns (named for safe logging)
# ---------------------------------------------------------------------------

QUERY_INJECTION_PATTERNS: dict[str, re.Pattern] = {
    # JSON fragments targeting ChromaDB $-operator where-filters
    "json_dollar_key":    re.compile(r'\{[^}]*"\$[^"]+"\s*:', re.I | re.DOTALL),
    "json_in_operator":   re.compile(r'\{[^}]*"\$in"\s*:\s*\[', re.I | re.DOTALL),
    "json_eq_operator":   re.compile(r'\{[^}]*"\$eq"\s*:', re.I | re.DOTALL),
    # SQL DML injection
    "sql_dml": re.compile(
        r"\b(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|EXEC|UNION)\b"
        r".*\b(FROM|INTO|TABLE|WHERE)\b",
        re.I,
    ),
    # Classic SQL tautology: ' OR '1'='1
    "sql_tautology":    re.compile(r"'\s*(OR|AND)\s*'\d", re.I),
    # SQL comment terminator
    "sql_comment":      re.compile(r"--\s*$", re.M),
    # Context/document manipulation instructions
    "forget_context":   re.compile(
        r"\bforget\s+(?:all\s+)?(?:previous|prior)\s+(?:context|documents)\b", re.I
    ),
    "search_password":  re.compile(
        r"\bsearch\s+for\s+documents?\s+(?:containing|with)\b.*\bpassword\b", re.I
    ),
    "list_all_docs":    re.compile(r"\blist\s+all\s+documents\b", re.I),
    # Embedding/vector extraction attempts
    "retrieve_embeddings": re.compile(r"\bretrieve\s+embeddings?\b", re.I),
    "show_vector":         re.compile(
        r"\bshow\s+(?:me\s+)?(?:the\s+)?(?:vector|embedding)\b", re.I
    ),
}


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class QueryInjectionResult:
    decision: RetrievalGuardrailDecision
    sanitized_query: str
    matched_pattern_names: list[str]
    match_count: int


@dataclass
class LowConfidenceResult:
    decision: RetrievalGuardrailDecision
    is_grounded: bool
    sources_count: int
    documents_used: int
    integrity_mismatch: bool


@dataclass
class IngestionScanResult:
    decision: IngestionGuardrailDecision
    sanitized_document: Optional[RetrievedDocument]
    redactions_count: int
    injection_patterns_detected: list[str]
    rejection_reason: Optional[str] = None


@dataclass
class RetrievedContextNeutralizerResult:
    cleaned_text: str
    fake_citations_neutralized: int
    injection_markers_neutralized: int


# ---------------------------------------------------------------------------
# Guardrail 5 — Query Injection Guard
# ---------------------------------------------------------------------------

class QueryInjectionGuard:
    """Detect hostile patterns in the retrieval query before it reaches ChromaDB or BM25.

    DECISION TABLE:
      0 matches        → ALLOW               (query is clean)
      1–2 matches      → SANITIZE_AND_CONTINUE  (strip fragments, use sanitized query)
      >= 3 matches     → REJECT              (abort retrieval, return empty doc list)

    Pattern names are logged (never the matched text) to avoid leaking hostile content
    into logs.

    Sanitization strategy:
      - Strip matched fragments from the query.
      - If the sanitized query is empty, fall back to the original user_query argument.
      - If user_query is also empty, use an empty string — retrieval returns no results
        and the response node uses its no-context fallback prompt.
    """

    MAX_SANITIZE_MATCHES: int = 2

    def check(self, query: str, user_query: Optional[str] = None) -> QueryInjectionResult:
        """Check the retrieval query for injection patterns.

        Args:
            query:      The retrieval input (possibly rewritten combined_text).
            user_query: The original user query, used as sanitization fallback.

        Returns:
            QueryInjectionResult with decision and sanitized query.
        """
        try:
            return self._check(query, user_query)
        except Exception as exc:
            logger.error(
                "QueryInjectionGuard: unexpected error — failing closed. %s",
                exc,
                exc_info=True,
            )
            return QueryInjectionResult(
                decision=RetrievalGuardrailDecision.REJECT,
                sanitized_query="",
                matched_pattern_names=[],
                match_count=0,
            )

    def _check(self, query: str, user_query: Optional[str]) -> QueryInjectionResult:
        matched_names: list[str] = []
        sanitized = query

        for name, pattern in QUERY_INJECTION_PATTERNS.items():
            if pattern.search(query):
                matched_names.append(name)
                # Strip matched fragments for sanitization.
                sanitized = pattern.sub(" ", sanitized).strip()

        match_count = len(matched_names)

        if match_count == 0:
            return QueryInjectionResult(
                decision=RetrievalGuardrailDecision.ALLOW,
                sanitized_query=query,
                matched_pattern_names=[],
                match_count=0,
            )

        if match_count > self.MAX_SANITIZE_MATCHES:
            logger.error(
                "QueryInjectionGuard: REJECT — %d injection pattern(s) detected: %s.",
                match_count,
                matched_names,
            )
            return QueryInjectionResult(
                decision=RetrievalGuardrailDecision.REJECT,
                sanitized_query="",
                matched_pattern_names=matched_names,
                match_count=match_count,
            )

        # 1–2 matches: sanitize and continue.
        # Fall back to user_query if sanitized result is too short to be useful.
        if not sanitized or len(sanitized) < 3:
            sanitized = (user_query or "").strip()

        logger.warning(
            "QueryInjectionGuard: SANITIZE — %d pattern(s) stripped: %s.",
            match_count,
            matched_names,
        )
        return QueryInjectionResult(
            decision=RetrievalGuardrailDecision.SANITIZE_AND_CONTINUE,
            sanitized_query=sanitized,
            matched_pattern_names=matched_names,
            match_count=match_count,
        )


# ---------------------------------------------------------------------------
# Guardrail 6 — Low Confidence Hallucination Guard
# ---------------------------------------------------------------------------

class LowConfidenceGuard:
    """Flag turns where retrieval found no relevant documents.

    Applied AFTER context_builder_node. Writes to guardrail_flags["retrieval_ungrounded"]
    so monitoring systems can track how often the bot responds without document evidence.

    IMPORTANT: This guardrail does NOT modify retrieved_context. It only signals state.
    The response node already handles the no-context path via its fallback prompt.

    Integrity check (fail-open): if documents_used != len(sources), logs ERROR but does
    not reject — this is a code integrity check, not a safety check.
    """

    def check(self, retrieved_context: RetrievedContext) -> LowConfidenceResult:
        """Assess whether the retrieved context is grounded.

        Args:
            retrieved_context: RetrievedContext produced by context_builder_node.

        Returns:
            LowConfidenceResult with grounding status and integrity check flag.
        """
        try:
            return self._check(retrieved_context)
        except Exception as exc:
            logger.error(
                "LowConfidenceGuard: unexpected error — treating as ungrounded. %s",
                exc,
                exc_info=True,
            )
            return LowConfidenceResult(
                decision=RetrievalGuardrailDecision.UNGROUNDED_RESPONSE_REQUIRED,
                is_grounded=False,
                sources_count=0,
                documents_used=0,
                integrity_mismatch=False,
            )

    def _check(self, retrieved_context: RetrievedContext) -> LowConfidenceResult:
        sources_count = len(retrieved_context.sources)
        documents_used = retrieved_context.documents_used

        # Integrity check: documents_used should match actual sources list length.
        integrity_mismatch = documents_used != sources_count
        if integrity_mismatch:
            logger.error(
                "LowConfidenceGuard: integrity mismatch — "
                "documents_used=%d but len(sources)=%d. "
                "This indicates a bug in context_builder_node.",
                documents_used,
                sources_count,
            )

        is_grounded = (
            retrieved_context.has_relevant_documents
            and documents_used > 0
            and not retrieved_context.fallback_applied
        )

        if not is_grounded:
            logger.warning(
                "LowConfidenceGuard: UNGROUNDED — fallback_applied=%s, "
                "has_relevant_documents=%s, documents_used=%d.",
                retrieved_context.fallback_applied,
                retrieved_context.has_relevant_documents,
                documents_used,
            )
            return LowConfidenceResult(
                decision=RetrievalGuardrailDecision.UNGROUNDED_RESPONSE_REQUIRED,
                is_grounded=False,
                sources_count=sources_count,
                documents_used=documents_used,
                integrity_mismatch=integrity_mismatch,
            )

        return LowConfidenceResult(
            decision=RetrievalGuardrailDecision.ALLOW,
            is_grounded=True,
            sources_count=sources_count,
            documents_used=documents_used,
            integrity_mismatch=integrity_mismatch,
        )


# ---------------------------------------------------------------------------
# Guardrail 7 — Document Ingestion & Corpus Poisoning Guard
# ---------------------------------------------------------------------------

class DocumentIngestionGuard:
    """Guardrail ensuring document corpus quality, privacy, and safety during ingestion.

    Applies to chunks before they are indexed into ChromaDB or BM25:
      1. Enforces chunk length boundaries (MIN_CHUNK_CHARS <= len <= MAX_CHUNK_CHARS).
      2. Detects binary corruption or non-printable character sequences.
      3. Redacts all sensitive citizen PII using mask_pii_in_text().
      4. Scans for and neutralizes/rejects indirect prompt injection attacks.
      5. Sanitizes document metadata by stripping forbidden query-operator keys.
    """

    def check_chunk(self, doc: RetrievedDocument) -> IngestionScanResult:
        """Validate and sanitize a single document chunk."""
        if not isinstance(doc, RetrievedDocument):
            try:
                doc = RetrievedDocument.model_validate(doc)
            except Exception as exc:
                logger.error("DocumentIngestionGuard: failed to validate document schema: %s", exc)
                return IngestionScanResult(
                    decision=IngestionGuardrailDecision.REJECT,
                    sanitized_document=None,
                    redactions_count=0,
                    injection_patterns_detected=[],
                    rejection_reason="invalid_document_schema",
                )

        content = doc.text_content or ""

        # 1. Boundary check: Length
        if len(content.strip()) < MIN_CHUNK_CHARS:
            logger.warning(
                "DocumentIngestionGuard: chunk '%s' rejected — too short (%d chars).",
                doc.id,
                len(content.strip()),
            )
            return IngestionScanResult(
                decision=IngestionGuardrailDecision.REJECT,
                sanitized_document=None,
                redactions_count=0,
                injection_patterns_detected=[],
                rejection_reason="chunk_too_short",
            )

        if len(content) > MAX_CHUNK_CHARS:
            logger.warning(
                "DocumentIngestionGuard: chunk '%s' rejected — exceeds max size (%d > %d).",
                doc.id,
                len(content),
                MAX_CHUNK_CHARS,
            )
            return IngestionScanResult(
                decision=IngestionGuardrailDecision.REJECT,
                sanitized_document=None,
                redactions_count=0,
                injection_patterns_detected=[],
                rejection_reason="chunk_too_large",
            )

        # 2. Binary / corruption check
        non_printable = sum(1 for ch in content if not (ch.isprintable() or ch in "\r\n\t"))
        if (non_printable / max(1, len(content))) > MAX_BINARY_NON_PRINTABLE_RATIO:
            logger.warning(
                "DocumentIngestionGuard: chunk '%s' rejected — binary or corrupted text.",
                doc.id,
            )
            return IngestionScanResult(
                decision=IngestionGuardrailDecision.REJECT,
                sanitized_document=None,
                redactions_count=0,
                injection_patterns_detected=[],
                rejection_reason="binary_or_corrupt_content",
            )

        # 3. Indirect prompt injection / poisoning check
        detected_injections: list[str] = []
        for pat in INGESTION_INJECTION_PATTERNS:
            matches = pat.findall(content)
            if matches:
                detected_injections.extend([str(m) if isinstance(m, str) else m[0] for m in matches])

        # If >= 2 distinct injection patterns or explicit system directive, reject chunk
        if len(detected_injections) >= 2 or any("system" in m.lower() for m in detected_injections):
            logger.error(
                "DocumentIngestionGuard: chunk '%s' REJECTED — prompt injection detected: %s",
                doc.id,
                detected_injections,
            )
            return IngestionScanResult(
                decision=IngestionGuardrailDecision.REJECT,
                sanitized_document=None,
                redactions_count=0,
                injection_patterns_detected=detected_injections,
                rejection_reason="prompt_injection_detected",
            )

        # If single mild match, neutralize it
        working_content = content
        if detected_injections:
            for pat in INGESTION_INJECTION_PATTERNS:
                working_content = pat.sub("[neutralized_instruction]", working_content)

        # 4. PII scrubbing
        pii_result = mask_pii_in_text(working_content)
        final_content = pii_result.text
        redactions_count = final_content.count("[REDACTED]") - working_content.count("[REDACTED]")
        if redactions_count <= 0 and final_content != working_content:
            redactions_count = 1

        # 5. Metadata sanitization
        metadata_altered = False
        raw_meta_dict = doc.metadata.model_dump()
        clean_meta_dict: dict[str, Any] = {}
        for k, v in raw_meta_dict.items():
            if k.lower() in FORBIDDEN_METADATA_KEYS or k.startswith("$"):
                metadata_altered = True
                continue
            if isinstance(v, (str, int, float, bool)) or v is None:
                clean_meta_dict[k] = v
            else:
                clean_meta_dict[k] = str(v)
                metadata_altered = True

        cleaned_metadata = ChunkMetadata.model_validate(clean_meta_dict)

        # Determine if sanitized
        is_sanitized = (
            final_content != content
            or bool(detected_injections)
            or metadata_altered
        )

        sanitized_doc = doc.model_copy(
            update={"text_content": final_content, "metadata": cleaned_metadata}
        )

        if is_sanitized:
            return IngestionScanResult(
                decision=IngestionGuardrailDecision.SANITIZE_AND_INGEST,
                sanitized_document=sanitized_doc,
                redactions_count=redactions_count,
                injection_patterns_detected=detected_injections,
            )

        return IngestionScanResult(
            decision=IngestionGuardrailDecision.ALLOW,
            sanitized_document=doc,
            redactions_count=0,
            injection_patterns_detected=[],
        )

    def validate_and_sanitize_corpus(
        self,
        docs: List[RetrievedDocument],
    ) -> tuple[List[RetrievedDocument], dict[str, int]]:
        """Batch validate and sanitize a list of documents before indexing.

        Drops rejected documents and returns only clean/sanitized documents.
        """
        sanitized_docs: List[RetrievedDocument] = []
        stats = {
            "total_scanned": len(docs),
            "accepted": 0,
            "sanitized": 0,
            "rejected": 0,
            "total_redactions": 0,
        }

        for doc in docs:
            res = self.check_chunk(doc)
            if res.decision == IngestionGuardrailDecision.REJECT:
                stats["rejected"] += 1
            elif res.decision == IngestionGuardrailDecision.SANITIZE_AND_INGEST:
                stats["sanitized"] += 1
                stats["accepted"] += 1
                stats["total_redactions"] += res.redactions_count
                if res.sanitized_document is not None:
                    sanitized_docs.append(res.sanitized_document)
            else:
                stats["accepted"] += 1
                if res.sanitized_document is not None:
                    sanitized_docs.append(res.sanitized_document)

        logger.info(
            "DocumentIngestionGuard: corpus scan complete — %d total, %d accepted (%d sanitized), %d rejected.",
            stats["total_scanned"],
            stats["accepted"],
            stats["sanitized"],
            stats["rejected"],
        )
        return sanitized_docs, stats


# ---------------------------------------------------------------------------
# Guardrail 8 — Retrieved Context Neutralizer
# ---------------------------------------------------------------------------

class RetrievedContextNeutralizer:
    """Neutralizes potential delimiter/citation injections in retrieved context passages."""

    def neutralize(self, text: str) -> RetrievedContextNeutralizerResult:
        if not text:
            return RetrievedContextNeutralizerResult(
                cleaned_text=text,
                fake_citations_neutralized=0,
                injection_markers_neutralized=0,
            )

        fake_citations = len(RAW_CITATION_PATTERN.findall(text))
        cleaned = RAW_CITATION_PATTERN.sub(r"(DocRef \1)", text)

        delimiters = len(DELIMITER_INJECTION_PATTERN.findall(cleaned))
        cleaned = DELIMITER_INJECTION_PATTERN.sub(" ", cleaned)

        return RetrievedContextNeutralizerResult(
            cleaned_text=cleaned,
            fake_citations_neutralized=fake_citations,
            injection_markers_neutralized=delimiters,
        )


__all__ = [
    "DELIMITER_INJECTION_PATTERN",
    "DocumentIngestionGuard",
    "FORBIDDEN_METADATA_KEYS",
    "INGESTION_INJECTION_PATTERNS",
    "IngestionGuardrailDecision",
    "IngestionScanResult",
    "LowConfidenceGuard",
    "LowConfidenceResult",
    "MAX_CHUNK_CHARS",
    "MIN_CHUNK_CHARS",
    "QUERY_INJECTION_PATTERNS",
    "QueryInjectionGuard",
    "QueryInjectionResult",
    "RAW_CITATION_PATTERN",
    "RetrievalGuardrailDecision",
    "RetrievedContextNeutralizer",
    "RetrievedContextNeutralizerResult",
]
