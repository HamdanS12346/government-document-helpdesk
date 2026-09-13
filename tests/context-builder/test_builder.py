"""Unit tests for ContextBuilder pipeline — dedup, filter, sort, budget.

Tests: ContextBuilder class (app/rag/context_builder/builder.py)
"""

import pytest
from app.contracts.retrieval import ChunkMetadata, RetrievedDocument
from app.contracts.response import RetrievedContext
from app.rag.context_builder import ContextBuilder


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def make_doc(
    chunk_id: str,
    text: str = "Sample government document content.",
    score: float = 0.90,
    document_name: str = "income-tax-return-and-related-forms",
    category: str = "income-documents",
    source_url: str = "https://www.incometax.gov.in/",
) -> RetrievedDocument:
    return RetrievedDocument(
        id=chunk_id,
        text_content=text,
        metadata=ChunkMetadata(
            document_id=f"tax-docs__{chunk_id}",
            category=category,
            document_name=document_name,
            source_url=source_url,
        ),
        score=score,
    )


# ---------------------------------------------------------------------------
# Single document — full round trip
# ---------------------------------------------------------------------------

def test_single_doc_returns_retrieved_context():
    doc = make_doc("chunk-001")
    result = ContextBuilder().build_context([doc])
    assert isinstance(result, RetrievedContext)


def test_single_doc_has_relevant_documents_true():
    result = ContextBuilder().build_context([make_doc("chunk-001")])
    assert result.has_relevant_documents is True


def test_single_doc_documents_used_is_one():
    result = ContextBuilder().build_context([make_doc("chunk-001")])
    assert result.documents_used == 1


def test_single_doc_fallback_not_applied():
    result = ContextBuilder().build_context([make_doc("chunk-001")])
    assert result.fallback_applied is False


def test_single_doc_citation_label_present():
    result = ContextBuilder().build_context([make_doc("chunk-001")])
    assert "[Document 1]" in result.formatted_context


def test_single_doc_document_name_in_context():
    result = ContextBuilder().build_context([make_doc("chunk-001")])
    assert "income-tax-return-and-related-forms" in result.formatted_context


def test_single_doc_source_url_in_context():
    result = ContextBuilder().build_context([make_doc("chunk-001")])
    assert "https://www.incometax.gov.in/" in result.formatted_context


def test_single_doc_text_content_in_context():
    result = ContextBuilder().build_context([make_doc("chunk-001")])
    assert "Sample government document content." in result.formatted_context


def test_single_doc_citation_source_fields():
    result = ContextBuilder().build_context([make_doc("chunk-001")])
    assert len(result.sources) == 1
    src = result.sources[0]
    assert src.index == 1
    assert src.chunk_id == "chunk-001"
    assert src.document_name == "income-tax-return-and-related-forms"
    assert src.source_url == "https://www.incometax.gov.in/"
    assert src.score == 0.90


# ---------------------------------------------------------------------------
# Empty / None — fallback behaviour
# ---------------------------------------------------------------------------

def test_empty_list_returns_fallback():
    builder = ContextBuilder(empty_fallback_message="No relevant government documents found.")
    result = builder.build_context([])
    assert result.has_relevant_documents is False
    assert result.fallback_applied is True
    assert result.documents_used == 0
    assert result.sources == []
    assert result.formatted_context == "No relevant government documents found."


def test_none_input_returns_fallback():
    result = ContextBuilder().build_context(None)
    assert result.has_relevant_documents is False
    assert result.fallback_applied is True


def test_empty_list_not_truncated():
    result = ContextBuilder().build_context([])
    assert result.truncated is False


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def test_duplicate_id_keeps_first_occurrence():
    doc1 = make_doc("chunk-1", text="Content A", score=0.90)
    doc2 = make_doc("chunk-1", text="Content A duplicate", score=0.85)
    result = ContextBuilder(deduplicate=True).build_context([doc1, doc2])
    assert result.documents_used == 1
    assert "Content A duplicate" not in result.formatted_context


def test_duplicate_content_hash_keeps_first():
    doc1 = make_doc("chunk-1", text="Identical text content.")
    doc2 = make_doc("chunk-2", text="Identical text content.")
    result = ContextBuilder(deduplicate=True).build_context([doc1, doc2])
    assert result.documents_used == 1
    assert result.sources[0].chunk_id == "chunk-1"


