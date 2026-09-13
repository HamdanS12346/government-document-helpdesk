"""Unit tests for the context_builder_node LangGraph adapter.

Tests: context_builder_node (app/rag/context_builder/node.py)
"""

from app.contracts.retrieval import ChunkMetadata, RetrievedDocument
from app.contracts.response import RetrievedContext
from app.rag.context_builder import ContextBuilder, context_builder_node


def make_doc_dict(chunk_id: str, text: str = "GST registration is mandatory.", score: float = 0.92) -> dict:
    return {
        "id": chunk_id,
        "text_content": text,
        "metadata": {
            "document_id": f"gst-docs__{chunk_id}",
            "category": "tax-documents",
            "document_name": "gst-registration-rules",
            "source_url": "https://gst.gov.in/rules",
            "source_type": "webpage",
        },
        "score": score,
    }


# ---------------------------------------------------------------------------
# State contract
# ---------------------------------------------------------------------------

def test_node_returns_dict():
    state = {"documents": []}
    output = context_builder_node(state)
    assert isinstance(output, dict)


def test_node_output_has_retrieved_context_key():
    state = {"documents": []}
    output = context_builder_node(state)
    assert "retrieved_context" in output


def test_node_output_is_retrieved_context_instance():
    state = {"documents": []}
    output = context_builder_node(state)
    assert isinstance(output["retrieved_context"], RetrievedContext)


# ---------------------------------------------------------------------------
# Normal processing
# ---------------------------------------------------------------------------

def test_node_processes_dict_documents_from_state():
    state = {"documents": [make_doc_dict("gst-chunk-001")]}
    rc = context_builder_node(state)["retrieved_context"]
    assert rc.has_relevant_documents is True
    assert "GST registration is mandatory." in rc.formatted_context


def test_node_processes_pydantic_documents_from_state():
    doc = RetrievedDocument(
        id="itr-chunk-001",
        text_content="ITR-4 form is for presumptive income taxpayers.",
        metadata=ChunkMetadata(
            document_id="tax-docs__itr4__india",
            category="income-documents",
            document_name="income-tax-return-and-related-forms",
            source_url="https://www.incometax.gov.in/",
        ),
        score=0.95,
    )
    state = {"documents": [doc]}
    rc = context_builder_node(state)["retrieved_context"]
    assert rc.has_relevant_documents is True
    assert rc.documents_used == 1
    assert "ITR-4 form is for presumptive income taxpayers." in rc.formatted_context


def test_node_multiple_documents_all_included():
    state = {"documents": [
        make_doc_dict(f"chunk-{i}", text=f"Unique document content for chunk {i} on GST rules.", score=1.0 - i * 0.05)
        for i in range(3)
    ]}
    rc = context_builder_node(state)["retrieved_context"]
    assert rc.documents_used == 3
    assert "[Document 1]" in rc.formatted_context
    assert "[Document 2]" in rc.formatted_context
    assert "[Document 3]" in rc.formatted_context


# ---------------------------------------------------------------------------
# Empty / missing documents
# ---------------------------------------------------------------------------

def test_node_empty_documents_returns_fallback():
    state = {"documents": []}
    rc = context_builder_node(state)["retrieved_context"]
    assert rc.has_relevant_documents is False
    assert rc.fallback_applied is True


def test_node_missing_documents_key_handled():
    state = {}  # no "documents" key at all
    rc = context_builder_node(state)["retrieved_context"]
    assert rc.has_relevant_documents is False


def test_node_none_documents_returns_fallback():
    state = {"documents": None}
    rc = context_builder_node(state)["retrieved_context"]
    assert rc.has_relevant_documents is False
    assert rc.fallback_applied is True


# ---------------------------------------------------------------------------
# Custom builder injection
# ---------------------------------------------------------------------------

def test_node_accepts_custom_builder():
    custom_builder = ContextBuilder(empty_fallback_message="Custom fallback message.")
    state = {"documents": []}
    rc = context_builder_node(state, builder=custom_builder)["retrieved_context"]
    assert rc.formatted_context == "Custom fallback message."
