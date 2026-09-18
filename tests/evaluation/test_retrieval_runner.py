"""Unit tests for retrieval evaluation runner initialization and corpus validation."""

from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from evaluation.runners.run_retrieval import (
    initialize_and_validate_corpus,
    run_dataset,
)


def test_corpus_initialization_fails_when_chroma_is_empty():
    """Verify that initialize_and_validate_corpus fails fast when Chroma has 0 documents."""
    pipeline = MagicMock()
    pipeline.warm_dense_resources.return_value = True

    # Chroma collection exists but has 0 documents
    collection = MagicMock()
    collection.count.return_value = 0
    pipeline.vector_retriever._get_collection.return_value = collection
    pipeline.vector_retriever.document_count = 0
    pipeline.vector_retriever._documents = []

    with pytest.raises(RuntimeError, match="Chroma corpus is empty"):
        initialize_and_validate_corpus(pipeline)


def test_corpus_initialization_fails_when_chroma_collection_is_none():
    """Verify failure when Chroma collection cannot be obtained."""
    pipeline = MagicMock()
    pipeline.warm_dense_resources.return_value = False
    pipeline.vector_retriever._get_collection.return_value = None
    pipeline.vector_retriever.document_count = 0
    pipeline.vector_retriever._documents = []

    with pytest.raises(RuntimeError, match="Chroma corpus is empty"):
        initialize_and_validate_corpus(pipeline)


def test_corpus_initialization_fails_when_bm25_is_empty():
    """Verify that initialize_and_validate_corpus fails fast when BM25 has 0 documents."""
    pipeline = MagicMock()
    pipeline.warm_dense_resources.return_value = True

    collection = MagicMock()
    collection.count.return_value = 100
    pipeline.vector_retriever._get_collection.return_value = collection

    # BM25 fails to index or remains empty
    pipeline.warm_lexical_index.return_value = False
    pipeline.lexical_searcher.document_count = 0
    pipeline.lexical_searcher.is_indexed = False

    with pytest.raises(RuntimeError, match="BM25 corpus is empty"):
        initialize_and_validate_corpus(pipeline)


def test_corpus_initialization_succeeds_when_both_populated():
    """Verify that initialize_and_validate_corpus returns counts when both corpora are ready."""
    pipeline = MagicMock()
    pipeline.warm_dense_resources.return_value = True

    collection = MagicMock()
    collection.count.return_value = 42
    pipeline.vector_retriever._get_collection.return_value = collection

    pipeline.warm_lexical_index.return_value = True
    pipeline.lexical_searcher.document_count = 42
    pipeline.lexical_searcher.is_indexed = True

    chroma_count, bm25_count = initialize_and_validate_corpus(pipeline)
    assert chroma_count == 42
    assert bm25_count == 42
    pipeline.warm_dense_resources.assert_called_once()
    pipeline.warm_lexical_index.assert_called_once()


def test_run_dataset_aborts_on_empty_corpus(tmp_path):
    """Verify run_dataset fails fast without executing cases if corpus validation fails."""
    dataset_file = tmp_path / "cases.jsonl"
    dataset_file.write_text('{"id": "RET-001", "query": "test query", "expected_chunks": ["doc-1"]}\n')

    pipeline = MagicMock()
    pipeline.vector_retriever._get_collection.return_value = None
    pipeline.vector_retriever.document_count = 0
    pipeline.vector_retriever._documents = []

    with pytest.raises(RuntimeError, match="Chroma corpus is empty"):
        run_dataset(dataset_file, pipeline=pipeline)


def test_evaluate_and_summarize_retrieval_evidence_counts():
    """Verify candidate counts flow through case evaluation and metric summarization."""
    from evaluation.evaluators.retrieval.evaluator import (
        evaluate_retrieval_case,
        summarize_retrieval_results,
    )

    case = {"id": "RET-001", "query": "test", "expected_chunks": ["doc-1"]}
    res = evaluate_retrieval_case(
        case=case,
        retrieved_chunks=["doc-1", "doc-2"],
        dense_result_count=10,
        lexical_result_count=8,
    )
    assert res["dense_result_count"] == 10
    assert res["lexical_result_count"] == 8

    case2 = {"id": "RET-002", "query": "test 2", "expected_chunks": ["doc-3"]}
    res2 = evaluate_retrieval_case(
        case=case2,
        retrieved_chunks=["doc-3"],
        dense_result_count=6,
        lexical_result_count=4,
    )

    summary = summarize_retrieval_results([res, res2])
    assert summary["average_dense_result_count"] == 8.0
    assert summary["average_lexical_result_count"] == 6.0


def test_run_dataset_produces_corpus_evidence(tmp_path):
    """Verify run_dataset output includes corpus_evidence and per-case candidate counts."""
    dataset_file = tmp_path / "cases.jsonl"
    dataset_file.write_text(
        '{"id": "RET-001", "query": "test query 1", "expected_chunks": ["chunk-1"]}\n'
        '{"id": "RET-002", "query": "test query 2", "expected_chunks": ["chunk-2"]}\n'
    )

    pipeline = MagicMock()
    pipeline.warm_dense_resources.return_value = True
    collection = MagicMock()
    collection.count.return_value = 1948
    pipeline.vector_retriever._get_collection.return_value = collection

    pipeline.warm_lexical_index.return_value = True
    pipeline.lexical_searcher.document_count = 1948
    pipeline.lexical_searcher.is_indexed = True

    from app.contracts.retrieval import RetrievedDocument, RetrievalStatus, ChunkMetadata

    # Mock execute output for each case
    def mock_execute(state):
        return {
            "retrieved_documents": [
                RetrievedDocument(
                    id="chunk-1",
                    text_content="sample text",
                    metadata=ChunkMetadata(
                        document_id="doc-1",
                        category="test",
                        document_name="Test Doc",
                    ),
                    score=0.9,
                )
            ],
            "retrieval_status": RetrievalStatus(
                status="success",
                dense_result_count=5,
                lexical_result_count=5,
                final_document_count=1,
            ),
        }

    pipeline.execute.side_effect = mock_execute

    report = run_dataset(dataset_file, pipeline=pipeline)

    # 1. Corpus evidence block
    assert "corpus_evidence" in report
    evidence = report["corpus_evidence"]
    assert evidence["chroma_document_count"] == 1948
    assert evidence["bm25_document_count"] == 1948
    assert evidence["average_dense_result_count"] == 5.0
    assert evidence["average_lexical_result_count"] == 5.0
    assert evidence["hybrid_retrieval_verified"] is True

    # 2. Metrics enriched
    metrics = report["metrics"]
    assert metrics["chroma_document_count"] == 1948
    assert metrics["bm25_document_count"] == 1948
    assert metrics["average_dense_result_count"] == 5.0
    assert metrics["average_lexical_result_count"] == 5.0
    assert metrics["hybrid_retrieval_verified"] is True

    # 3. Per-case evidence
    for case_res in report["cases"]:
        assert case_res["dense_result_count"] == 5
        assert case_res["lexical_result_count"] == 5

