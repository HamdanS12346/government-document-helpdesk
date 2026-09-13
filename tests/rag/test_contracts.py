"""Unit tests for retrieval contracts."""

from app.contracts.retrieval import ChunkMetadata, RetrievalOutput, RetrievedDocument


def test_chunk_metadata_parsing():
    data = {
        "document_id": "income-documents__income-tax-return-and-related-forms__india",
        "category": "income-documents",
        "document_name": "income-tax-return-and-related-forms",
        "source_url": "https://www.incometax.gov.in/iec/foportal/help/e-filing-itr4-form-sugam-faq",
        "source_type": "webpage",
        "extra_field": "custom_value",
    }
    meta = ChunkMetadata.model_validate(data)
    assert meta.document_id == "income-documents__income-tax-return-and-related-forms__india"
    assert meta.category == "income-documents"
    assert meta.document_name == "income-tax-return-and-related-forms"
    assert meta.source_url == "https://www.incometax.gov.in/iec/foportal/help/e-filing-itr4-form-sugam-faq"
    assert meta.source_type == "webpage"
    assert getattr(meta, "extra_field") == "custom_value"


def test_retrieved_document_from_user_chunk_format():
    chunk_payload = {
        "id": "income-documents__income-tax-return-and-related-forms__india__source-005__chunk-0004",
        "text_content": "To relieve small taxpayers from such compliance burden...",
        "metadata": {
            "document_id": "income-documents__income-tax-return-and-related-forms__india",
            "category": "income-documents",
            "document_name": "income-tax-return-and-related-forms",
            "source_url": "https://www.incometax.gov.in/iec/foportal/help/e-filing-itr4-form-sugam-faq",
            "source_type": "webpage",
        },
    }
    doc = RetrievedDocument.model_validate(chunk_payload)
    assert doc.id == "income-documents__income-tax-return-and-related-forms__india__source-005__chunk-0004"
    assert doc.text_content.startswith("To relieve small")
    assert doc.content == doc.text_content
    assert doc.source == "https://www.incometax.gov.in/iec/foportal/help/e-filing-itr4-form-sugam-faq"
    assert doc.score is None

    doc.score = 0.95
    assert doc.score == 0.95


def test_retrieval_output_container():
    doc = RetrievedDocument(
        id="chunk-1",
        text_content="Sample text",
        metadata=ChunkMetadata(
            document_id="doc-1",
            category="tax",
            document_name="tax guide",
        ),
        score=0.88,
    )
    output = RetrievalOutput(
        original_query="What is tax?",
        rewritten_query="What is tax procedure?",
        documents=[doc],
        applied_fallback=False,
    )
    assert output.original_query == "What is tax?"
    assert len(output.documents) == 1
    assert not output.applied_fallback
