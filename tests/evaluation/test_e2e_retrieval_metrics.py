"""Unit tests for retrieval metrics calculation within the connected graph evaluation runner."""

from __future__ import annotations

from evaluation.evaluators.retrieval.evaluator import evaluate_retrieval_case


def test_expected_chunks_extraction_from_response_case():
    """Verify ground-truth chunk IDs are correctly extracted from response case context."""
    case = {
        "id": "RESP-001",
        "query": "What is passport requirement?",
        "context": [
            {"chunk_id": "doc-chunk-1", "text": "Passport info..."},
            {"chunk_id": "doc-chunk-2", "text": "Validity info..."},
        ],
    }

    expected_chunks = case.get("expected_chunks") or [
        c["chunk_id"] for c in case.get("context", []) if isinstance(c, dict) and "chunk_id" in c
    ]

    assert expected_chunks == ["doc-chunk-1", "doc-chunk-2"]


def test_expected_chunks_fallback_to_explicit_field():
    """Verify explicit expected_chunks field takes precedence if provided."""
    case = {
        "id": "RESP-002",
        "query": "Test query",
        "expected_chunks": ["doc-chunk-override"],
        "context": [{"chunk_id": "doc-chunk-1"}],
    }

    expected_chunks = case.get("expected_chunks") or [
        c["chunk_id"] for c in case.get("context", []) if isinstance(c, dict) and "chunk_id" in c
    ]

    assert expected_chunks == ["doc-chunk-override"]


def test_retrieval_metrics_calculation_hit():
    """Verify retrieval metrics when retrieved chunks match expected chunks."""
    case = {
        "id": "RESP-003",
        "query": "Where do I apply?",
        "expected_chunks": ["doc-1"],
    }
    retrieved_chunk_ids = ["doc-1", "doc-2", "doc-3", "doc-4", "doc-5"]

    retrieval_res = evaluate_retrieval_case(
        case=case,
        retrieved_chunks=retrieved_chunk_ids,
    )

    assert retrieval_res["recall_at_5"] == 1.0
    assert retrieval_res["precision_at_5"] == 0.2  # 1 relevant out of 5 retrieved
    assert retrieval_res["mrr"] == 1.0  # First result
    assert retrieval_res["ndcg_at_5"] == 1.0


def test_retrieval_metrics_calculation_miss():
    """Verify retrieval metrics when retrieved chunks do not match."""
    case = {
        "id": "RESP-004",
        "query": "Where do I apply?",
        "expected_chunks": ["doc-99"],
    }
    retrieved_chunk_ids = ["doc-1", "doc-2", "doc-3", "doc-4", "doc-5"]

    retrieval_res = evaluate_retrieval_case(
        case=case,
        retrieved_chunks=retrieved_chunk_ids,
    )

    assert retrieval_res["recall_at_5"] == 0.0
    assert retrieval_res["precision_at_5"] == 0.0
    assert retrieval_res["mrr"] == 0.0
    assert retrieval_res["ndcg_at_5"] == 0.0


def test_retrieval_metrics_empty_expected_chunks():
    """Verify graceful handling when no expected chunks exist (e.g. chit-chat query)."""
    case = {
        "id": "RESP-005",
        "query": "Hello",
        "expected_chunks": [],
    }
    retrieved_chunk_ids = []

    retrieval_res = evaluate_retrieval_case(
        case=case,
        retrieved_chunks=retrieved_chunk_ids,
    )

    assert retrieval_res["recall_at_5"] == 0.0
    assert retrieval_res["precision_at_5"] == 0.0
    assert retrieval_res["mrr"] == 0.0


def test_graph_evaluation_output_candidate_counts():
    """Verify GraphEvaluationOutput holds and serializes dense and lexical candidate counts."""
    from evaluation.graph.adapter import GraphEvaluationOutput

    out = GraphEvaluationOutput(
        success=True,
        query="test query",
        dense_result_count=12,
        lexical_result_count=18,
    )
    assert out.dense_result_count == 12
    assert out.lexical_result_count == 18

    d = out.to_dict()
    assert d["dense_result_count"] == 12
    assert d["lexical_result_count"] == 18


