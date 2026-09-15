"""Unit tests for CohereReranker and circuit breaker fallback."""

from unittest.mock import MagicMock
from app.contracts.retrieval import ChunkMetadata, RetrievedDocument
from app.rag.reranker import CohereReranker


def create_doc(doc_id: str, text: str, initial_score: float = 0.0) -> RetrievedDocument:
    return RetrievedDocument(
        id=doc_id,
        text_content=text,
        metadata=ChunkMetadata(
            document_id=f"doc_{doc_id}",
            category="general",
            document_name="Guide",
        ),
        score=initial_score,
    )


def test_cohere_rerank_success():
    """Successful Cohere rerank re-orders documents and updates scores."""
    doc1 = create_doc("doc1", "General procedural instructions", 0.02)
    doc2 = create_doc("doc2", "Exact tax calculation for Section 44AD", 0.01)

    mock_client = MagicMock()
    # Mock Cohere returning doc2 as rank 1 and doc1 as rank 2
    mock_result_item_0 = MagicMock()
    mock_result_item_0.index = 1
    mock_result_item_0.relevance_score = 0.98

    mock_result_item_1 = MagicMock()
    mock_result_item_1.index = 0
    mock_result_item_1.relevance_score = 0.45

    mock_response = MagicMock()
    mock_response.results = [mock_result_item_0, mock_result_item_1]
    mock_client.rerank.return_value = mock_response

    reranker = CohereReranker(api_key="test-key", client=mock_client)
    reranked, fallback = reranker.rerank(
        query="Section 44AD tax calculation",
        documents=[doc1, doc2],
        top_n=2,
    )

    assert fallback is False
    assert len(reranked) == 2
    assert reranked[0].id == "doc2"
    assert reranked[0].score == 0.98
    assert reranked[1].id == "doc1"
    assert reranked[1].score == 0.45


def test_cohere_fallback_when_api_key_absent():
    """When API key is not present, reranker falls back to input order."""
    doc1 = create_doc("doc1", "First doc", 0.03)
    doc2 = create_doc("doc2", "Second doc", 0.02)

    reranker = CohereReranker(api_key=None, client=None)
    reranked, fallback = reranker.rerank(
        query="Any query",
        documents=[doc1, doc2],
        top_n=1,
    )

    assert fallback is True
    assert len(reranked) == 1
    assert reranked[0].id == "doc1"


def test_cohere_fallback_on_api_exception():
    """When Cohere API throws an exception, circuit breaker falls back to RRF ranking."""
    doc1 = create_doc("doc1", "First doc", 0.03)
    doc2 = create_doc("doc2", "Second doc", 0.02)

    mock_client = MagicMock()
    mock_client.rerank.side_effect = ConnectionError("Cohere API gateway timeout")

    reranker = CohereReranker(api_key="test-key", client=mock_client)
    reranked, fallback = reranker.rerank(
        query="Any query",
        documents=[doc1, doc2],
        top_n=2,
    )

    assert fallback is True
    assert len(reranked) == 2
    assert reranked[0].id == "doc1"
    assert reranked[1].id == "doc2"


def test_empty_documents():
    reranker = CohereReranker()
    reranked, fallback = reranker.rerank(query="test", documents=[], top_n=5)
    assert reranked == []
    assert fallback is False
