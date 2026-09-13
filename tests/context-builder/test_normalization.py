"""Unit tests for normalize_retrieved_documents.

Tests: input format flexibility — native Pydantic, raw dicts, LangChain-style
objects, RetrievalOutput containers, None, empty lists, and bad inputs.
"""

import pytest
from app.contracts.retrieval import ChunkMetadata, RetrievedDocument, RetrievalOutput
from app.rag.context_builder import normalize_retrieved_documents


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def make_chunk_meta(**kwargs) -> ChunkMetadata:
    defaults = dict(
        document_id="tax-docs__itr4__india",
        category="income-documents",
        document_name="income-tax-return-and-related-forms",
    )
    defaults.update(kwargs)
    return ChunkMetadata(**defaults)


def make_doc(chunk_id: str = "chunk-001", text: str = "Sample content.", **meta_kwargs) -> RetrievedDocument:
    return RetrievedDocument(
        id=chunk_id,
        text_content=text,
        metadata=make_chunk_meta(**meta_kwargs),
        score=0.90,
    )


# ---------------------------------------------------------------------------
# Native Pydantic models
# ---------------------------------------------------------------------------

def test_native_pydantic_passed_through():
    doc = make_doc()
    result = normalize_retrieved_documents([doc])
    assert len(result) == 1
    assert result[0] is doc  # same object, not a copy


def test_multiple_native_docs_all_returned():
    docs = [make_doc(f"chunk-{i}") for i in range(3)]
    result = normalize_retrieved_documents(docs)
    assert len(result) == 3


# ---------------------------------------------------------------------------
# Plain dict inputs
# ---------------------------------------------------------------------------

def test_dict_with_text_content_key():
    raw = {
        "id": "dict-chunk-001",
        "text_content": "Form 6 is required for new voter registration.",
        "metadata": {
            "document_id": "voter-docs__form6__india",
            "category": "voter-registration",
            "document_name": "voter-registration-form-6",
        },
        "score": 0.85,
    }
    result = normalize_retrieved_documents([raw])
    assert len(result) == 1
    assert isinstance(result[0], RetrievedDocument)
    assert result[0].id == "dict-chunk-001"
    assert result[0].text_content == "Form 6 is required for new voter registration."
    assert result[0].metadata.document_name == "voter-registration-form-6"
    assert result[0].score == 0.85


def test_dict_with_content_key_fallback():
    raw = {"id": "chunk-x", "content": "Driving license requires physical test.", "metadata": {
        "document_id": "dl-docs__rto__india",
        "category": "transport",
        "document_name": "driving-license-rules",
    }}
    result = normalize_retrieved_documents([raw])
    assert result[0].text_content == "Driving license requires physical test."


def test_dict_with_page_content_key_fallback():
    raw = {"id": "chunk-y", "page_content": "Ration card can serve as address proof.", "metadata": {
        "document_id": "ration-docs__pds__india",
        "category": "welfare",
        "document_name": "ration-card-guidelines",
    }}
    result = normalize_retrieved_documents([raw])
    assert result[0].text_content == "Ration card can serve as address proof."


def test_dict_preserves_score():
    raw = {"id": "x", "text_content": "content", "metadata": {
        "document_id": "d", "category": "c", "document_name": "n",
    }, "score": 0.77}
    result = normalize_retrieved_documents([raw])
    assert result[0].score == 0.77


def test_dict_invalid_score_becomes_none():
    raw = {"id": "x", "text_content": "y", "metadata": {
        "document_id": "d", "category": "c", "document_name": "n",
    }, "score": "not-a-number"}
    result = normalize_retrieved_documents([raw])
    assert result[0].score is None


# ---------------------------------------------------------------------------
# RetrievalOutput container
# ---------------------------------------------------------------------------

def test_retrieval_output_container_unwrapped():
    doc = make_doc()
    container = RetrievalOutput(
        original_query="What documents are needed?",
        rewritten_query="required documents for application",
        documents=[doc],
        applied_fallback=False,
    )
    result = normalize_retrieved_documents(container)
    assert len(result) == 1
    assert result[0].id == doc.id


# ---------------------------------------------------------------------------
# LangChain-style duck-type objects
# ---------------------------------------------------------------------------

def test_langchain_style_object_normalised():
    class MockLangChainDoc:
        id = "lc-chunk-01"
        page_content = "Passport validity is 10 years for adults."
        metadata = {
            "document_id": "passport-docs__mea__india",
            "category": "identity-documents",
            "document_name": "passport-application-guidelines",
        }
        score = None

    result = normalize_retrieved_documents([MockLangChainDoc()])
    assert len(result) == 1
    assert result[0].text_content == "Passport validity is 10 years for adults."


# ---------------------------------------------------------------------------
# Empty / None / bad inputs
# ---------------------------------------------------------------------------

def test_none_returns_empty_list():
    assert normalize_retrieved_documents(None) == []


def test_empty_list_returns_empty_list():
    assert normalize_retrieved_documents([]) == []


def test_string_input_returns_empty_list():
    assert normalize_retrieved_documents("this is not a document list") == []


def test_integer_input_returns_empty_list():
    assert normalize_retrieved_documents(42) == []


def test_none_items_inside_list_are_skipped():
    doc = make_doc()
    result = normalize_retrieved_documents([None, doc, None])
    assert len(result) == 1
    assert result[0].id == doc.id


def test_all_results_are_retrieved_document_instances():
    raw = {"id": "x", "text_content": "y", "metadata": {
        "document_id": "d", "category": "c", "document_name": "n",
    }}
    result = normalize_retrieved_documents([raw])
    assert all(isinstance(r, RetrievedDocument) for r in result)
