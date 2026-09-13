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
