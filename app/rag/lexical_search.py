"""BM25 Lexical search engine for government document chunks."""

import re
from typing import List, Optional
from rank_bm25 import BM25Okapi
from app.contracts.retrieval import RetrievedDocument


class BM25LexicalSearcher:
    """In-memory BM25 index over RetrievedDocument corpus chunks."""

    def __init__(self, documents: Optional[List[RetrievedDocument]] = None):
        self._documents: List[RetrievedDocument] = []
        self._bm25: Optional[BM25Okapi] = None
        if documents:
            self.index(documents)

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Lowercase alphanumeric whitespace tokenization."""
        return re.findall(r"\w+", text.lower())

    def index(self, documents: List[RetrievedDocument]) -> None:
        """Build or replace BM25 index with provided documents."""
        self._documents = list(documents)
        tokenized_corpus = [
            self._tokenize(doc.text_content) for doc in self._documents
        ]
        if tokenized_corpus and any(tokenized_corpus):
            self._bm25 = BM25Okapi(tokenized_corpus)
        else:
            self._bm25 = None

    def search(
        self,
        query: str,
        top_k: int = 25,
        filter_criteria: Optional[dict] = None,
    ) -> List[RetrievedDocument]:
        """Search documents using BM25 scoring and return top_k candidates with optional metadata filtering."""
        if not self._bm25 or not self._documents:
            return []

        tokenized_query = self._tokenize(query)
        if not tokenized_query:
            return []

        scores = self._bm25.get_scores(tokenized_query)

        # Pair documents with scores
        scored_docs = []
        filtered_docs = []
        for doc, score in zip(self._documents, scores):
            if score > 0.0:
                doc_copy = doc.model_copy(update={"score": float(score)})
                scored_docs.append(doc_copy)
                if self._matches_filter(doc_copy, filter_criteria):
                    filtered_docs.append(doc_copy)

        # If filter was provided and produced results, use them; otherwise fall back to all scored documents
        active_pool = filtered_docs if (filter_criteria and filtered_docs) else scored_docs

        # Sort descending by BM25 score
        active_pool.sort(key=lambda d: d.score or 0.0, reverse=True)
        return active_pool[:top_k]

    @staticmethod
    def _matches_filter(doc: RetrievedDocument, filter_criteria: Optional[dict]) -> bool:
        if not filter_criteria:
            return True
        meta = doc.metadata.model_dump()
        return all(meta.get(k) == v for k, v in filter_criteria.items())


__all__ = ["BM25LexicalSearcher"]
