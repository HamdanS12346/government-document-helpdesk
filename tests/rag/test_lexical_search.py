"""Unit tests for BM25LexicalSearcher."""

from app.contracts.retrieval import ChunkMetadata, RetrievedDocument
from app.rag.lexical_search import BM25LexicalSearcher


def create_sample_doc(doc_id: str, text: str, category: str = "tax") -> RetrievedDocument:
    return RetrievedDocument(
        id=doc_id,
        text_content=text,
        metadata=ChunkMetadata(
            document_id=f"doc_{doc_id}",
            category=category,
            document_name="Government Document Guide",
        ),
    )


def test_bm25_search_finds_exact_terms():
    docs = [
        create_sample_doc("doc1", "To claim deduction under section 80C, investment in PPF or ELSS is required."),
        create_sample_doc("doc2", "Section 44AD provides presumptive taxation for small businesses with turnover below 3 crore."),
        create_sample_doc("doc3", "Passport renewal requires proof of residence such as Aadhaar or utility bill."),
    ]
    searcher = BM25LexicalSearcher(documents=docs)

    results = searcher.search(query="Section 44AD presumptive taxation", top_k=2)
    assert len(results) > 0
    assert results[0].id == "doc2"
    assert results[0].score is not None
    assert results[0].score > 0.0


def test_bm25_search_empty_or_unmatched_query():
    docs = [create_sample_doc("doc1", "Income tax return filing due date.")]
    searcher = BM25LexicalSearcher(documents=docs)

    # Completely unmatched terms
    results = searcher.search(query="extraterrestrial spaceship galaxy", top_k=5)
    assert len(results) == 0

    # Empty query
    assert len(searcher.search(query="", top_k=5)) == 0


def test_bm25_empty_searcher():
    searcher = BM25LexicalSearcher()
    results = searcher.search(query="any query", top_k=5)
    assert results == []


def test_bm25_ensure_indexed_loads_external_corpus_once():
    docs = [
        create_sample_doc("doc1", "PAN application requires proof of identity."),
        create_sample_doc("doc2", "Passport renewal requires address proof."),
        create_sample_doc("doc3", "Income tax return filing has a due date."),
    ]
    searcher = BM25LexicalSearcher()
    provider_calls = 0

    def documents_provider():
        nonlocal provider_calls
        provider_calls += 1
        return docs

    assert searcher.ensure_indexed(documents_provider) is True
    assert searcher.document_count == 3

    results = searcher.search(query="PAN identity", top_k=1)
    assert len(results) == 1
    assert results[0].id == "doc1"

    assert searcher.ensure_indexed(documents_provider) is True
    assert provider_calls == 1