def test_connected_graph_adapter_extracts_candidate_counts(monkeypatch):
    """Verify ConnectedGraphAdapter extracts candidate counts from state retrieval_status."""
    from unittest.mock import MagicMock
    from evaluation.graph.adapter import ConnectedGraphAdapter
    from app.contracts.retrieval import RetrievalStatus

    adapter = ConnectedGraphAdapter()

    # Mock process_input
    mock_input_res = MagicMock()
    mock_input_res.success = True
    mock_input_res.normalized_input = MagicMock()
    mock_input_res.normalized_input.model_dump.return_value = {"user_query": "test"}

    monkeypatch.setattr("evaluation.graph.adapter.process_input", lambda *a, **kw: mock_input_res)

    # Mock invoke_full_graph returning state with retrieval_status
    mock_ret_status = RetrievalStatus(
        status="success",
        dense_result_count=15,
        lexical_result_count=20,
        final_document_count=5,
    )
    monkeypatch.setattr(
        "evaluation.graph.adapter.invoke_full_graph",
        lambda **kw: {
            "retrieval_status": mock_ret_status,
            "documents": [],
            "messages": [],
            "clarification_round_count": 0,
        },
    )

    out = adapter.run(query="test")
    assert out.success is True
    assert out.dense_result_count == 15
    assert out.lexical_result_count == 20


def test_run_e2e_demo_corpus_evidence_reporting(monkeypatch, tmp_path):
    """Verify run_demo produces corpus_evidence and per-case hybrid counts in report."""
    from unittest.mock import MagicMock
    from evaluation.runners import run_e2e_demo
    from evaluation.graph.adapter import GraphEvaluationOutput

    # Mock ensure_corpus_indexed to return 1948, 1948
    monkeypatch.setattr(run_e2e_demo, "ensure_corpus_indexed", lambda: (1948, 1948))
    monkeypatch.setattr(run_e2e_demo, "get_langfuse_client", lambda: None)
    monkeypatch.setattr(run_e2e_demo, "flush_langfuse", lambda: None)

    # Mock evaluate_response_case
    monkeypatch.setattr(
        run_e2e_demo,
        "evaluate_response_case",
        lambda **kw: {"scores": {"correctness": 1.0}, "composite_score": 1.0, "passed": True},
    )

    cases_file = tmp_path / "cases.jsonl"
    cases_file.write_text(
        '{"id": "RESP-001", "query": "passport query 1", "expected_chunks": ["chunk-1"]}\n'
        '{"id": "RESP-002", "query": "passport query 2", "expected_chunks": ["chunk-2"]}\n'
    )

    # Mock adapter
    mock_adapter = MagicMock()
    mock_adapter.run.side_effect = [
        GraphEvaluationOutput(
            success=True,
            query="passport query 1",
            retrieved_chunk_ids=["chunk-1"],
            dense_result_count=10,
            lexical_result_count=20,
            response="Answer 1",
        ),
        GraphEvaluationOutput(
            success=True,
            query="passport query 2",
            retrieved_chunk_ids=["chunk-2"],
            dense_result_count=14,
            lexical_result_count=22,
            response="Answer 2",
        ),
    ]

    out_file = tmp_path / "report.json"
    report = run_e2e_demo.run_demo(
        start=1,
        end=2,
        output=out_file,
        adapter=mock_adapter,
        cases_file=cases_file,
    )

    assert "corpus_evidence" in report
    evidence = report["corpus_evidence"]
    assert evidence["chroma_document_count"] == 1948
    assert evidence["bm25_document_count"] == 1948
    assert evidence["average_dense_result_count"] == 12.0
    assert evidence["average_lexical_result_count"] == 21.0
    assert evidence["hybrid_retrieval_verified"] is True

    assert out_file.exists()

