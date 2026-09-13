"""Reciprocal Rank Fusion (RRF) algorithm for hybrid search consolidation."""

from typing import Dict, List
from app.contracts.retrieval import RetrievedDocument


def reciprocal_rank_fusion(
    dense_results: List[RetrievedDocument],
    lexical_results: List[RetrievedDocument],
    k: int = 60,
    top_n: int = 25,
) -> List[RetrievedDocument]:
    """Fuse dense and lexical retrieved documents using Reciprocal Rank Fusion (RRF).

    Formula:
        RRF_Score(doc) = sum_{m in {dense, lexical}} (1 / (k + rank_m(doc)))

    Args:
        dense_results: Ordered list of documents retrieved via semantic search.
        lexical_results: Ordered list of documents retrieved via BM25 lexical search.
        k: Smoothing constant, standard is 60.
        top_n: Maximum number of fused documents to return.

    Returns:
        List of unique RetrievedDocument objects sorted by descending RRF score.
    """
    rrf_scores: Dict[str, float] = {}
    doc_lookup: Dict[str, RetrievedDocument] = {}

    # Process dense results
    for rank, doc in enumerate(dense_results, start=1):
        rrf_scores[doc.id] = rrf_scores.get(doc.id, 0.0) + (1.0 / (k + rank))
        if doc.id not in doc_lookup:
            doc_lookup[doc.id] = doc

    # Process lexical results
    for rank, doc in enumerate(lexical_results, start=1):
        rrf_scores[doc.id] = rrf_scores.get(doc.id, 0.0) + (1.0 / (k + rank))
        if doc.id not in doc_lookup:
            doc_lookup[doc.id] = doc

    # Sort documents descending by RRF score
    sorted_doc_ids = sorted(rrf_scores.keys(), key=lambda doc_id: rrf_scores[doc_id], reverse=True)

    fused_documents: List[RetrievedDocument] = []
    for doc_id in sorted_doc_ids[:top_n]:
        base_doc = doc_lookup[doc_id]
        fused_score = rrf_scores[doc_id]
        fused_documents.append(base_doc.model_copy(update={"score": fused_score}))

    return fused_documents


__all__ = ["reciprocal_rank_fusion"]
