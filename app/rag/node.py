"""LangGraph Retriever Node implementation."""

import logging
from typing import Any, Dict, List, Optional
from app.config import get_settings
from app.contracts.normalized_input import NormalizedInput
from app.contracts.retrieval import RetrievedDocument
from app.rag.hybrid_fusion import reciprocal_rank_fusion
from app.rag.lexical_search import BM25LexicalSearcher
from app.rag.metadata_extractor import MetadataExtractor
from app.rag.query_rewriter import QueryRewriter
from app.rag.reranker import CohereReranker
from app.rag.vector_store import VectorStoreRetriever
from langchain_community.callbacks import get_openai_callback

from app.observability import start_observation
from app.observability.metadata import (
    build_documents_metadata,
    build_normalized_input_metadata,
    build_query_rewrite_input_metadata,
    build_query_rewrite_output_metadata,
)
from guardrails.retrieval import QueryInjectionGuard, RetrievalGuardrailDecision

logger = logging.getLogger(__name__)


def _debug_print(*args: object, **kwargs: object) -> None:
    if get_settings().chat_debug_prints:
        print(*args, **kwargs)


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
        rrf_top_n: int = 15,
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

    def warm_lexical_index(self) -> bool:
        """Ensure BM25 has the same canonical corpus available to dense search."""
        ensure_indexed = getattr(self.lexical_searcher, "ensure_indexed", None)
        get_all_documents = getattr(self.vector_retriever, "get_all_documents", None)
        if not callable(ensure_indexed) or not callable(get_all_documents):
            return False

        before_count = getattr(self.lexical_searcher, "document_count", 0)
        loaded = ensure_indexed(get_all_documents)
        after_count = getattr(self.lexical_searcher, "document_count", 0)

        if after_count > before_count:
            logger.info("Initialized BM25 lexical index with %d document chunks.", after_count)
        elif not loaded:
            logger.warning("BM25 lexical index is empty; lexical retrieval will return no documents.")
        return bool(loaded)

    def warm_dense_resources(self) -> bool:
        """Initialize Chroma collection, collection count, and embedding client."""
        warm_resources = getattr(self.vector_retriever, "warm_resources", None)
        if not callable(warm_resources):
            return False
        warmed = warm_resources()
        if warmed:
            logger.info("Initialized dense retrieval resources.")
        return bool(warmed)

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the end-to-end retriever pipeline on a LangGraph state dictionary."""
        raw_norm_input = state.get("normalized_input")
        if isinstance(raw_norm_input, dict):
            norm_input = NormalizedInput.model_validate(raw_norm_input)
        elif isinstance(raw_norm_input, NormalizedInput):
            norm_input = raw_norm_input
        else:
            norm_input = NormalizedInput(user_query=str(raw_norm_input or ""))

        retrieval_input = norm_input.combined_text.strip() or norm_input.user_query
        used_combined_text = bool(norm_input.combined_text.strip())
        messages = state.get("messages", [])
        summary = state.get("conversation_summary")

        # --- Query Injection Guard ---
        # Applied before query rewrite so hostile fragments never reach the LLM
        # query rewriter, ChromaDB, or BM25.
        _injection_guard = QueryInjectionGuard()
        injection_result = _injection_guard.check(
            retrieval_input,
            user_query=norm_input.user_query,
        )
        guardrail_flags = dict(state.get("guardrail_flags") or {})
        guardrail_flags["query_injection_decision"] = injection_result.decision
        if injection_result.matched_pattern_names:
            guardrail_flags["query_injection_patterns"] = injection_result.matched_pattern_names

        if injection_result.decision == RetrievalGuardrailDecision.REJECT:
            logger.error(
                "[QueryInjectionGuard] REJECT — aborting retrieval pipeline. "
                "Matched patterns: %s.",
                injection_result.matched_pattern_names,
            )
            return {"documents": [], "guardrail_flags": guardrail_flags}
        if injection_result.decision == RetrievalGuardrailDecision.SANITIZE_AND_CONTINUE:
            logger.warning(
                "[QueryInjectionGuard] SANITIZE — query cleaned before retrieval. "
                "Matched patterns: %s.",
                injection_result.matched_pattern_names,
            )
            retrieval_input = injection_result.sanitized_query
        # --- End Query Injection Guard ---

        with start_observation(
            "retriever",
            input={
                **build_normalized_input_metadata(
                    norm_input,
                    messages=messages,
                    conversation_summary=summary,
                ),
                "intent_type": str(
                    getattr(state.get("intent_decision"), "intent_type", "")
                ),
            },
        ) as retriever_observation:
            with start_observation(
                "query_rewrite",
                as_type="generation",
                model="gpt-4o-mini",
                input=build_query_rewrite_input_metadata(
                    retrieval_input,
                    used_combined_text=used_combined_text,
                    messages=messages,
                    conversation_summary=summary,
                    attachment_preview_count=0,
                ),
            ) as query_observation:
                with get_openai_callback() as rewrite_cb:
                    rewritten_query = self.query_rewriter.rewrite(
                        user_query=retrieval_input,
                        messages=messages,
                        conversation_summary=summary,
                        attachment_previews=[],
                    )
                query_output = build_query_rewrite_output_metadata(
                    retrieval_input,
                    rewritten_query,
                )
                if rewrite_cb.total_tokens > 0:
                    query_output["token_usage"] = {
                        "input_tokens": rewrite_cb.prompt_tokens,
                        "output_tokens": rewrite_cb.completion_tokens,
                        "total_tokens": rewrite_cb.total_tokens,
                    }
                query_observation.update(
                    output=query_output,
                    usage_details={
                        "input": rewrite_cb.prompt_tokens,
                        "output": rewrite_cb.completion_tokens,
                        "total": rewrite_cb.total_tokens,
                    },
                )

            logger.info(
                "Retrieval input: '%s' -> Rewritten query: '%s'",
                retrieval_input,
                rewritten_query,
            )

            _debug_print("\n[Retriever Node] Conversation History in Memory:", flush=True)
            if messages:
                for idx, msg in enumerate(messages, 1):
                    msg_type = getattr(msg, "type", "")
                    content = getattr(msg, "content", str(msg))
                    role_label = (
                        "Human Message"
                        if msg_type == "human"
                        else ("AI Message" if msg_type == "ai" else f"{msg_type.capitalize()} Message")
                    )
                    _debug_print(f"  {idx}. {role_label}: {content}", flush=True)
            else:
                _debug_print("  (None - initial turn)", flush=True)

            if summary:
                _debug_print(f"[Retriever Node] Conversation Summary:\n  {summary}", flush=True)

            _debug_print(f"[Retriever Node] Query Optimization:", flush=True)
            _debug_print(f"  Original Query:  {retrieval_input}", flush=True)
            _debug_print(f"  Optimized Query: {rewritten_query}\n", flush=True)

            with start_observation(
                "metadata_filter",
                as_type="generation",
                model="gpt-4o-mini",
                input={"rewritten_query_length": len(rewritten_query)},
            ) as metadata_observation:
                with get_openai_callback() as meta_cb:
                    meta_decision = self.metadata_extractor.extract(rewritten_query)
                chroma_where = MetadataExtractor.build_chroma_filter(meta_decision)
                bm25_filter = MetadataExtractor.build_criteria(meta_decision)
                meta_output = {
                    "is_confident": meta_decision.is_confident,
                    "category": meta_decision.category,
                    "document_name": meta_decision.document_name,
                    "chroma_filter_applied": chroma_where is not None,
                    "bm25_filter_applied": bm25_filter is not None,
                }
                if meta_cb.total_tokens > 0:
                    meta_output["token_usage"] = {
                        "input_tokens": meta_cb.prompt_tokens,
                        "output_tokens": meta_cb.completion_tokens,
                        "total_tokens": meta_cb.total_tokens,
                    }
                metadata_observation.update(
                    output=meta_output,
                    usage_details={
                        "input": meta_cb.prompt_tokens,
                        "output": meta_cb.completion_tokens,
                        "total": meta_cb.total_tokens,
                    },
                )

            logger.info(
                "Metadata filter decision: confident=%s, category=%s, subcategory=%s",
                meta_decision.is_confident,
                meta_decision.category,
                meta_decision.document_name,
            )

            with start_observation(
                "dense_retrieval",
                input={
                    "method": "dense_vector",
                    "top_k": self.dense_top_k,
                    "filter_applied": chroma_where is not None,
                    "rewritten_query_length": len(rewritten_query),
                },
            ) as dense_observation:
                dense_results = self.vector_retriever.search(
                    rewritten_query,
                    top_k=self.dense_top_k,
                    where=chroma_where,
                )
                dense_observation.update(output=build_documents_metadata(dense_results))

            with start_observation(
                "lexical_retrieval",
                input={
                    "method": "bm25_lexical",
                    "top_k": self.bm25_top_k,
                    "filter_applied": bm25_filter is not None,
                    "rewritten_query_length": len(rewritten_query),
                },
            ) as lexical_observation:
                lexical_results = self.lexical_searcher.search(
                    rewritten_query,
                    top_k=self.bm25_top_k,
                    filter_criteria=bm25_filter,
                )
                lexical_observation.update(
                    output=build_documents_metadata(lexical_results)
                )

            with start_observation(
                "reciprocal_rank_fusion",
                input={
                    "dense_result_count": len(dense_results),
                    "lexical_result_count": len(lexical_results),
                    "rrf_k": self.rrf_k,
                    "rrf_top_n": self.rrf_top_n,
                },
            ) as rrf_observation:
                fused_results = reciprocal_rank_fusion(
                    dense_results=dense_results,
                    lexical_results=lexical_results,
                    k=self.rrf_k,
                    top_n=self.rrf_top_n,
                )
                rrf_observation.update(output=build_documents_metadata(fused_results))

            with start_observation(
                "reranking",
                input={
                    "reranker_provider": "cohere",
                    "input_document_count": len(fused_results),
                    "top_n": self.final_top_k,
                },
            ) as rerank_observation:
                final_documents, applied_fallback = self.reranker.rerank(
                    query=rewritten_query,
                    documents=fused_results,
                    top_n=self.final_top_k,
                )
                rerank_observation.update(
                    output={
                        **build_documents_metadata(final_documents),
                        "fallback_applied": applied_fallback,
                    }
                )

            logger.info(
                "Retrieved %d final documents (fallback applied: %s)",
                len(final_documents),
                applied_fallback,
            )

            retrieval_input_tokens = rewrite_cb.prompt_tokens + meta_cb.prompt_tokens
            retrieval_output_tokens = rewrite_cb.completion_tokens + meta_cb.completion_tokens
            retrieval_total_tokens = rewrite_cb.total_tokens + meta_cb.total_tokens

            retriever_output = {
                **build_documents_metadata(final_documents),
                "fallback_applied": applied_fallback,
            }
            if retrieval_total_tokens > 0:
                retriever_output["token_usage"] = {
                    "input_tokens": retrieval_input_tokens,
                    "output_tokens": retrieval_output_tokens,
                    "total_tokens": retrieval_total_tokens,
                }

            retriever_observation.update(
                output=retriever_output,
                usage_details={
                    "input": retrieval_input_tokens,
                    "output": retrieval_output_tokens,
                    "total": retrieval_total_tokens,
                },
            )

        ret_update: Dict[str, Any] = {"documents": final_documents}
        if guardrail_flags:
            ret_update["guardrail_flags"] = guardrail_flags
        return ret_update


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
