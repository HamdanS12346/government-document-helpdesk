"""Common Graph Adapter for Connected RAG Graph Evaluation.

Provides a unified interface between evaluation runners (Input Processor,
Intent Classifier, Retrieval, and Response) and the connected LangGraph workflow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any, Callable, Iterable, List, Optional, Union

from langchain_community.callbacks import get_openai_callback
from langchain_core.messages import BaseMessage, HumanMessage

from app.contracts.intent_decision import IntentDecision
from app.contracts.normalized_input import NormalizedInput
from app.contracts.response import RetrievedContext
from app.graph.graph import (
    CLARIFICATION_NODE,
    CONTEXT_BUILDER_NODE,
    INTENT_CLASSIFIER_NODE,
    RESPONSE_NODE,
    RETRIEVER_NODE,
    invoke_full_graph,
)
from app.graph.state import State
from app.input_processing.ocr_provider import OCRProvider
from app.input_processing.pdf_processor import PDFExtractor, PDFPageImageExtractor
from app.input_processing.processors import process_input
from app.input_processing.schemas import (
    Attachment,
    InputProcessingResult,
    InputRequest,
)
from app.intent.classifier import IntentClassifier, OpenAIIntentClassifier
from app.rag.context_builder.node import context_builder_node
from app.rag.node import retriever_node
from app.response.node import response_node
from app.clarification.node import clarification_node

logger = logging.getLogger(__name__)


@dataclass
class GraphEvaluationOutput:
    """Unified result container exposing intermediate and final outputs of the graph."""

    success: bool
    query: str
    error: Optional[str] = None

    # Stage 1: Input Processor Output
    input_result: Optional[InputProcessingResult] = None
    normalized_input: Optional[NormalizedInput] = None

    # Stage 2: Intent Classifier Output
    intent_decision: Optional[IntentDecision] = None
    intent: Optional[str] = None
    confidence_score: Optional[float] = None

    # Stage 3: Retrieval Output
    documents: List[Any] = field(default_factory=list)
    retrieved_chunk_ids: List[str] = field(default_factory=list)

    # Stage 4: Context Builder Output
    retrieved_context: Optional[RetrievedContext] = None
    formatted_context: Optional[str] = None
    citations: List[str] = field(default_factory=list)

    # Stage 5: Response / Clarification Output
    response: Optional[str] = None
    clarification_question: Optional[str] = None
    is_clarification: bool = False

    # Multi-turn Context & Memory
    messages: List[Any] = field(default_factory=list)
    conversation_summary: Optional[str] = None
    clarification_round_count: int = 0
    thread_id: Optional[str] = None

    # Token Usage & Cost Metrics
    token_usage: dict[str, Any] = field(default_factory=dict)

    # Full Graph Raw State
    raw_state: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to structured evaluation schema matching Section 10 of evaluation plan."""
        return {
            "success": self.success,
            "query": self.query,
            "error": self.error,
            "processed_input": (
                self.normalized_input.model_dump()
                if self.normalized_input is not None
                else None
            ),
            "intent": self.intent,
            "confidence_score": self.confidence_score,
            "retrieved_chunk_ids": self.retrieved_chunk_ids,
            "retrieved_context": (
                [self.formatted_context] if self.formatted_context else []
            ),
            "response": self.response,
            "citations": self.citations,
            "is_clarification": self.is_clarification,
            "clarification_question": self.clarification_question,
            "clarification_round_count": self.clarification_round_count,
            "thread_id": self.thread_id,
            "conversation_summary": self.conversation_summary,
            "token_usage": self.token_usage,
        }


