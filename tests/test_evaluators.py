from evaluation.evaluators.input_processor.evaluator import (
    evaluate_input_case,
    summarize_input_results,
)
from evaluation.evaluators.intent.evaluator import (
    evaluate_intent_case,
    summarize_intent_results,
)


def test_input_metrics_keep_validity_and_modality_separate():
    cases = [
        {
            "id": "IP-001",
            "expected": {"valid": True, "modality": ["text"]},
        },
        {
            "id": "IP-002",
            "expected": {"valid": False, "modality": []},
        },
    ]

    results = [
        evaluate_input_case(cases[0], actual_valid=True, actual_modality=["text"]),
        evaluate_input_case(cases[1], actual_valid=True, actual_modality=["text"]),
    ]

    assert summarize_input_results(results) == {
        "total_cases": 2,
        "valid_accuracy": 0.5,
        "modality_accuracy": 0.5,
        "passed_cases": 1,
        "failed_cases": 1,
    }


def test_intent_metrics_include_per_class_scores_and_confusion_matrix():
    cases = [
        {"id": "INT-001", "input": "passport", "expected_intent": "ambiguous"},
        {"id": "INT-002", "input": "hello", "expected_intent": "general_chat"},
        {
            "id": "INT-003",
            "input": "passport fee",
            "expected_intent": "document_info",
        },
    ]
    results = [
        evaluate_intent_case(cases[0], "ambiguous"),
        evaluate_intent_case(cases[1], "general_chat"),
        evaluate_intent_case(cases[2], "ambiguous"),
    ]

    summary = summarize_intent_results(results)

    assert summary["total_cases"] == 3
    assert summary["accuracy"] == 2 / 3
    assert summary["confusion_matrix"]["document_info"]["ambiguous"] == 1
    assert summary["per_class"]["ambiguous"]["support"] == 1
