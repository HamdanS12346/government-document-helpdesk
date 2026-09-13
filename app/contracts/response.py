"""Shared response and context data contracts between Context Builder and Response Node.

Defines schemas for:
- ContextSource: Structured citation metadata for individual chunks.
- RetrievedContext: Prepared, bounded context ready for the Response Node.
"""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ContextSource(BaseModel):
    """Structured citation metadata for a document chunk included in retrieved context.

    Provided to the Response Node and Guardrails to support factual grounding,
    hallucination checks, and rendering source references to users.
    """
    model_config = ConfigDict(extra="allow")

    index: int = Field(description="1-based citation index corresponding to [Document X] in prompt")
    chunk_id: str = Field(description="Unique identifier of the cited chunk")
    document_name: Optional[str] = Field(default=None, description="Name or title of the source document")
    source_url: Optional[str] = Field(default=None, description="Source URL or reference link")
    score: Optional[float] = Field(default=None, description="Relevance score of this chunk")


class RetrievedContext(BaseModel):
    """Prepared, bounded context produced by Context Builder for the Response Node.

    Conforms to the shared state contract (state["retrieved_context"]) defined in:
    - docs/architecture/state-flow.md
    - docs/architecture/state.md
    """
    model_config = ConfigDict(extra="allow")

    formatted_context: str = Field(
        description="Clean, bounded context string formatted for LLM prompts with document citations"
    )
    sources: List[ContextSource] = Field(
        default_factory=list,
        description="List of structured citations matching the documents included in formatted_context"
    )
    total_documents_retrieved: int = Field(
        default=0,
        description="Total number of documents received from retrieval before filtering/bounding"
    )
    documents_used: int = Field(
        default=0,
        description="Number of documents included within the context budget"
    )
    has_relevant_documents: bool = Field(
        default=True,
        description="Flag indicating whether any relevant documents were successfully included"
    )
    truncated: bool = Field(
        default=False,
        description="True if one or more documents were omitted due to token/character budget limits"
    )
    fallback_applied: bool = Field(
        default=False,
        description="True if default fallback text was used because no relevant documents were found"
    )

    @property
    def text(self) -> str:
        """Convenience property returning the formatted text for prompt templates."""
        return self.formatted_context

    def __str__(self) -> str:
        """String representation returns the formatted context text."""
        return self.formatted_context
