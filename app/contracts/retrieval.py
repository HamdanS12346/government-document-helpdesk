"""Retrieval contract definitions."""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class ChunkMetadata(BaseModel):
    """Metadata attributes associated with a document chunk."""

    model_config = ConfigDict(extra="allow")

    document_id: str = Field(description="Unique identifier for parent document")
    category: str = Field(description="Document category, e.g. 'income-documents'")
    document_name: str = Field(description="Official name or title of the document")
    source_url: Optional[str] = Field(default=None, description="Source URL or citation")
    source_type: Optional[str] = Field(default=None, description="Source format, e.g. 'webpage', 'pdf'")


class RetrievedDocument(BaseModel):
    """A single retrieved and reranked document chunk conforming to corpus schema."""

    id: str = Field(description="Unique chunk identifier (e.g. income-documents__...__chunk-0004)")
    text_content: str = Field(description="Textual content of the chunk")
    metadata: ChunkMetadata = Field(description="Document metadata")
    score: Optional[float] = Field(default=None, description="Relevance score from Cohere or RRF")

    @property
    def content(self) -> str:
        """Compatibility property for downstream nodes expecting .content."""
        return self.text_content

    @property
    def source(self) -> Optional[str]:
        """Convenience property extracting source_url or document_name."""
        return self.metadata.source_url or self.metadata.document_name


class RetrievalOutput(BaseModel):
    """Diagnostic container for retriever node results."""

    original_query: str
    rewritten_query: str
    documents: List[RetrievedDocument]
    applied_fallback: bool = False


RetrievalStatusValue = Literal[
    "success",
    "no_documents_found",
    "partial_failure",
    "failed",
    "blocked_by_guardrail",
]


class RetrievalError(BaseModel):
    """Safe diagnostic for a retrieval component failure."""

    component: str = Field(description="Retrieval component that failed")
    code: str = Field(description="Stable machine-readable error code")
    message: str = Field(description="Safe non-secret error summary")


class RetrievalStatus(BaseModel):
    """Outcome summary distinguishing clean no-match results from service failures."""

    status: RetrievalStatusValue = Field(description="Overall retrieval outcome")
    errors: List[RetrievalError] = Field(default_factory=list)
    dense_result_count: int = 0
    lexical_result_count: int = 0
    final_document_count: int = 0
    no_documents_found: bool = False


__all__ = [
    "ChunkMetadata",
    "RetrievedDocument",
    "RetrievalError",
    "RetrievalOutput",
    "RetrievalStatus",
    "RetrievalStatusValue",
]