class ConnectedGraphAdapter:
    """Adapter executing the real connected LangGraph pipeline for evaluation."""

    def __init__(
        self,
        classifier: Optional[IntentClassifier] = None,
        retriever: Callable[[State], dict[str, Any]] = retriever_node,
        context_builder: Callable[[State], dict[str, Any]] = context_builder_node,
        responder: Callable[[State], dict[str, Any]] = response_node,
        clarification: Callable[[State], dict[str, Any]] = clarification_node,
        memory_manager: Optional[Any] = None,
        ocr_provider: Optional[OCRProvider] = None,
        pdf_extractor: Optional[PDFExtractor] = None,
        page_image_extractor: Optional[PDFPageImageExtractor] = None,
    ) -> None:
        self.classifier = classifier or OpenAIIntentClassifier()
        self.retriever = retriever
        self.context_builder = context_builder
        self.responder = responder
        self.clarification = clarification
        self.memory_manager = memory_manager
        self.ocr_provider = ocr_provider
        self.pdf_extractor = pdf_extractor
        self.page_image_extractor = page_image_extractor

    def run(
        self,
        query: str,
        attachments: Optional[List[Attachment]] = None,
        input_result: Optional[InputProcessingResult] = None,
        thread_id: Optional[str] = None,
        messages: Optional[Iterable[Any]] = None,
        conversation_summary: Optional[str] = None,
        clarification_round_count: Optional[int] = None,
    ) -> GraphEvaluationOutput:
        """Execute the connected graph and capture stage-by-stage outputs."""
        try:
            # Stage 1: Input Processing (if not already supplied)
            if input_result is None:
                request = InputRequest(
                    user_query=query,
                    attachments=attachments or [],
                )
                input_result = process_input(
                    request,
                    ocr_provider=self.ocr_provider,
                    pdf_extractor=self.pdf_extractor,
                    page_image_extractor=self.page_image_extractor,
                )

            if not input_result.success or input_result.normalized_input is None:
                err_msg = (
                    input_result.error_message
                    if hasattr(input_result, "error_message")
                    else "Input processing failed"
                )
                return GraphEvaluationOutput(
                    success=False,
                    query=query,
                    error=str(err_msg),
                    input_result=input_result,
                )

            # Stage-by-stage token trackers
            stage_tokens = {
                "intent": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0.0},
                "retrieval": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0.0},
                "response": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0.0},
                "clarification": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0.0},
            }

            class TrackedClassifier:
                def __init__(self, inner: Any) -> None:
                    self.inner = inner

                def classify(self, q: str, **kwargs: Any) -> Any:
                    with get_openai_callback() as cb:
                        res = self.inner.classify(q, **kwargs)
                    stage_tokens["intent"]["input_tokens"] += cb.prompt_tokens
                    stage_tokens["intent"]["output_tokens"] += cb.completion_tokens
                    stage_tokens["intent"]["total_tokens"] += cb.total_tokens
                    stage_tokens["intent"]["cost_usd"] += cb.total_cost
                    return res

            def tracked_retriever(state: State) -> dict[str, Any]:
                with get_openai_callback() as cb:
                    res = self.retriever(state)
                stage_tokens["retrieval"]["input_tokens"] += cb.prompt_tokens
                stage_tokens["retrieval"]["output_tokens"] += cb.completion_tokens
                stage_tokens["retrieval"]["total_tokens"] += cb.total_tokens
                stage_tokens["retrieval"]["cost_usd"] += cb.total_cost
                return res

            def tracked_responder(state: State) -> dict[str, Any]:
                with get_openai_callback() as cb:
                    res = self.responder(state)
                stage_tokens["response"]["input_tokens"] += cb.prompt_tokens
                stage_tokens["response"]["output_tokens"] += cb.completion_tokens
                stage_tokens["response"]["total_tokens"] += cb.total_tokens
                stage_tokens["response"]["cost_usd"] += cb.total_cost
                return res

            def tracked_clarification(state: State) -> dict[str, Any]:
                with get_openai_callback() as cb:
                    res = self.clarification(state)
                stage_tokens["clarification"]["input_tokens"] += cb.prompt_tokens
                stage_tokens["clarification"]["output_tokens"] += cb.completion_tokens
                stage_tokens["clarification"]["total_tokens"] += cb.total_tokens
                stage_tokens["clarification"]["cost_usd"] += cb.total_cost
                return res

            # Stage 2 to 5: Execute connected graph with callback tracking
            with get_openai_callback() as pipeline_cb:
                output_state = invoke_full_graph(
                    result=input_result,
                    classifier=TrackedClassifier(self.classifier),
                    retriever=tracked_retriever,
                    context_builder=self.context_builder,
                    responder=tracked_responder,
                    clarification=tracked_clarification,
                    thread_id=thread_id,
                    memory_manager=self.memory_manager,
                    messages=messages,
                    conversation_summary=conversation_summary,
                    clarification_round_count=clarification_round_count,
                )

            token_metrics = {
                "input_tokens": pipeline_cb.prompt_tokens,
                "output_tokens": pipeline_cb.completion_tokens,
                "total_tokens": pipeline_cb.total_tokens,
                "cost_usd": pipeline_cb.total_cost,
                "stages": stage_tokens,
            }

            # Unpack intermediate states
            normalized_input = output_state.get("normalized_input")
            intent_decision = output_state.get("intent_decision")
            intent_str = (
                str(intent_decision.intent_type.value)
                if intent_decision is not None and hasattr(intent_decision.intent_type, "value")
                else str(intent_decision.intent_type)
                if intent_decision is not None
                else None
            )
            confidence = (
                float(intent_decision.confidence_score)
                if intent_decision is not None
                else None
            )

            # Retrieved Documents & Chunk IDs
            docs = output_state.get("documents", []) or []
            chunk_ids: List[str] = []
            for doc in docs:
                if hasattr(doc, "id"):
                    chunk_ids.append(str(doc.id))
                elif isinstance(doc, dict) and "id" in doc:
                    chunk_ids.append(str(doc["id"]))

            # Context Builder output
            retrieved_ctx: Optional[RetrievedContext] = output_state.get("retrieved_context")
            formatted_ctx: Optional[str] = None
            citations: List[str] = []

            if retrieved_ctx is not None:
                formatted_ctx = getattr(retrieved_ctx, "formatted_context", None)
                sources = getattr(retrieved_ctx, "sources", []) or []
                for src in sources:
                    src_url = getattr(src, "source_url", None)
                    chunk_id = getattr(src, "chunk_id", None)
                    if src_url:
                        citations.append(str(src_url))
                    elif chunk_id:
                        citations.append(str(chunk_id))

            # Response / Clarification message
            state_messages = output_state.get("messages", []) or []
            final_response: Optional[str] = None
            clarification_text: Optional[str] = None
            is_clarification = False

            if state_messages:
                last_msg = state_messages[-1]
                content = getattr(last_msg, "content", str(last_msg))
                if intent_str == "ambiguous" and output_state.get("clarification_round_count", 0) > 0:
                    is_clarification = True
                    clarification_text = content
                else:
                    final_response = content

            return GraphEvaluationOutput(
                success=True,
                query=query,
                error=None,
                input_result=input_result,
                normalized_input=normalized_input,
                intent_decision=intent_decision,
                intent=intent_str,
                confidence_score=confidence,
                documents=docs,
                retrieved_chunk_ids=chunk_ids,
                retrieved_context=retrieved_ctx,
                formatted_context=formatted_ctx,
                citations=citations,
                response=final_response,
                clarification_question=clarification_text,
                is_clarification=is_clarification,
                messages=state_messages,
                conversation_summary=output_state.get("conversation_summary"),
                clarification_round_count=output_state.get("clarification_round_count", 0),
                thread_id=output_state.get("thread_id"),
                token_usage=token_metrics,
                raw_state=dict(output_state),
            )

        except Exception as exc:
            logger.exception("Error executing connected graph adapter: %s", exc)
            return GraphEvaluationOutput(
                success=False,
                query=query,
                error=str(exc),
                input_result=input_result,
            )


