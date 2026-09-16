"""End-to-end integration tests for retriever_node."""

from unittest.mock import MagicMock
from langchain_core.messages import AIMessage, HumanMessage
from app.contracts.intent_decision import IntentDecision
from app.contracts.normalized_input import ImageContent, NormalizedInput, PDFContent
from app.contracts.retrieval import ChunkMetadata, RetrievedDocument
from app.rag.lexical_search import BM25LexicalSearcher
from app.rag.metadata_extractor import MetadataFilterDecision
from app.rag.node import RetrieverPipeline, retriever_node, set_default_retriever_pipeline
from app.rag.query_rewriter import QueryRewriter
from app.rag.reranker import CohereReranker
from app.rag.vector_store import VectorStoreRetriever


def get_mock_corpus() -> list[RetrievedDocument]:
    return [
        RetrievedDocument(
            id="income-documents__itr-forms__india__source-001__chunk-0001",
            text_content="Section 44AD provides presumptive taxation scheme for resident individual, HUF, and partnership firms with turnover up to 3 crore.",
            metadata=ChunkMetadata(
                document_id="income-documents__itr-forms__india",
                category="income-documents",
                document_name="income-tax-return-and-related-forms",
                source_url="https://incometax.gov.in/sec44ad",
                source_type="webpage",
            ),
        ),
        RetrievedDocument(
            id="income-documents__itr-forms__india__source-001__chunk-0002",
            text_content="Section 44ADA applies to professionals like doctors, lawyers, and engineers with receipts up to 75 lakh.",
            metadata=ChunkMetadata(
                document_id="income-documents__itr-forms__india",
                category="income-documents",
                document_name="income-tax-return-and-related-forms",
                source_url="https://incometax.gov.in/sec44ada",
                source_type="webpage",
            ),
        ),
        RetrievedDocument(
            id="identity-documents__passport__india__source-002__chunk-0001",
            text_content="For passport address proof, utility bills or certificate of residence from designated authorities can be used.",
            metadata=ChunkMetadata(
                document_id="identity-documents__passport__india",
                category="identity-documents",
                document_name="passport-application-rules",
                source_url="https://passportindia.gov.in/rules",
                source_type="webpage",
            ),
        ),
    ]


def test_retriever_node_single_turn():
    """Single-turn query retrieves relevant documents through hybrid search and fallback rerank."""
    corpus = get_mock_corpus()

    pipeline = RetrieverPipeline(
        lexical_searcher=BM25LexicalSearcher(corpus),
        vector_retriever=VectorStoreRetriever(),
        reranker=CohereReranker(api_key=None),  # Uses RRF fallback
        final_top_k=2,
    )
    set_default_retriever_pipeline(pipeline)

    state = {
        "normalized_input": NormalizedInput(
            user_query="Section 44AD presumptive taxation turnover limit",
            image_content=[],
            pdf_content=[],
            combined_text="Section 44AD presumptive taxation turnover limit",
        ),
        "intent_decision": IntentDecision(
            query="Section 44AD presumptive taxation turnover limit",
            intent_type="document_info",
            confidence_score=0.98,
        ),
        "messages": [],
        "conversation_summary": None,
    }

    result = retriever_node(state)

    assert "documents" in result
    docs = result["documents"]
    assert len(docs) > 0
    assert docs[0].id == "income-documents__itr-forms__india__source-001__chunk-0001"
    assert "Section 44AD" in docs[0].text_content
    assert docs[0].metadata.document_name == "income-tax-return-and-related-forms"


def test_retriever_node_multi_turn_with_cohere_rerank():
    """Multi-turn query resolves pronoun references and reranks results via Cohere."""
    corpus = get_mock_corpus()

    # Mock query rewriter LLM
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = AIMessage(
        content="What is the presumptive taxation threshold limit under Section 44ADA?"
    )
    query_rewriter = QueryRewriter(llm=mock_llm)

    # Mock Cohere client reranking index 1 (Section 44ADA chunk) as the most relevant
    mock_cohere = MagicMock()
    mock_result_item = MagicMock()
    mock_result_item.index = 1
    mock_result_item.relevance_score = 0.96
    mock_response = MagicMock()
    mock_response.results = [mock_result_item]
    mock_cohere.rerank.return_value = mock_response

    reranker = CohereReranker(api_key="mock-key", client=mock_cohere)

    pipeline = RetrieverPipeline(
        query_rewriter=query_rewriter,
        lexical_searcher=BM25LexicalSearcher(corpus),
        vector_retriever=VectorStoreRetriever(),
        reranker=reranker,
        final_top_k=1,
    )

    state = {
        "normalized_input": NormalizedInput(
            user_query="What is the limit for the second one?",
            image_content=[],
            pdf_content=[],
            combined_text="What is the limit for the second one?",
        ),
        "messages": [
            HumanMessage(content="Explain presumptive taxation schemes"),
            AIMessage(content="There are schemes under 44AD for business and 44ADA for professionals"),
        ],
        "conversation_summary": None,
    }

    result = pipeline.execute(state)

    assert "documents" in result
    assert len(result["documents"]) == 1
    doc = result["documents"][0]
    assert doc.id == "income-documents__itr-forms__india__source-001__chunk-0002"
    assert "Section 44ADA" in doc.text_content
    assert doc.score == 0.96


