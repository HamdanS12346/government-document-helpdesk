"""Unit tests for VectorStoreRetriever dense adapter behavior."""

import pytest

from app.rag.vector_store import RetrievalServiceError, VectorStoreRetriever


class FakeCollection:
    def __init__(self) -> None:
        self.count_calls = 0
        self.query_calls = []

    def count(self) -> int:
        self.count_calls += 1
        return 42

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        return {
            "ids": [["doc1"]],
            "documents": [["PAN application requires proof of identity."]],
            "metadatas": [[
                {
                    "document_id": "identity-documents__pan-card",
                    "category": "identity-documents",
                    "document_name": "pan-card",
                }
            ]],
            "distances": [[0.2]],
        }


class FakeChromaClient:
    def __init__(self, collection: FakeCollection) -> None:
        self.collection = collection

    def get_or_create_collection(self, **kwargs):
        return self.collection


class FakeEmbeddings:
    def __init__(self) -> None:
        self.embed_query_calls = 0

    def embed_query(self, query: str):
        self.embed_query_calls += 1
        return [0.1, 0.2, 0.3]


class FailingEmbeddings:
    def embed_query(self, query: str):
        raise RuntimeError("missing OPENAI_API_KEY")


def test_vector_store_search_does_not_count_collection():
    collection = FakeCollection()
    embeddings = FakeEmbeddings()
    retriever = VectorStoreRetriever(
        embeddings_model=embeddings,
        chroma_client=FakeChromaClient(collection),
    )

    assert retriever.warm_resources() is True
    assert collection.count_calls == 0

    results = retriever.search("PAN identity", top_k=5)

    assert len(results) == 1
    assert results[0].id == "doc1"
    assert collection.count_calls == 0
    assert collection.query_calls[0]["n_results"] == 5


def test_vector_store_search_raises_provider_error_for_embedding_failure():
    retriever = VectorStoreRetriever(embeddings_model=FailingEmbeddings())

    with pytest.raises(RetrievalServiceError) as exc_info:
        retriever.search("PAN identity", top_k=5)

    assert exc_info.value.component == "dense_retrieval"
    assert exc_info.value.code == "openai_embedding_failed"
