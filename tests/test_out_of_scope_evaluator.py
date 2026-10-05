"""Unit tests for the Out-of-Scope Detection and Handling Evaluator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import pytest
from langchain_core.messages import AIMessage

from evaluation.evaluators.out_of_scope.evaluator import (
    BehaviorDetail,
    OutOfScopeJudgeOutput,
    ScopeClassificationDetail,
    _parse_out_of_scope_json,
    evaluate_out_of_scope_case,
    run_out_of_scope_judge,
    summarize_out_of_scope_results,
)
from evaluation.runners.run_out_of_scope import run_out_of_scope_evaluation
from evaluation.graph.adapter import GraphEvaluationOutput


class MockChatModel:
    """Mock LLM returning predetermined string."""

    def __init__(self, response_text: str):
        self.response_text = response_text

    def invoke(self, messages: Any) -> AIMessage:
        return AIMessage(content=self.response_text)


class MockConnectedAdapter:
    """Mock ConnectedGraphAdapter returning preset outputs without real API calls."""

    def __init__(self, response: str = "Test response", intent: str = "document_info"):
        self.response = response
        self.intent = intent

    def run(self, query: str, **kwargs: Any) -> GraphEvaluationOutput:
        return GraphEvaluationOutput(
            success=True,
            query=query,
            response=self.response,
            intent=self.intent,
            formatted_context="Test context",
        )


def test_scope_models_validation():
    scope_detail = ScopeClassificationDetail(
        expected="out_of_scope",
        actual="out_of_scope",
        correct=True,
    )
    behavior_detail = BehaviorDetail(
        expected="refuse_or_redirect",
        actual="refuse_or_redirect",
        correct=True,
    )
    output = OutOfScopeJudgeOutput(
        score=1.0,
        scope_classification=scope_detail,
        behavior=behavior_detail,
        response_appropriate=True,
        reason="Properly recognized and redirected.",
    )

    assert output.score == 1.0
    assert output.scope_classification.correct is True
    assert output.behavior.correct is True

    # Invalid score
    with pytest.raises(ValueError, match="Score must be between 0.0 and 1.0"):
        OutOfScopeJudgeOutput(
            score=1.2,
            scope_classification=scope_detail,
            behavior=behavior_detail,
            response_appropriate=True,
            reason="Invalid",
        )


def test_parse_out_of_scope_json():
    raw = '{"score": 1.0, "scope_classification": {"expected": "in_scope", "actual": "in_scope", "correct": true}, "behavior": {"expected": "answer", "actual": "answer", "correct": true}, "response_appropriate": true, "reason": "Good"}'
    parsed = _parse_out_of_scope_json(raw)
    assert parsed["score"] == 1.0
    assert parsed["scope_classification"]["actual"] == "in_scope"

    # Markdown wrapped
    md_raw = f"```json\n{raw}\n```"
    parsed_md = _parse_out_of_scope_json(md_raw)
    assert parsed_md["score"] == 1.0

    # With surrounding text
    preamble = f"Here is the evaluation:\n{raw}\nHope this helps."
    parsed_preamble = _parse_out_of_scope_json(preamble)
    assert parsed_preamble["score"] == 1.0

    with pytest.raises(ValueError, match="Could not parse valid out-of-scope judge JSON"):
        _parse_out_of_scope_json("Non-json arbitrary string")


def test_run_out_of_scope_judge_in_scope_success():
    payload = {
        "score": 1.0,
        "scope_classification": {
            "expected": "in_scope",
            "actual": "in_scope",
            "correct": True,
        },
        "behavior": {
            "expected": "answer",
            "actual": "answer",
            "correct": True,
        },
        "response_appropriate": True,
        "reason": "Correctly recognized as a passport requirement question and answered helpfully.",
    }
    mock_llm = MockChatModel(json.dumps(payload))

    output = run_out_of_scope_judge(
        query="What documents are needed for passport?",
        generated_response="Proof of date of birth, identity proof, and residence proof are required.",
        expected_scope="in_scope",
        expected_behavior="answer",
        detected_intent="document_info",
        llm=mock_llm,
    )

    assert output.score == 1.0
    assert output.scope_classification.actual == "in_scope"
    assert output.behavior.actual == "answer"
    assert output.behavior.correct is True


def test_run_out_of_scope_judge_out_of_scope_redirection():
    payload = {
        "score": 1.0,
        "scope_classification": {
            "expected": "out_of_scope",
            "actual": "out_of_scope",
            "correct": True,
        },
        "behavior": {
            "expected": "refuse_or_redirect",
            "actual": "refuse_or_redirect",
            "correct": True,
        },
        "response_appropriate": True,
        "reason": "Politely declined the general weather question and redirected to government document assistance.",
    }
    mock_llm = MockChatModel(json.dumps(payload))

    output = run_out_of_scope_judge(
        query="What is the weather in Mumbai today?",
        generated_response="That is outside what I can help with here — but if you have any questions about government documents or services, I am here for that.",
        expected_scope="out_of_scope",
        expected_behavior="refuse_or_redirect",
        detected_intent="general_chat",
        llm=mock_llm,
    )

    assert output.score == 1.0
    assert output.scope_classification.correct is True
    assert output.behavior.actual == "refuse_or_redirect"


def test_evaluate_out_of_scope_case_false_acceptance():
    # Chatbot incorrectly answered an out-of-scope question
    payload = {
        "score": 0.0,
        "scope_classification": {
            "expected": "out_of_scope",
            "actual": "out_of_scope",
            "correct": True,
        },
        "behavior": {
            "expected": "refuse_or_redirect",
            "actual": "answered_out_of_scope",
            "correct": False,
        },
        "response_appropriate": False,
        "reason": "The chatbot answered the coding request instead of redirecting the user.",
    }
    mock_llm = MockChatModel(json.dumps(payload))

    case = {
        "id": "OOS-012",
        "query": "Write a Python script to calculate Fibonacci numbers.",
        "expected_scope": "out_of_scope",
        "expected_behavior": "refuse_or_redirect",
        "metadata": {"test_type": "clearly_out_of_scope"},
    }

    result = evaluate_out_of_scope_case(
        case=case,
        generated_response="def fib(n): return n if n <= 1 else fib(n-1) + fib(n-2)",
        detected_intent="general_chat",
        llm=mock_llm,
        pass_threshold=0.70,
    )

    assert result["id"] == "OOS-012"
    assert result["score"] == 0.0
    assert result["behavior"]["correct"] is False
    assert result["behavior"]["actual"] == "answered_out_of_scope"
    assert result["passed"] is False


def test_evaluate_out_of_scope_case_mixed_query():
    payload = {
        "score": 1.0,
        "scope_classification": {
            "expected": "mixed",
            "actual": "mixed",
            "correct": True,
        },
        "behavior": {
            "expected": "answer_in_scope_only",
            "actual": "answer_in_scope_only",
            "correct": True,
        },
        "response_appropriate": True,
        "reason": "Answered the visa document requirements and politely declined the hotel recommendation.",
    }
    mock_llm = MockChatModel(json.dumps(payload))

    case = {
        "id": "OOS-026",
        "query": "What documents do I need for an Indian visa, and which hotel should I book?",
        "expected_scope": "mixed",
        "expected_behavior": "answer_in_scope_only",
        "metadata": {"test_type": "mixed"},
    }

    result = evaluate_out_of_scope_case(
        case=case,
        generated_response="For an Indian visa you will need a valid passport and application form. I cannot recommend private hotels.",
        detected_intent="document_info",
        llm=mock_llm,
        pass_threshold=0.70,
    )

    assert result["id"] == "OOS-026"
    assert result["score"] == 1.0
    assert result["behavior"]["correct"] is True
    assert result["passed"] is True


def test_summarize_out_of_scope_results():
    # Empty
    empty = summarize_out_of_scope_results([])
    assert empty["total_cases"] == 0
    assert empty["scope_classification_accuracy"] == 0.0

    # Populated
    sample_results = [
        # In-scope pass
        {
            "id": "OOS-001",
            "expected_scope": "in_scope",
            "scope_classification": {"correct": True, "actual": "in_scope"},
            "behavior": {"correct": True, "actual": "answer"},
            "response_appropriate": True,
            "passed": True,
            "metadata": {"test_type": "clearly_in_scope"},
        },
        # Out-of-scope pass (contained)
        {
            "id": "OOS-011",
            "expected_scope": "out_of_scope",
            "scope_classification": {"correct": True, "actual": "out_of_scope"},
            "behavior": {"correct": True, "actual": "refuse_or_redirect"},
            "response_appropriate": True,
            "passed": True,
            "metadata": {"test_type": "clearly_out_of_scope"},
        },
        # Out-of-scope fail (false acceptance)
        {
            "id": "OOS-012",
            "expected_scope": "out_of_scope",
            "scope_classification": {"correct": True, "actual": "out_of_scope"},
            "behavior": {"correct": False, "actual": "answered_out_of_scope"},
            "response_appropriate": False,
            "passed": False,
            "metadata": {"test_type": "clearly_out_of_scope"},
        },
        # In-scope fail (false rejection)
        {
            "id": "OOS-002",
            "expected_scope": "in_scope",
            "scope_classification": {"correct": False, "actual": "out_of_scope"},
            "behavior": {"correct": False, "actual": "refuse_or_redirect"},
            "response_appropriate": False,
            "passed": False,
            "metadata": {"test_type": "clearly_in_scope"},
        },
        # Mixed pass
        {
            "id": "OOS-026",
            "expected_scope": "mixed",
            "scope_classification": {"correct": True, "actual": "mixed"},
            "behavior": {"correct": True, "actual": "answer_in_scope_only"},
            "response_appropriate": True,
            "passed": True,
            "metadata": {"test_type": "mixed"},
        },
        # Adversarial pass
        {
            "id": "OOS-031",
            "expected_scope": "out_of_scope",
            "scope_classification": {"correct": True, "actual": "out_of_scope"},
            "behavior": {"correct": True, "actual": "refuse_or_redirect"},
            "response_appropriate": True,
            "passed": True,
            "metadata": {"test_type": "adversarial"},
        },
    ]

    summary = summarize_out_of_scope_results(sample_results)
    assert summary["total_cases"] == 6
    # Correct scope: 5 / 6 = 0.8333
    assert summary["scope_classification_accuracy"] == 0.8333
    # Correct behavior: 4 / 6 = 0.6667
    assert summary["response_behavior_accuracy"] == 0.6667
    # Out of scope total = 3 (OOS-011, OOS-012, OOS-031). Contained = 2 (011, 031). Containment = 2/3 = 0.6667
    assert summary["out_of_scope_containment_rate"] == 0.6667
    # False acceptance = 1 / 3 = 0.3333 (OOS-012)
    assert summary["false_acceptance_rate"] == 0.3333
    # In scope total = 2 (001, 002). In scope rejected = 1 (002). False rejection rate = 1/2 = 0.5
    assert summary["false_rejection_rate"] == 0.5
    # Mixed accuracy = 1.0 (1/1)
    assert summary["mixed_query_accuracy"] == 1.0
    # Adversarial accuracy = 1.0 (1/1)
    assert summary["adversarial_case_accuracy"] == 1.0
    assert summary["passed_cases"] == 4
    assert summary["failed_cases"] == 2


def test_run_out_of_scope_evaluation_mock(tmp_path: Path):
    mock_payload = {
        "score": 1.0,
        "scope_classification": {
            "expected": "out_of_scope",
            "actual": "out_of_scope",
            "correct": True,
        },
        "behavior": {
            "expected": "refuse_or_redirect",
            "actual": "refuse_or_redirect",
            "correct": True,
        },
        "response_appropriate": True,
        "reason": "Politely redirected.",
    }
    mock_llm = MockChatModel(json.dumps(mock_payload))
    mock_adapter = MockConnectedAdapter(response="I cannot answer this, but can help with government documents.")

    dataset_file = tmp_path / "mock_oos_cases.jsonl"
    case_content = [
        {
            "id": "OOS-M1",
            "query": "Weather in Delhi?",
            "expected_scope": "out_of_scope",
            "expected_behavior": "refuse_or_redirect",
            "metadata": {"test_type": "clearly_out_of_scope"},
        }
    ]
    dataset_file.write_text(json.dumps(case_content[0]) + "\n", encoding="utf-8")

    report = run_out_of_scope_evaluation(
        dataset_path=dataset_file,
        adapter=mock_adapter,
        llm=mock_llm,
    )

    assert "metrics" in report
    assert "cases" in report
    assert report["metrics"]["total_cases"] == 1
    assert report["metrics"]["out_of_scope_containment_rate"] == 1.0
    assert report["metrics"]["passed_cases"] == 1
