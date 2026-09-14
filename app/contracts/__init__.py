"""Shared data contracts used across workflow nodes."""

from app.contracts.intent_decision import IntentDecision
from app.contracts.normalized_input import ImageContent, NormalizedInput, PDFContent
from app.contracts.response import ContextSource, RetrievedContext
from app.contracts.retrieval import ChunkMetadata, RetrievalOutput, RetrievedDocument

__all__ = [
    "ChunkMetadata",
    "ContextSource",
    "ImageContent",
    "IntentDecision",
    "NormalizedInput",
    "PDFContent",
    "RetrievalOutput",
    "RetrievedContext",
    "RetrievedDocument",
]