def test_retriever_node_with_multimodal_attachments():
    """Combined text lets attached images and PDFs inform query rewriting."""
    corpus = get_mock_corpus()

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = AIMessage(
        content="Can a Certificate of Residence be used as proof of address for passport?"
    )
    query_rewriter = QueryRewriter(llm=mock_llm)

    pipeline = RetrieverPipeline(
        query_rewriter=query_rewriter,
        lexical_searcher=BM25LexicalSearcher(corpus),
        vector_retriever=VectorStoreRetriever(),
        reranker=CohereReranker(api_key=None),
        final_top_k=1,
    )

    state = {
        "normalized_input": NormalizedInput(
            user_query="Can I use this document for passport?",
            image_content=[
                ImageContent(
                    image_name="residence.jpg",
                    extracted_text="Certificate of Residence...",
                    preview="Certificate of Residence",
                )
            ],
            pdf_content=[
                PDFContent(
                    pdf_name="annexure.pdf",
                    extracted_text="Annexure details...",
                    preview="Annexure A address proof",
                )
            ],
            combined_text=(
                "User Query:\nCan I use this document for passport?\n\n"
                "Attached Image: residence.jpg\nPreview: Certificate of Residence\n\n"
                "Attached PDF: annexure.pdf\nPreview: Annexure A address proof"
            ),
        ),
        "messages": [],
        "conversation_summary": None,
    }

    result = pipeline.execute(state)

    assert "documents" in result
    assert len(result["documents"]) == 1
    doc = result["documents"][0]
    assert doc.id == "identity-documents__passport__india__source-002__chunk-0001"
    assert "passport" in doc.text_content.lower()


class RecordingQueryRewriter:
    def __init__(self) -> None:
        self.user_query = None
        self.messages = None
        self.conversation_summary = None
        self.attachment_previews = None

    def rewrite(
        self,
        user_query,
        messages=None,
        conversation_summary=None,
        attachment_previews=None,
    ):
        self.user_query = user_query
        self.messages = messages
        self.conversation_summary = conversation_summary
        self.attachment_previews = attachment_previews
        return "rewritten retrieval query"


class FakeMetadataExtractor:
    def extract(self, query):
        return MetadataFilterDecision(
            category=None,
            document_name=None,
            is_confident=False,
            reasoning="test",
        )


class EmptyVectorRetriever:
    def search(self, query, top_k=25, where=None):
        return []


class CorpusOnlyVectorRetriever:
    def __init__(self, corpus):
        self.corpus = corpus
        self.get_all_documents_calls = 0

    def search(self, query, top_k=25, where=None):
        return []

    def get_all_documents(self):
        self.get_all_documents_calls += 1
        return self.corpus


class EmptyLexicalSearcher:
    def search(self, query, top_k=25, filter_criteria=None):
        return []


class PassthroughReranker:
    def rerank(self, query, documents, top_n=5):
        return documents[:top_n], False


def test_retriever_pipeline_rewrites_from_combined_text_not_intent_query():
    """Retriever query rewriting starts from normalized combined_text."""
    query_rewriter = RecordingQueryRewriter()
    pipeline = RetrieverPipeline(
        query_rewriter=query_rewriter,
        metadata_extractor=FakeMetadataExtractor(),
        lexical_searcher=EmptyLexicalSearcher(),
        vector_retriever=EmptyVectorRetriever(),
        reranker=PassthroughReranker(),
    )
    combined_text = (
        "<USER_QUERY>\nCan I use this for passport?\n\n"
        "<IMAGE_CONTENT>\nCertificate of Residence extracted from image."
    )
    state = {
        "normalized_input": NormalizedInput(
            user_query="Can I use this for passport?",
            image_content=[
                ImageContent(
                    image_name="residence.jpg",
                    extracted_text="Certificate of Residence extracted from image.",
                    preview="Certificate of Residence",
                )
            ],
            pdf_content=[],
            combined_text=combined_text,
        ),
        "intent_decision": IntentDecision(
            query="classifier preview query",
            intent_type="document_info",
            confidence_score=0.93,
        ),
        "messages": [{"role": "human", "content": "Previous turn"}],
        "conversation_summary": "Earlier passport address proof question.",
    }

    result = pipeline.execute(state)

    assert result == {"documents": []}
    assert query_rewriter.user_query == combined_text
    assert query_rewriter.user_query != state["intent_decision"].query
    assert query_rewriter.messages == state["messages"]
    assert query_rewriter.conversation_summary == state["conversation_summary"]
    assert query_rewriter.attachment_previews == []


def test_retriever_pipeline_uses_startup_warmed_lexical_index():
    """Default-style BM25 searcher can warm before requests and then search locally."""
    corpus = get_mock_corpus()
    vector_retriever = CorpusOnlyVectorRetriever(corpus)
    pipeline = RetrieverPipeline(
        query_rewriter=QueryRewriter(),
        metadata_extractor=FakeMetadataExtractor(),
        lexical_searcher=BM25LexicalSearcher(),
        vector_retriever=vector_retriever,
        reranker=PassthroughReranker(),
        final_top_k=2,
    )
    state = {
        "normalized_input": NormalizedInput(
            user_query="Section 44ADA professionals receipts",
            image_content=[],
            pdf_content=[],
            combined_text="Section 44ADA professionals receipts",
        ),
        "messages": [],
        "conversation_summary": None,
    }

    assert pipeline.warm_lexical_index() is True
    assert vector_retriever.get_all_documents_calls == 1

    first_result = pipeline.execute(state)
    second_result = pipeline.execute(state)

    assert len(first_result["documents"]) > 0
    assert first_result["documents"][0].id == "income-documents__itr-forms__india__source-001__chunk-0002"
    assert len(second_result["documents"]) > 0
    assert vector_retriever.get_all_documents_calls == 1
