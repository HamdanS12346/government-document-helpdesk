"""Shared data contracts used across workflow nodes."""

from app.contracts.intent_decision import IntentDecision
from app.contracts.normalized_input import ImageContent, NormalizedInput, PDFContent
from app.contracts.retrieval import ChunkMetadata, RetrievalOutput, RetrievedDocument

__all__ = [
    "ImageContent",
    "PDFContent",
    "NormalizedInput",
    "IntentDecision",
    "ChunkMetadata",
    "RetrievedDocument",
    "RetrievalOutput",
]
