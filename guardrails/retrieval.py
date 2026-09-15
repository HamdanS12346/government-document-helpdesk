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
from typing import Optional

from app.contracts.response import RetrievedContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Decision enum
# ---------------------------------------------------------------------------

class RetrievalGuardrailDecision(StrEnum):
    """Possible outcomes from a retrieval-layer guardrail check."""

    ALLOW = "allow"
    SANITIZE_AND_CONTINUE = "sanitize_and_continue"
    REJECT = "reject"
    UNGROUNDED_RESPONSE_REQUIRED = "ungrounded_response_required"


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


__all__ = [
    "LowConfidenceGuard",
    "LowConfidenceResult",
    "QUERY_INJECTION_PATTERNS",
    "QueryInjectionGuard",
    "QueryInjectionResult",
    "RetrievalGuardrailDecision",
]
