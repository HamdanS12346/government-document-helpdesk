"""Unit tests for the Hallucination and Unsupported Information Evaluator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List
import pytest
from langchain_core.messages import AIMessage

from evaluation.evaluators.hallucination.evaluator import (
    ClaimItem,
    HallucinationJudgeOutput,
    _parse_hallucination_json,
    evaluate_hallucination_case,
    run_hallucination_judge,
    summarize_hallucination_results,
)
from evaluation.runners.run_hallucination import run_hallucination_evaluation
from evaluation.graph.adapter import GraphEvaluationOutput


class MockChatModel:
    """Mock LLM returning predetermined text."""

    def __init__(self, response_text: str):
        self.response_text = response_text

    def invoke(self, messages: Any) -> AIMessage:
        return AIMessage(content=self.response_text)


class MockConnectedAdapter:
    """Mock ConnectedGraphAdapter that returns preset outputs without real LLM/RAG calls."""

    def __init__(self, response: str = "Test response", context: str = "Test context"):
        self.response = response
        self.context = context

    def run(self, query: str, **kwargs: Any) -> GraphEvaluationOutput:
        return GraphEvaluationOutput(
            success=True,
            query=query,
            response=self.response,
            formatted_context=self.context,
            retrieved_chunk_ids=["chunk-001"],
            citations=["https://passportindia.gov.in"],
        )


def test_claim_item_creation():
    item = ClaimItem(
        claim="An Indian passport is required for international travel.",
        supported=True,
        evidence="Passport Act 1967 requires travel document",
    )
    assert item.claim == "An Indian passport is required for international travel."
    assert item.supported is True
    assert item.evidence == "Passport Act 1967 requires travel document"


def test_hallucination_judge_output_validation():
    # Valid output
    output = HallucinationJudgeOutput(
        score=0.85,
        hallucination_detected=False,
        claims=[
            ClaimItem(claim="Claim A", supported=True, evidence="Evidence"),
        ],
        unsupported_claims=0,
        unsupported_information_handling=1.0,
        reason="Fully supported by context.",
    )
    assert output.score == 0.85
    assert not output.hallucination_detected
    assert len(output.claims) == 1

    # Score out of bounds
    with pytest.raises(ValueError, match="Score must be between 0.0 and 1.0"):
        HallucinationJudgeOutput(
            score=1.5,
            hallucination_detected=False,
            reason="Invalid",
        )

    with pytest.raises(ValueError, match="Score must be between 0.0 and 1.0"):
        HallucinationJudgeOutput(
            score=-0.1,
            hallucination_detected=False,
            reason="Invalid",
        )


def test_parse_hallucination_json():
    # Plain JSON
    raw = '{"score": 1.0, "hallucination_detected": false, "claims": [], "unsupported_claims": 0, "unsupported_information_handling": 1.0, "reason": "Good"}'
    parsed = _parse_hallucination_json(raw)
    assert parsed["score"] == 1.0
    assert parsed["hallucination_detected"] is False

    # Markdown wrapped
    md_raw = '```json\n{"score": 0.5, "hallucination_detected": true, "claims": [], "unsupported_claims": 1, "unsupported_information_handling": 0.5, "reason": "Partial"}\n```'
    parsed_md = _parse_hallucination_json(md_raw)
    assert parsed_md["score"] == 0.5
    assert parsed_md["hallucination_detected"] is True

    # Preamble text with embedded json
    preamble = 'Here is the evaluation:\n{"score": 0.0, "hallucination_detected": true, "claims": [], "unsupported_claims": 2, "unsupported_information_handling": 0.0, "reason": "Failed"}\nHope this helps.'
    parsed_preamble = _parse_hallucination_json(preamble)
    assert parsed_preamble["score"] == 0.0

    # Malformed text
    with pytest.raises(ValueError, match="Could not parse valid hallucination judge JSON"):
        _parse_hallucination_json("This is purely arbitrary text with no json at all.")


def test_run_hallucination_judge_fully_supported():
    mock_payload = {
        "score": 1.0,
        "hallucination_detected": False,
        "claims": [
            {
                "claim": "An Indian passport facilitates international travel.",
                "supported": True,
                "evidence": "Under Passports Act 1967, passports facilitate travel.",
            },
            {
                "claim": "Proof of date of birth is required.",
                "supported": True,
                "evidence": "Supporting documents include Proof of Date of Birth.",
            },
        ],
        "unsupported_claims": 0,
        "unsupported_information_handling": 1.0,
        "reason": "All factual claims are fully supported by the retrieved context.",
    }
    mock_llm = MockChatModel(json.dumps(mock_payload))

    output = run_hallucination_judge(
        query="What documents are needed for passport?",
        generated_response="Proof of date of birth is needed, and passport facilitates travel.",
        retrieved_context="Under Passports Act 1967, passports facilitate travel. Supporting documents include Proof of Date of Birth.",
        expected_behavior="supported",
        llm=mock_llm,
    )

    assert output.score == 1.0
    assert output.hallucination_detected is False
    assert len(output.claims) == 2
    assert output.unsupported_claims == 0
    assert output.unsupported_information_handling == 1.0


def test_run_hallucination_judge_unsupported_claim():
    mock_payload = {
        "score": 0.5,
        "hallucination_detected": True,
        "claims": [
            {
                "claim": "An Indian passport is valid for international travel.",
                "supported": True,
                "evidence": "Retrieved context chunk 1",
            },
            {
                "claim": "The passport application fee is ₹1,500.",
                "supported": False,
                "evidence": None,
            },
        ],
        "unsupported_claims": 1,
        "unsupported_information_handling": 0.5,
        "reason": "The response fabricated a fee amount not present in the retrieved context.",
    }
    mock_llm = MockChatModel(json.dumps(mock_payload))

    output = run_hallucination_judge(
        query="What is the passport fee?",
        generated_response="The passport application fee is ₹1,500 and is valid for travel.",
        retrieved_context="An Indian passport is valid for international travel.",
        expected_behavior="should_not_guess",
        llm=mock_llm,
    )

    assert output.score == 0.5
    assert output.hallucination_detected is True
    assert output.unsupported_claims == 1
    assert output.claims[1].supported is False
    assert output.claims[1].evidence is None


def test_evaluate_hallucination_case_uncertainty_handling():
    # Chatbot properly acknowledges that information is unavailable
    mock_payload = {
        "score": 1.0,
        "hallucination_detected": False,
        "claims": [],
        "unsupported_claims": 0,
        "unsupported_information_handling": 1.0,
        "reason": "The chatbot appropriately stated that the processing time is not specified in the available information without guessing.",
    }
    mock_llm = MockChatModel(json.dumps(mock_payload))

    case = {
        "id": "HAL-011",
        "query": "What is the passport processing time?",
        "expected_behavior": "should_not_guess",
        "metadata": {"test_type": "partially_supported"},
    }

    result = evaluate_hallucination_case(
        case=case,
        generated_response="The available government documentation does not specify the exact processing time.",
        retrieved_context="General passport eligibility information.",
        llm=mock_llm,
        pass_threshold=0.70,
    )

    assert result["id"] == "HAL-011"
    assert result["score"] == 1.0
    assert result["hallucination_detected"] is False
    assert result["unsupported_information_handling"] == 1.0
    assert result["passed"] is True


def test_evaluate_hallucination_case_failure():
    mock_payload = {
        "score": 0.0,
        "hallucination_detected": True,
        "claims": [
            {
                "claim": "Senior citizens receive a 50% discount on passport fees.",
                "supported": False,
                "evidence": None,
            }
        ],
        "unsupported_claims": 1,
        "unsupported_information_handling": 0.0,
        "reason": "Accepted the false premise and invented a senior citizen discount.",
    }
    mock_llm = MockChatModel(json.dumps(mock_payload))

    case = {
        "id": "HAL-021",
        "query": "What is the 50% discount available to senior citizens?",
        "expected_behavior": "challenge_premise",
        "metadata": {"test_type": "false_premise"},
    }

    result = evaluate_hallucination_case(
        case=case,
        generated_response="Senior citizens receive a 50% discount on all passport applications.",
        retrieved_context="Passport application requirements without fee discount information.",
        llm=mock_llm,
        pass_threshold=0.70,
    )

    assert result["id"] == "HAL-021"
    assert result["score"] == 0.0
    assert result["hallucination_detected"] is True
    assert result["passed"] is False


def test_summarize_hallucination_results():
    # Empty results
    empty_summary = summarize_hallucination_results([])
    assert empty_summary["total_cases"] == 0
    assert empty_summary["average_hallucination_score"] == 0.0

    # Populated results
    sample_results = [
        {
            "id": "HAL-001",
            "score": 1.0,
            "hallucination_detected": False,
            "total_claims": 2,
            "unsupported_claims": 0,
            "unsupported_information_handling": 1.0,
            "passed": True,
        },
        {
            "id": "HAL-002",
            "score": 0.5,
            "hallucination_detected": True,
            "total_claims": 2,
            "unsupported_claims": 1,
            "unsupported_information_handling": 0.5,
            "passed": False,
        },
        {
            "id": "HAL-003",
            "score": 1.0,
            "hallucination_detected": False,
            "total_claims": 1,
            "unsupported_claims": 0,
            "unsupported_information_handling": 1.0,
            "passed": True,
        },
    ]

    summary = summarize_hallucination_results(sample_results)
    assert summary["total_cases"] == 3
    # Average score: (1.0 + 0.5 + 1.0) / 3 = 0.8333
    assert summary["average_hallucination_score"] == 0.8333
    # Hallucination rate: 1 / 3 = 0.3333
    assert summary["hallucination_rate"] == 0.3333
    # Unsupported claim rate: 1 / 5 = 0.2
    assert summary["unsupported_claim_rate"] == 0.2
    # Handling: (1.0 + 0.5 + 1.0) / 3 = 0.8333
    assert summary["unsupported_information_handling"] == 0.8333
    assert summary["cases_with_hallucinations"] == 1
    assert summary["cases_correctly_handling_missing_information"] == 2
    assert summary["passed_cases"] == 2
    assert summary["failed_cases"] == 1


def test_run_hallucination_evaluation_with_mock_adapter(tmp_path: Path):
    mock_payload = {
        "score": 1.0,
        "hallucination_detected": False,
        "claims": [
            {
                "claim": "Test claim",
                "supported": True,
                "evidence": "Test context snippet",
            }
        ],
        "unsupported_claims": 0,
        "unsupported_information_handling": 1.0,
        "reason": "Claim is supported.",
    }
    mock_llm = MockChatModel(json.dumps(mock_payload))
    mock_adapter = MockConnectedAdapter(response="Test response", context="Test context")

    dataset_file = tmp_path / "mock_cases.jsonl"
    case_content = [
        {"id": "HAL-M1", "query": "Query 1", "expected_behavior": "supported", "metadata": {"test_type": "fully_supported"}},
        {"id": "HAL-M2", "query": "Query 2", "expected_behavior": "supported", "metadata": {"test_type": "fully_supported"}},
    ]
    dataset_file.write_text("\n".join(json.dumps(c) for c in case_content) + "\n", encoding="utf-8")

    report = run_hallucination_evaluation(
        dataset_path=dataset_file,
        adapter=mock_adapter,
        llm=mock_llm,
    )

    assert "metrics" in report
    assert "cases" in report
    assert report["metrics"]["total_cases"] == 2
    assert report["metrics"]["average_hallucination_score"] == 1.0
    assert report["metrics"]["passed_cases"] == 2
