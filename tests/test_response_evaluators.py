"""Unit tests for the Response Evaluators suite."""

import pytest
from unittest.mock import MagicMock
from langchain_core.messages import AIMessage

from evaluation.evaluators.response.llm_judge import (
    JudgeEvaluationError,
    JudgeResult,
    format_context,
    format_expected_answer,
    run_llm_judge,
)
from evaluation.evaluators.response.correctness import evaluate_correctness
from evaluation.evaluators.response.faithfulness import evaluate_faithfulness
from evaluation.evaluators.response.relevance import evaluate_relevance
from evaluation.evaluators.response.completeness import evaluate_completeness
from evaluation.evaluators.response.citation import evaluate_citation
from evaluation.evaluators.response.safety import evaluate_safety
from evaluation.evaluators.response.evaluator import (
    evaluate_response_case,
    summarize_response_results,
)


class MockChatModel:
    """Mock LLM that returns a predetermined JSON string."""

    def __init__(self, response_text: str):
        self.response_text = response_text

    def invoke(self, messages):
        return AIMessage(content=self.response_text)


def test_judge_result_validation():
    # Valid score
    res = JudgeResult(score=0.85, reason="Valid reason")
    assert res.score == 0.85
    assert res.reason == "Valid reason"

    # Score below 0
    with pytest.raises(ValueError, match="Score must be between 0.0 and 1.0"):
        JudgeResult(score=-0.1, reason="Invalid")

    # Score above 1
    with pytest.raises(ValueError, match="Score must be between 0.0 and 1.0"):
        JudgeResult(score=1.2, reason="Invalid")


def test_format_helpers():
    # Context format
    ctx_list = [{"chunk_id": "c1", "text": "Hello world", "source_url": "https://gov.in"}]
    formatted = format_context(ctx_list)
    assert "[c1] (https://gov.in):" in formatted
    assert "Hello world" in formatted

    assert format_context(None) == "None provided"

    # Expected answer format
    exp_dict = {"key_points": ["Point A", "Point B"]}
    formatted_exp = format_expected_answer(exp_dict)
    assert "- Point A" in formatted_exp
    assert "- Point B" in formatted_exp


def test_run_llm_judge_json_parsing():
    # Plain JSON
    mock_llm = MockChatModel('{"score": 0.9, "reason": "Accurate response"}')
    result = run_llm_judge(
        criterion="correctness",
        query="What is passport?",
        generated_response="A passport is a travel document.",
        llm=mock_llm,
    )
    assert result.score == 0.9
    assert result.reason == "Accurate response"
    assert result.criterion == "correctness"

    # Markdown wrapped JSON
    mock_llm_md = MockChatModel('```json\n{"score": 0.7, "reason": "Mostly good"}\n```')
    result_md = run_llm_judge(
        criterion="relevance",
        query="What is passport?",
        generated_response="A passport is a travel document.",
        llm=mock_llm_md,
    )
    assert result_md.score == 0.7
    assert result_md.reason == "Mostly good"


def test_run_llm_judge_error_handling():
    # Invalid non-JSON output
    bad_llm = MockChatModel("I cannot evaluate this.")
    with pytest.raises(JudgeEvaluationError):
        run_llm_judge(
            criterion="safety",
            query="test",
            generated_response="test",
            llm=bad_llm,
        )


def test_individual_evaluators():
    mock_llm = MockChatModel('{"score": 0.85, "reason": "Satisfies criteria"}')

    res_corr = evaluate_correctness("q", "resp", "expected", llm=mock_llm)
    assert res_corr["criterion"] == "correctness"
    assert res_corr["score"] == 0.85

    res_faith = evaluate_faithfulness("q", "resp", "context", llm=mock_llm)
    assert res_faith["criterion"] == "faithfulness"
    assert res_faith["score"] == 0.85

    res_rel = evaluate_relevance("q", "resp", llm=mock_llm)
    assert res_rel["criterion"] == "relevance"
    assert res_rel["score"] == 0.85

    res_comp = evaluate_completeness("q", "resp", "expected", llm=mock_llm)
    assert res_comp["criterion"] == "completeness"
    assert res_comp["score"] == 0.85

    res_cit = evaluate_citation("q", "resp", ["http://cite"], llm=mock_llm)
    assert res_cit["criterion"] == "citation"
    assert res_cit["score"] == 0.85

    res_safe = evaluate_safety("q", "resp", llm=mock_llm)
    assert res_safe["criterion"] == "safety"
    assert res_safe["score"] == 0.85


def test_evaluate_response_case():
    mock_llm = MockChatModel('{"score": 0.8, "reason": "Good job"}')
    case = {
        "id": "RESP-001",
        "query": "What is the fee?",
        "context": [{"text": "Fee is 1500 INR"}],
        "expected_answer": {"key_points": ["Fee is 1500 INR"]},
        "expected_citations": ["https://passport.gov.in"],
    }

    result = evaluate_response_case(case, "The fee is 1500 INR.", llm=mock_llm)
    assert result["id"] == "RESP-001"
    assert result["average_score"] == 0.8
    assert result["passed"] is True
    assert set(result["scores"].keys()) == {
        "correctness",
        "faithfulness",
        "relevance",
        "completeness",
        "citation",
        "safety",
    }


def test_evaluate_response_case_fails_on_safety():
    # If safety score is below 0.6, the case must fail even if average is high
    def dynamic_invoke(messages):
        content = messages[0].content
        if "SAFETY" in content:
            return AIMessage(content='{"score": 0.2, "reason": "Unsafe advice"}')
        return AIMessage(content='{"score": 0.9, "reason": "Good"}')

    mock_llm = MagicMock()
    mock_llm.invoke = dynamic_invoke

    case = {"id": "RESP-002", "query": "q", "context": []}
    result = evaluate_response_case(case, "resp", llm=mock_llm)
    assert result["scores"]["safety"] == 0.2
    assert result["passed"] is False


def test_summarize_response_results():
    results = [
        {
            "id": "RESP-001",
            "passed": True,
            "average_score": 0.85,
            "scores": {
                "correctness": 0.9,
                "faithfulness": 0.8,
                "relevance": 0.9,
                "completeness": 0.8,
                "citation": 0.85,
                "safety": 1.0,
            },
        },
        {
            "id": "RESP-002",
            "passed": False,
            "average_score": 0.50,
            "scores": {
                "correctness": 0.5,
                "faithfulness": 0.6,
                "relevance": 0.7,
                "completeness": 0.4,
                "citation": 0.3,
                "safety": 0.5,
            },
        },
    ]

    summary = summarize_response_results(results)
    assert summary["total_cases"] == 2
    assert summary["passed_cases"] == 1
    assert summary["failed_cases"] == 1
    assert summary["pass_rate"] == 0.5
    assert summary["average_correctness"] == 0.7
    assert summary["average_faithfulness"] == 0.7
    assert summary["average_relevance"] == 0.8
    assert summary["average_completeness"] == 0.6
    assert summary["average_citation"] == 0.575
    assert summary["average_safety"] == 0.75
    assert summary["overall_score"] == 0.675
