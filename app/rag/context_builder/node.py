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
from app.contracts.response import RetrievedContext

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

    doc_count = len(raw_documents) if isinstance(raw_documents, (list, tuple)) else 0
    logger.debug("context_builder_node: %d document(s) received from Retriever.", doc_count)

    # Delegate all transformation to ContextBuilder — normalization, dedup,
    # filter, sort, budget enforcement, formatting, and citation assembly.
    retrieved_context: RetrievedContext = active_builder.build_context(raw_documents)

    logger.info(
        "context_builder_node: complete — documents_used=%d, truncated=%s, "
        "has_relevant_documents=%s.",
        retrieved_context.documents_used,
        retrieved_context.truncated,
        retrieved_context.has_relevant_documents,
    )

    return {"retrieved_context": retrieved_context}
