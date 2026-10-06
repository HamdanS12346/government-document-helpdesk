"""Hallucination and Unsupported Information Evaluator package."""

from evaluation.evaluators.hallucination.evaluator import (
    DEFAULT_PASS_THRESHOLD,
    ClaimItem,
    HallucinationJudgeOutput,
    evaluate_hallucination_case,
    run_hallucination_judge,
    summarize_hallucination_results,
)

__all__ = [
    "DEFAULT_PASS_THRESHOLD",
    "ClaimItem",
    "HallucinationJudgeOutput",
    "evaluate_hallucination_case",
    "run_hallucination_judge",
    "summarize_hallucination_results",
]
