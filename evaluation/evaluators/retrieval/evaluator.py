from __future__ import annotations

import math
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
load_dotenv()

# Expected case format (as defined in retrieval_evaluation_plan.md)
# {
#   "id": "RET-001",
#   "query": "...",
#   "expected_chunks": ["chunk-id-1", "chunk-id-2", ...]
# }

def _reciprocal_rank(retrieved: List[str], relevant: List[str]) -> float:
    """Return the reciprocal rank for the first relevant chunk.
    If none of the relevant chunks are found, return 0.0.
    """
    for idx, chunk_id in enumerate(retrieved, start=1):
        if chunk_id in relevant:
            return 1.0 / idx
    return 0.0

def _dcg_at_k(retrieved: List[str], relevant: List[str], k: int) -> float:
    """Compute DCG@k with binary relevance (1 for relevant, 0 otherwise)."""
    dcg = 0.0
    for i, chunk_id in enumerate(retrieved[:k], start=1):
        rel = 1 if chunk_id in relevant else 0
        if i == 1:
            dcg += rel
        else:
            dcg += rel / math.log2(i + 0)
    return dcg

def _idcg_at_k(relevant: List[str], k: int) -> float:
    """Ideal DCG@k for binary relevance (all relevant items ranked first)."""
    ideal_hits = min(len(relevant), k)
    idcg = 0.0
    for i in range(1, ideal_hits + 1):
        if i == 1:
            idcg += 1
        else:
            idcg += 1 / math.log2(i + 0)
    return idcg

def evaluate_retrieval_case(
    case: Dict[str, Any],
    retrieved_chunks: List[str],
    *,
    dense_result_count: Optional[int] = None,
    lexical_result_count: Optional[int] = None,
) -> Dict[str, Any]:
    """Evaluate a single retrieval case.

    Returns a dictionary containing:
        - id
        - query
        - expected_chunks
        - retrieved_chunks
        - recall_at_5
        - precision_at_5
        - mrr
        - ndcg_at_5
        - dense_result_count (optional)
        - lexical_result_count (optional)
    """
    case_id = case.get("id")
    query = case.get("query")
    expected = case.get("expected_chunks", [])
    k = 5

    # Compute metrics
    retrieved_k = retrieved_chunks[:k]
    relevant_in_k = [c for c in retrieved_k if c in expected]

    recall_at_5 = len(relevant_in_k) / len(expected) if expected else 0.0
    precision_at_5 = len(relevant_in_k) / k
    mrr = _reciprocal_rank(retrieved_k, expected)
    ndcg_at_5 = (
        _dcg_at_k(retrieved_k, expected, k) / _idcg_at_k(expected, k)
        if _idcg_at_k(expected, k) > 0
        else 0.0
    )

    result: Dict[str, Any] = {
        "id": case_id,
        "query": query,
        "expected_chunks": expected,
        "retrieved_chunks": retrieved_chunks,
        "recall_at_5": round(recall_at_5, 4),
        "precision_at_5": round(precision_at_5, 4),
        "mrr": round(mrr, 4),
        "ndcg_at_5": round(ndcg_at_5, 4),
    }
    if dense_result_count is not None:
        result["dense_result_count"] = dense_result_count
    if lexical_result_count is not None:
        result["lexical_result_count"] = lexical_result_count

    return result

def summarize_retrieval_results(cases_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate metrics across all cases (simple average)."""
    if not cases_results:
        return {}
    total_cases = len(cases_results)
    agg: Dict[str, Any] = {
        "total_cases": total_cases,
        "average_recall_at_5": round(sum(r["recall_at_5"] for r in cases_results) / total_cases, 4),
        "average_precision_at_5": round(sum(r["precision_at_5"] for r in cases_results) / total_cases, 4),
        "average_mrr": round(sum(r["mrr"] for r in cases_results) / total_cases, 4),
        "average_ndcg_at_5": round(sum(r["ndcg_at_5"] for r in cases_results) / total_cases, 4),
    }
    if any("dense_result_count" in r for r in cases_results):
        agg["average_dense_result_count"] = round(
            sum(r.get("dense_result_count", 0) for r in cases_results) / total_cases, 2
        )
    if any("lexical_result_count" in r for r in cases_results):
        agg["average_lexical_result_count"] = round(
            sum(r.get("lexical_result_count", 0) for r in cases_results) / total_cases, 2
        )
    return agg
