"""Cohere Cross-Encoder Reranker with Resilient Circuit Breaker Fallback."""

import logging
import os
from typing import Any, List, Optional, Tuple
from app.contracts.retrieval import RetrievedDocument

logger = logging.getLogger(__name__)


class CohereReranker:
    """Reranks candidate document chunks using Cohere cross-encoder models."""

    applies_relevance_threshold = True

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "rerank-v3.5",
        client: Optional[Any] = None,
    ):
        self.api_key = api_key or os.getenv("COHERE_API_KEY")
        self.model = model
        self._client = client

    def _get_client(self) -> Optional[Any]:
        if self._client is not None:
            return self._client
        if not self.api_key:
            return None
        try:
            import cohere
            self._client = cohere.ClientV2(api_key=self.api_key)
            return self._client
        except Exception as exc:
            logger.warning("Failed to initialize Cohere client: %s", exc)
            return None

    def rerank(
        self,
        query: str,
        documents: List[RetrievedDocument],
        top_n: int = 5,
    ) -> Tuple[List[RetrievedDocument], bool]:
        """Rerank candidate documents against query using Cohere.

        Args:
            query: The search query to score relevance against.
            documents: Candidate documents (typically sorted by RRF).
            top_n: Number of top documents to return.

        Returns:
            Tuple of (reranked_documents, applied_fallback).
        """
        if not documents:
            return [], False

        effective_top_n = min(top_n, len(documents))

        client = self._get_client()
        if client is None:
            logger.warning("Cohere API key not available; falling back to initial RRF ranking.")
            return documents[:effective_top_n], True

        try:
            doc_texts = [doc.text_content for doc in documents]
            
            # Support both ClientV2 and legacy Client interfaces
            if hasattr(client, "rerank"):
                response = client.rerank(
                    model=self.model,
                    query=query,
                    documents=doc_texts,
                    top_n=effective_top_n,
                )
            elif hasattr(client, "v2") and hasattr(client.v2, "rerank"):
                response = client.v2.rerank(
                    model=self.model,
                    query=query,
                    documents=doc_texts,
                    top_n=effective_top_n,
                )
            else:
                logger.warning("Unknown Cohere client interface; falling back to RRF ranking.")
                return documents[:effective_top_n], True

            reranked_docs: List[RetrievedDocument] = []
            for item in response.results:
                idx = item.index
                relevance_score = getattr(item, "relevance_score", 0.0)
                original_doc = documents[idx]
                reranked_docs.append(
                    original_doc.model_copy(update={"score": float(relevance_score)})
                )

            return reranked_docs, False

        except Exception as exc:
            logger.warning(
                "Cohere rerank failed with error: %s; falling back to RRF ranking.",
                exc,
            )
            return documents[:effective_top_n], True


__all__ = ["CohereReranker"]
