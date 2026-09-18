"""LangGraph node implementation for the Context Builder.

STATE CONTRACT
--------------
Receives from state:
  state["documents"]  — List[RetrievedDocument] written by the Retriever node.

Writes to state:
  state["retrieved_context"]  — RetrievedContext consumed by the Response Node.

DESIGN RESPONSIBILITY
---------------------
This file is intentionally thin. Its only job is to:
  1. Extract state["documents"].
  2. Delegate all transformation logic to ContextBuilder (in builder.py).
  3. Return the correct state update dict for LangGraph.

No business logic lives here. Business logic belongs in builder.py.
No text rendering lives here. Text rendering belongs in formatter.py.
"""

import logging
from typing import Any, Dict, Optional

from app.rag.context_builder.builder import ContextBuilder
from app.contracts.retrieval import RetrievalStatus
from app.contracts.response import RetrievedContext
from app.observability import start_observation
from app.observability.metadata import (
    build_documents_metadata,
    build_retrieved_context_metadata,
)
from guardrails.retrieval import LowConfidenceGuard

logger = logging.getLogger(__name__)

# Module-level default builder with standard configuration.
#
# WHY A MODULE-LEVEL INSTANCE:
# LangGraph calls node functions on every graph invocation. Constructing a
# ContextBuilder inside the function on every call would be wasteful — the
# object is stateless between calls, all configuration is fixed at construction
# time. A module-level instance is constructed once at import time and reused.
#
# PRODUCTION NOTE: replace with config-driven values from app/config/ settings:
#   from app.config import settings
#   _DEFAULT_BUILDER = ContextBuilder(
#       max_context_chars=settings.context_max_chars,
#       min_relevance_score=settings.context_min_score,
#   )
_DEFAULT_BUILDER = ContextBuilder()

RETRIEVAL_FAILURE_CONTEXT_MESSAGE = (
    "Document retrieval could not be completed because a retrieval service failed."
)


def context_builder_node(
    state: Dict[str, Any],
    builder: Optional[ContextBuilder] = None,
) -> Dict[str, Any]:
    """LangGraph node function: transforms retrieved documents into bounded context.

    Reads state["documents"] — a List[RetrievedDocument] produced by the Retriever.
    Delegates all transformation to ContextBuilder.build_context().
    Returns {"retrieved_context": <RetrievedContext>} for the Response Node.

    WHY THIS FUNCTION IS AN ADAPTER (not a processor):
    LangGraph nodes receive the entire shared state dict. This function's only
    responsibility is to unpack state → call the real logic → repack the result.
    ContextBuilder is fully testable without LangGraph; this adapter only adds the
    LangGraph integration layer.

    Args:
        state: Shared LangGraph state dictionary.
        builder: Optional custom ContextBuilder instance. Uses the module-level
                 default if None. Inject a custom builder in tests.

    Returns:
        {"retrieved_context": RetrievedContext} — LangGraph merges this into state.
    """
    active_builder = builder or _DEFAULT_BUILDER

    # Read documents from state. The Retriever writes List[RetrievedDocument] here.
    raw_documents = state.get("documents")
    raw_retrieval_status = state.get("retrieval_status")
    retrieval_status = (
        raw_retrieval_status
        if isinstance(raw_retrieval_status, RetrievalStatus)
        else (
            RetrievalStatus.model_validate(raw_retrieval_status)
            if isinstance(raw_retrieval_status, dict)
            else None
        )
    )

    if retrieval_status is not None and retrieval_status.status == "failed":
        retrieved_context = RetrievedContext(
            formatted_context=RETRIEVAL_FAILURE_CONTEXT_MESSAGE,
            sources=[],
            total_documents_retrieved=0,
            documents_used=0,
            has_relevant_documents=False,
            truncated=False,
            fallback_applied=True,
            retrieval_status=retrieval_status.status,
        )
        existing_flags = dict(state.get("guardrail_flags") or {})
        existing_flags["retrieval_ungrounded"] = True
        existing_flags["retrieval_failed"] = True
        return {
            "retrieved_context": retrieved_context,
            "guardrail_flags": existing_flags,
        }

    doc_count = len(raw_documents) if isinstance(raw_documents, (list, tuple)) else 0
    logger.debug("context_builder_node: %d document(s) received from Retriever.", doc_count)

    # Delegate all transformation to ContextBuilder — normalization, dedup,
    # filter, sort, budget enforcement, formatting, and citation assembly.
    with start_observation(
        "context_builder",
        input=build_documents_metadata(raw_documents or []),
    ) as observation:
        retrieved_context: RetrievedContext = active_builder.build_context(raw_documents)
        if retrieval_status is not None:
            retrieved_context = retrieved_context.model_copy(
                update={"retrieval_status": retrieval_status.status}
            )
        observation.update(output=build_retrieved_context_metadata(retrieved_context))

    logger.info(
        "context_builder_node: complete — documents_used=%d, truncated=%s, "
        "has_relevant_documents=%s.",
        retrieved_context.documents_used,
        retrieved_context.truncated,
        retrieved_context.has_relevant_documents,
    )

    # --- Low Confidence Guard ---
    # Flags turns where no relevant documents were found so that monitoring
    # systems can track ungrounded responses. Does NOT modify retrieved_context.
    _lc_guard = LowConfidenceGuard()
    lc_result = _lc_guard.check(retrieved_context)
    existing_flags = dict(state.get("guardrail_flags") or {})
    existing_flags["retrieval_ungrounded"] = not lc_result.is_grounded
    # --- End Low Confidence Guard ---

    return {
        "retrieved_context": retrieved_context,
        "guardrail_flags": existing_flags,
    }