def run_graph(
    query: str,
    attachments: Optional[List[Attachment]] = None,
    classifier: Optional[IntentClassifier] = None,
    retriever: Callable[[State], dict[str, Any]] = retriever_node,
    context_builder: Callable[[State], dict[str, Any]] = context_builder_node,
    responder: Callable[[State], dict[str, Any]] = response_node,
    clarification: Callable[[State], dict[str, Any]] = clarification_node,
    memory_manager: Optional[Any] = None,
    thread_id: Optional[str] = None,
    messages: Optional[Iterable[Any]] = None,
    conversation_summary: Optional[str] = None,
    clarification_round_count: Optional[int] = None,
    ocr_provider: Optional[OCRProvider] = None,
    pdf_extractor: Optional[PDFExtractor] = None,
    page_image_extractor: Optional[PDFPageImageExtractor] = None,
) -> GraphEvaluationOutput:
    """Convenience functional interface to execute the connected graph for evaluation."""
    adapter = ConnectedGraphAdapter(
        classifier=classifier,
        retriever=retriever,
        context_builder=context_builder,
        responder=responder,
        clarification=clarification,
        memory_manager=memory_manager,
        ocr_provider=ocr_provider,
        pdf_extractor=pdf_extractor,
        page_image_extractor=page_image_extractor,
    )
    return adapter.run(
        query=query,
        attachments=attachments,
        thread_id=thread_id,
        messages=messages,
        conversation_summary=conversation_summary,
        clarification_round_count=clarification_round_count,
    )
