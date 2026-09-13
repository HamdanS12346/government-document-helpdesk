"""Context Builder package for the Government Document Helpdesk.

Constructs bounded, formatted, and source-attributed context from retrieved
documents for the Response Node in LangGraph.
"""

from app.contracts.retrieval import (
    ChunkMetadata,
    RetrievedDocument,
    RetrievalOutput,
)
from app.contracts.response import (
    ContextSource,
    RetrievedContext,
)
from app.rag.context_builder.builder import (
    ContextBuilder,
    normalize_retrieved_documents,
)
from app.rag.context_builder.formatter import DocumentFormatter
from app.rag.context_builder.node import context_builder_node

__all__ = [
    "ContextBuilder",
    "DocumentFormatter",
    "context_builder_node",
    "normalize_retrieved_documents",
    "ChunkMetadata",
    "RetrievedDocument",
    "RetrievalOutput",
    "ContextSource",
    "RetrievedContext",
]
