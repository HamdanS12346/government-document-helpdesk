"""Unit tests for DocumentFormatter.

Tests: DocumentFormatter class (app/rag/context_builder/formatter.py)
"""

from app.contracts.retrieval import ChunkMetadata, RetrievedDocument
from app.rag.context_builder.formatter import DocumentFormatter


def make_doc(
    chunk_id: str = "chunk-001",
    text: str = "To relieve small taxpayers from such compliance burden...",
    document_name: str = "income-tax-return-and-related-forms",
    category: str = "income-documents",
    source_url: str = "https://www.incometax.gov.in/iec/foportal/help/e-filing-itr4",
    source_type: str = "webpage",
    score: float = 0.94,
) -> RetrievedDocument:
    return RetrievedDocument(
        id=chunk_id,
        text_content=text,
        metadata=ChunkMetadata(
            document_id=f"tax-docs__{chunk_id}",
            category=category,
            document_name=document_name,
            source_url=source_url,
            source_type=source_type,
        ),
        score=score,
    )


# ---------------------------------------------------------------------------
# format_single_chunk
# ---------------------------------------------------------------------------

def test_citation_label_uses_provided_index():
    doc = make_doc()
    out = DocumentFormatter().format_single_chunk(doc, 3)
    assert "[Document 3]" in out


def test_document_name_always_present():
    doc = make_doc()
    out = DocumentFormatter().format_single_chunk(doc, 1)
    assert "Document: income-tax-return-and-related-forms" in out


def test_category_always_present():
    doc = make_doc()
    out = DocumentFormatter().format_single_chunk(doc, 1)
    assert "Category: income-documents" in out


def test_source_url_present_when_set():
    doc = make_doc()
    out = DocumentFormatter().format_single_chunk(doc, 1)
    assert "Source URL: https://www.incometax.gov.in" in out


def test_source_type_present_when_set():
    doc = make_doc()
    out = DocumentFormatter().format_single_chunk(doc, 1)
    assert "Source Type: webpage" in out


def test_relevance_score_rendered_to_4_decimal_places():
    doc = make_doc(score=0.94)
    out = DocumentFormatter(include_score=True).format_single_chunk(doc, 1)
    assert "Relevance Score: 0.9400" in out


def test_score_absent_when_none():
    doc = make_doc(score=None)
    out = DocumentFormatter(include_score=True).format_single_chunk(doc, 1)
    assert "Relevance Score" not in out


def test_score_absent_when_include_score_false():
    doc = make_doc(score=0.88)
    out = DocumentFormatter(include_score=False).format_single_chunk(doc, 1)
    assert "Relevance Score" not in out


def test_content_label_separator_present():
    doc = make_doc()
    out = DocumentFormatter().format_single_chunk(doc, 1)
    assert "Content:\n" in out


def test_text_content_in_output():
    doc = make_doc(text="Proof of address can include utility bills.")
    out = DocumentFormatter().format_single_chunk(doc, 1)
    assert "Proof of address can include utility bills." in out


def test_source_url_absent_when_none():
    doc = RetrievedDocument(
        id="no-url",
        text_content="Content.",
        metadata=ChunkMetadata(
            document_id="doc-no-url",
            category="test",
            document_name="Test Document",
            source_url=None,
        ),
    )
    out = DocumentFormatter().format_single_chunk(doc, 1)
    assert "Source URL" not in out


def test_source_type_absent_when_none():
    doc = RetrievedDocument(
        id="no-type",
        text_content="Content.",
        metadata=ChunkMetadata(
            document_id="doc-no-type",
            category="test",
            document_name="Test Document",
            source_type=None,
        ),
    )
    out = DocumentFormatter().format_single_chunk(doc, 1)
    assert "Source Type" not in out


# ---------------------------------------------------------------------------
# format_all_chunks
# ---------------------------------------------------------------------------

def test_empty_list_returns_fallback_message():
    formatter = DocumentFormatter(default_empty_message="Nothing found.")
    assert formatter.format_all_chunks([]) == "Nothing found."


def test_single_doc_no_delimiter():
    doc = make_doc()
    out = DocumentFormatter().format_all_chunks([doc])
    assert "---" not in out


def test_two_docs_have_delimiter():
    doc1 = make_doc("chunk-1")
    doc2 = make_doc("chunk-2")
    out = DocumentFormatter().format_all_chunks([doc1, doc2])
    assert "---" in out


def test_three_docs_sequential_citation_labels():
    docs = [make_doc(f"chunk-{i}") for i in range(3)]
    out = DocumentFormatter().format_all_chunks(docs)
    assert "[Document 1]" in out
    assert "[Document 2]" in out
    assert "[Document 3]" in out


def test_custom_delimiter_used():
    doc1 = make_doc("a")
    doc2 = make_doc("b")
    formatter = DocumentFormatter(delimiter="\n===\n")
    out = formatter.format_all_chunks([doc1, doc2])
    assert "\n===\n" in out
    assert "---" not in out
