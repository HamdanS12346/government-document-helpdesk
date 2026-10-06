"""Out-of-Scope Detection Evaluation Package."""

from evaluation.evaluators.out_of_scope.evaluator import (
    DEFAULT_PASS_THRESHOLD,
    BehaviorDetail,
    OutOfScopeJudgeOutput,
    ScopeClassificationDetail,
    evaluate_out_of_scope_case,
    run_out_of_scope_judge,
    summarize_out_of_scope_results,
)

__all__ = [
    "DEFAULT_PASS_THRESHOLD",
    "BehaviorDetail",
    "OutOfScopeJudgeOutput",
    "ScopeClassificationDetail",
    "evaluate_out_of_scope_case",
    "run_out_of_scope_judge",
    "summarize_out_of_scope_results",
]
