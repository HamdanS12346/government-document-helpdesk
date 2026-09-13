"""LangGraph Retriever Node implementation."""

import logging
from typing import Any, Dict, List, Optional
from app.contracts.intent_decision import IntentDecision
from app.contracts.normalized_input import NormalizedInput
from app.contracts.retrieval import RetrievedDocument
from app.rag.hybrid_fusion import reciprocal_rank_fusion
from app.rag.lexical_search import BM25LexicalSearcher
from app.rag.metadata_extractor import MetadataExtractor, MetadataFilterDecision
from app.rag.query_rewriter import QueryRewriter
from app.rag.reranker import CohereReranker
from app.rag.vector_store import VectorStoreRetriever

logger = logging.getLogger(__name__)


class RetrieverPipeline:
    """Configurable pipeline orchestrating query rewriting, metadata filtering, hybrid search, RRF, and reranking."""

    def __init__(
        self,
        query_rewriter: Optional[QueryRewriter] = None,
        metadata_extractor: Optional[MetadataExtractor] = None,
        lexical_searcher: Optional[BM25LexicalSearcher] = None,
        vector_retriever: Optional[VectorStoreRetriever] = None,
        reranker: Optional[CohereReranker] = None,
        dense_top_k: int = 25,
        bm25_top_k: int = 25,
        rrf_top_n: int = 25,
        final_top_k: int = 5,
        rrf_k: int = 60,
    ):
        self.query_rewriter = query_rewriter or QueryRewriter()
        self.metadata_extractor = metadata_extractor or MetadataExtractor()
        self.lexical_searcher = lexical_searcher or BM25LexicalSearcher()
        self.vector_retriever = vector_retriever or VectorStoreRetriever()
        self.reranker = reranker or CohereReranker()
        self.dense_top_k = dense_top_k
        self.bm25_top_k = bm25_top_k
        self.rrf_top_n = rrf_top_n
        self.final_top_k = final_top_k
        self.rrf_k = rrf_k

    def set_corpus(self, documents: List[RetrievedDocument]) -> None:
        """Update active document corpus for both lexical and semantic searchers."""
        self.lexical_searcher.index(documents)
        self.vector_retriever.index(documents)

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the end-to-end retriever pipeline on a LangGraph state dictionary."""
        # 1. Parse NormalizedInput
        raw_norm_input = state.get("normalized_input")
        if isinstance(raw_norm_input, dict):
            norm_input = NormalizedInput.model_validate(raw_norm_input)
        elif isinstance(raw_norm_input, NormalizedInput):
            norm_input = raw_norm_input
        else:
            norm_input = NormalizedInput(user_query=str(raw_norm_input or ""))

        retrieval_input = norm_input.combined_text.strip() or norm_input.user_query
        messages = state.get("messages", [])
        summary = state.get("conversation_summary")

        # 2. Query Rewriting
        rewritten_query = self.query_rewriter.rewrite(
            user_query=retrieval_input,
            messages=messages,
            conversation_summary=summary,
            attachment_previews=[],
        )

        logger.info(
            "Retrieval input: '%s' -> Rewritten query: '%s'",
            retrieval_input,
            rewritten_query,
        )

        # 3. High-Confidence Metadata Filtering
        meta_decision = self.metadata_extractor.extract(rewritten_query)
        chroma_where = MetadataExtractor.build_chroma_filter(meta_decision)
        bm25_filter = MetadataExtractor.build_criteria(meta_decision)

        logger.info(
            "Metadata filter decision: confident=%s, category=%s, subcategory=%s",
            meta_decision.is_confident,
            meta_decision.category,
            meta_decision.document_name,
        )

        # 4. Dual Hybrid Retrieval (with metadata filtering)
        dense_results = self.vector_retriever.search(
            rewritten_query,
            top_k=self.dense_top_k,
            where=chroma_where,
        )
        lexical_results = self.lexical_searcher.search(
            rewritten_query,
            top_k=self.bm25_top_k,
            filter_criteria=bm25_filter,
        )

        # 4. Reciprocal Rank Fusion (RRF)
        fused_results = reciprocal_rank_fusion(
            dense_results=dense_results,
            lexical_results=lexical_results,
            k=self.rrf_k,
            top_n=self.rrf_top_n,
        )

        # 5. Cohere Cross-Encoder Reranking (with automated circuit-breaker fallback)
        final_documents, applied_fallback = self.reranker.rerank(
            query=rewritten_query,
            documents=fused_results,
            top_n=self.final_top_k,
        )

        logger.info(
            "Retrieved %d final documents (fallback applied: %s)",
            len(final_documents),
            applied_fallback,
        )

        return {"documents": final_documents}


# Default singleton pipeline instance for LangGraph wiring
_default_pipeline: Optional[RetrieverPipeline] = None


def get_default_retriever_pipeline() -> RetrieverPipeline:
    global _default_pipeline
    if _default_pipeline is None:
        _default_pipeline = RetrieverPipeline()
    return _default_pipeline


def set_default_retriever_pipeline(pipeline: RetrieverPipeline) -> None:
    global _default_pipeline
    _default_pipeline = pipeline


def retriever_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph node function for the Retriever stage."""
    pipeline = get_default_retriever_pipeline()
    return pipeline.execute(state)


__all__ = [
    "RetrieverPipeline",
    "retriever_node",
    "get_default_retriever_pipeline",
    "set_default_retriever_pipeline",
]