def test_deduplication_disabled_includes_all():
    doc1 = make_doc("chunk-1", text="Same text.")
    doc2 = make_doc("chunk-1", text="Same text.")
    result = ContextBuilder(deduplicate=False).build_context([doc1, doc2])
    assert result.documents_used == 2


def test_whitespace_variant_is_deduplicated():
    doc1 = make_doc("a", text="Same  text   here.")
    doc2 = make_doc("b", text="Same text here.")
    result = ContextBuilder(deduplicate=True).build_context([doc1, doc2])
    assert result.documents_used == 1


# ---------------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------------

def test_sorted_high_to_low_score():
    doc_low = make_doc("low", text="Low relevance content about voter registration.", score=0.60)
    doc_high = make_doc("high", text="High relevance content about income tax returns.", score=0.98)
    doc_mid = make_doc("mid", text="Mid relevance content about GST registration.", score=0.82)
    result = ContextBuilder(sort_by_score=True).build_context([doc_low, doc_high, doc_mid])
    chunk_ids = [s.chunk_id for s in result.sources]
    assert chunk_ids == ["high", "mid", "low"]


def test_sort_disabled_preserves_input_order():
    doc_low = make_doc("low", text="Voter ID card is accepted as address proof.", score=0.50)
    doc_high = make_doc("high", text="Aadhaar card is valid proof of identity for all services.", score=0.99)
    result = ContextBuilder(sort_by_score=False).build_context([doc_low, doc_high])
    assert result.sources[0].chunk_id == "low"
    assert result.sources[1].chunk_id == "high"


# ---------------------------------------------------------------------------
# Score filtering
# ---------------------------------------------------------------------------

def test_low_score_doc_excluded():
    doc_pass = make_doc("p1", score=0.85)
    doc_fail = make_doc("f1", score=0.45)
    result = ContextBuilder(min_relevance_score=0.70).build_context([doc_pass, doc_fail])
    chunk_ids = [s.chunk_id for s in result.sources]
    assert "f1" not in chunk_ids


def test_score_exactly_at_threshold_is_included():
    doc = make_doc("boundary", score=0.70)
    result = ContextBuilder(min_relevance_score=0.70).build_context([doc])
    assert result.documents_used == 1


def test_all_docs_below_threshold_returns_fallback():
    docs = [make_doc(f"doc-{i}", score=0.20) for i in range(3)]
    result = ContextBuilder(min_relevance_score=0.70).build_context(docs)
    assert result.has_relevant_documents is False
    assert result.fallback_applied is True


def test_total_retrieved_reflects_pre_filter_count():
    docs = [make_doc(f"doc-{i}", score=0.10) for i in range(4)]
    result = ContextBuilder(min_relevance_score=0.70).build_context(docs)
    assert result.total_documents_retrieved == 4
    assert result.documents_used == 0


# ---------------------------------------------------------------------------
# Context bounding (budget enforcement)
# ---------------------------------------------------------------------------

def test_truncated_flag_set_when_budget_exceeded():
    docs = [
        make_doc(f"chunk-{i}", text=f"Unique government procedure content item {i} details here. " * 20, score=1.0 - i * 0.05)
        for i in range(8)
    ]
    result = ContextBuilder(max_context_chars=500).build_context(docs)
    assert result.truncated is True


def test_documents_used_less_than_total_when_truncated():
    docs = [make_doc(f"chunk-{i}", text=f"Content block {i}: " + "A" * 190, score=1.0 - i * 0.05) for i in range(5)]
    result = ContextBuilder(max_context_chars=500).build_context(docs)
    assert result.documents_used < result.total_documents_retrieved


def test_single_oversized_chunk_sliced_to_budget():
    doc = make_doc("huge", text="A" * 2000)
    result = ContextBuilder(max_context_chars=300).build_context([doc])
    assert result.truncated is True
    assert result.documents_used == 1
    assert len(result.formatted_context) <= 300


def test_citation_indexes_sequential_after_truncation():
    docs = [make_doc(f"chunk-{i}", text=f"Unique citation content block number {i} describing government procedure. " * 3, score=1.0 - i * 0.05) for i in range(8)]
    result = ContextBuilder(max_context_chars=500).build_context(docs)
    expected = list(range(1, result.documents_used + 1))
    actual = [s.index for s in result.sources]
    assert actual == expected
