"""Citation quality evaluator for generated responses."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
from evaluation.evaluators.response.llm_judge import run_llm_judge

CITATION_INSTRUCTIONS = """
Evaluation Objective:
Determine whether citations are present, appropriate, accurate, and supported by the supplied sources and Expected Citations.

Questions to consider:
1. Does the response provide citations/source attributions when document evidence is used?
2. Do the cited sources or references accurately correspond to the claims being made?
3. Are the citations relevant to the answer?
4. Does the response cite incorrect or unrelated documents?
5. Does the response invent or fabricate non-existent citations/links?
6. Are expected citations/official portals referenced where expected?

Important Principle:
- Citation quality requires BOTH:
  (a) Citation Presence (attributing claims to official documents, portal URLs, or sources)
  (b) Citation Correctness (the cited source actually supports the specific claim made)
- A response that provides accurate, relevant citations aligning with the context and expected citations: score 0.9 - 1.0.
- A response that provides mostly correct citations with minor formatting or slight attribution mismatch: score 0.6 - 0.8.
- A response that makes factual claims without citing sources when evidence was available: score 0.3 - 0.5.
- A response that invents fake citations, cites completely wrong sources, or hallucinates URLs: score 0.0 - 0.2.
- Note: If no citations were expected (e.g. general chat or out-of-scope query), lack of citations is appropriate: score 1.0.
"""


def evaluate_citation(
    query: str,
    generated_response: str,
    context: Union[str, List[Dict[str, Any]], None] = None,
    expected_citations: Optional[List[str]] = None,
    llm: Optional[Any] = None,
) -> Dict[str, Any]:
    """Evaluate whether citations in the response are present, accurate, and grounded.

    Args:
        query: User query.
        generated_response: Generated chatbot response.
        context: Optional retrieved context chunks with source URLs.
        expected_citations: Ground truth list of expected URLs or document titles.
        llm: Injected chat model for testing.

    Returns:
        Dict with keys: criterion, score, reason.
    """
    result = run_llm_judge(
        criterion="citation",
        query=query,
        generated_response=generated_response,
        context=context,
        expected_citations=expected_citations,
        prompt_instructions=CITATION_INSTRUCTIONS,
        llm=llm,
    )
    return {
        "criterion": "citation",
        "score": result.score,
        "reason": result.reason,
    }


__all__ = ["CITATION_INSTRUCTIONS", "evaluate_citation"]
