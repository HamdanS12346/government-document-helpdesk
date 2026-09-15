"""Unit tests for context builder contract models.

Tests: ContextSource, RetrievedContext (app/contracts/response.py)
"""

from app.contracts.response import ContextSource, RetrievedContext


def test_context_source_fields():
    source = ContextSource(
        index=1,
        chunk_id="income-documents__itr4-form__chunk-0001",
        document_name="income-tax-return-and-related-forms",
        source_url="https://www.incometax.gov.in/iec/foportal/help/e-filing-itr4-form-sugam-faq",
        score=0.94,
    )
    assert source.index == 1
    assert source.chunk_id == "income-documents__itr4-form__chunk-0001"
    assert source.document_name == "income-tax-return-and-related-forms"
    assert source.source_url.startswith("https://")
    assert source.score == 0.94


def test_context_source_optional_fields_default_none():
    source = ContextSource(index=1, chunk_id="chunk-x")
    assert source.document_name is None
    assert source.source_url is None
    assert source.score is None


def test_retrieved_context_fields():
    source = ContextSource(index=1, chunk_id="chunk-1", document_name="Tax Guide")
    rc = RetrievedContext(
        formatted_context="[Document 1]\nDocument: Tax Guide\nContent:\nSome evidence.",
        sources=[source],
        total_documents_retrieved=5,
        documents_used=1,
        has_relevant_documents=True,
        truncated=False,
        fallback_applied=False,
    )
    assert rc.documents_used == 1
    assert rc.total_documents_retrieved == 5
    assert rc.has_relevant_documents is True
    assert rc.truncated is False
    assert rc.fallback_applied is False
    assert len(rc.sources) == 1


def test_retrieved_context_text_property():
    rc = RetrievedContext(formatted_context="Evidence text here.", sources=[])
    assert rc.text == "Evidence text here."
    assert rc.text == rc.formatted_context


def test_retrieved_context_str_returns_formatted_context():
    rc = RetrievedContext(formatted_context="Expected output.", sources=[])
    assert str(rc) == "Expected output."


def test_retrieved_context_fallback_defaults():
    rc = RetrievedContext(
        formatted_context="No relevant government documents were found for this query.",
        sources=[],
        has_relevant_documents=False,
        fallback_applied=True,
    )
    assert rc.documents_used == 0
    assert rc.has_relevant_documents is False
    assert rc.fallback_applied is True
    assert rc.truncated is False
