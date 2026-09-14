from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache
import json
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, UploadFile, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.api.serialization import serialize_public_message
from app.contracts.chat import (
    ChatIntentSummary,
    ChatMessage,
    ChatResponse,
    ChatStatus,
)
from app.graph.graph import invoke_full_graph, invoke_intent_retriever_graph
from app.input_processing.processors import process_input
from app.input_processing.schemas import Attachment, InputProcessingResult, InputRequest
from app.intent.classifier import OpenAIIntentClassifier
from app.observability import flush_langfuse, start_observation
from app.observability.metadata import (
    build_chat_request_metadata,
    build_chat_graph_response_metadata,
    build_input_processing_result_metadata,
    build_input_request_metadata,
)


_DEFAULT_INVOKE_INTENT_RETRIEVER = invoke_intent_retriever_graph


router = APIRouter()


@dataclass(frozen=True)
class UploadedFileBytes:
    """Transient upload bytes read at the HTTP boundary."""

    filename: str
    media_type: str
    content: bytes


@router.post("/chat")
async def chat(
    message: Annotated[str | None, Form()] = None,
    files: Annotated[list[UploadFile] | None, File()] = None,
) -> JSONResponse:
    """Process frontend chat input through the Input Processor boundary."""
    incoming_files = files or []
    with start_observation(
        "chat_request",
        input=build_chat_request_metadata(message, incoming_files),
    ) as trace:
        graph_state: dict[str, object] | None = None
        try:
            uploaded_files = await _read_uploaded_files(incoming_files)
            attachments = _build_attachments(uploaded_files)
            request = InputRequest(user_query=message, attachments=attachments)
            with start_observation(
                "input_processor",
                input=build_input_request_metadata(request),
            ) as input_observation:
                result = process_input(request)
                input_observation.update(
                    output=build_input_processing_result_metadata(result)
                )
            if result.success and result.normalized_input is not None:
                print("Normalized input:", flush=True)
                print(result.normalized_input.model_dump_json(indent=2), flush=True)
                try:
                    graph_state = _invoke_chat_graph(
                        result,
                    )
                except Exception:
                    trace.update(output={"status": "classification_error"})
                    return JSONResponse(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        content=_build_classification_error_payload(),
                    )
                print("\nIntent decision:", flush=True)
                print(graph_state["intent_decision"].model_dump_json(indent=2), flush=True)
                if "documents" in graph_state:
                    print("\nDocuments:", flush=True)
                    print(
                        json.dumps(
                            jsonable_encoder(graph_state["documents"]),
                            indent=2,
                        ),
                        flush=True,
                    )
                if "retrieved_context" in graph_state:
                    print("\nRetrieved context:", flush=True)
                    print(
                        json.dumps(
                            jsonable_encoder(graph_state["retrieved_context"]),
                            indent=2,
                        ),
                        flush=True,
                    )
                response_status = _build_chat_status(result, graph_state)
                assistant_message = _build_assistant_message(graph_state)
                trace.update(
                    output=build_chat_graph_response_metadata(
                        graph_state,
                        status=str(response_status),
                        assistant_message_content=(
                            assistant_message.content
                            if assistant_message is not None
                            else None
                        ),
                    )
                )
            else:
                print(result.model_dump_json(indent=2))
                trace.update(
                    output={
                        "status": "input_failed",
                        **build_input_processing_result_metadata(result),
                    }
                )
        except Exception:
            trace.update(output={"status": "system_error"})
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=_build_internal_error_payload(),
            )
        finally:
            flush_langfuse()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=_build_response_payload(result, graph_state),
    )


async def _read_uploaded_files(files: list[UploadFile]) -> list[UploadedFileBytes]:
    uploaded_files: list[UploadedFileBytes] = []
    for file in files:
        uploaded_files.append(
            UploadedFileBytes(
                filename=file.filename or "upload",
                media_type=file.content_type or "application/octet-stream",
                content=await file.read(),
            )
        )
    return uploaded_files


def _build_attachments(uploaded_files: list[UploadedFileBytes]) -> list[Attachment]:
    return [
        Attachment(
            filename=uploaded_file.filename,
            media_type=uploaded_file.media_type,
            content=uploaded_file.content,
        )
        for uploaded_file in uploaded_files
    ]


@cache
def _build_intent_classifier() -> OpenAIIntentClassifier:
    return OpenAIIntentClassifier()


def _invoke_chat_graph(
    result: InputProcessingResult,
    *,
    messages: Iterable[Any] | None = None,
    conversation_summary: str | None = None,
    clarification_round_count: int | None = None,
) -> dict[str, object]:
    """Invoke the chat graph with memory fields supplied by the API boundary."""

    memory_kwargs: dict[str, object] = {}
    if messages is not None:
        memory_kwargs["messages"] = messages
    if conversation_summary is not None:
        memory_kwargs["conversation_summary"] = conversation_summary
    if clarification_round_count is not None:
        memory_kwargs["clarification_round_count"] = clarification_round_count

    if invoke_intent_retriever_graph is not _DEFAULT_INVOKE_INTENT_RETRIEVER:
        return invoke_intent_retriever_graph(
            result,
            _build_intent_classifier(),
            **memory_kwargs,
        )

    return invoke_full_graph(
        result,
        _build_intent_classifier(),
        **memory_kwargs,
    )


def _build_response_payload(
    result: InputProcessingResult,
    graph_state: dict[str, object] | None = None,
) -> dict[str, object]:
    response = ChatResponse(
        success=result.success,
        status=_build_chat_status(result, graph_state),
        message=_build_response_message(result, graph_state),
        assistant_message=_build_assistant_message(graph_state),
        attachment_statuses=result.attachment_statuses,
        warnings=result.warnings,
        normalized_input=result.normalized_input,
        intent=_build_intent_summary(graph_state),
    )
    return jsonable_encoder(response)


def _build_chat_status(
    result: InputProcessingResult,
    graph_state: dict[str, object] | None,
) -> ChatStatus:
    if not result.success:
        return ChatStatus.INPUT_FAILED
    intent_decision = (graph_state or {}).get("intent_decision")
    if getattr(intent_decision, "intent_type", None) == "ambiguous":
        return ChatStatus.CLARIFICATION_REQUIRED
    return ChatStatus.COMPLETED


def _build_intent_summary(
    graph_state: dict[str, object] | None,
) -> ChatIntentSummary | None:
    intent_decision = (graph_state or {}).get("intent_decision")
    if intent_decision is None:
        return None
    intent_type = getattr(intent_decision, "intent_type", None)
    if intent_type is None:
        return None
    return ChatIntentSummary(
        type=str(intent_type),
        confidence_score=getattr(intent_decision, "confidence_score", None),
    )


def _build_assistant_message(
    graph_state: dict[str, object] | None,
) -> ChatMessage | None:
    messages = (graph_state or {}).get("messages")
    if not isinstance(messages, list):
        return None

    for message in reversed(messages):
        public_message = serialize_public_message(message)
        if public_message is not None and public_message.role == "assistant":
            fallback_text = (
                "I need a little more detail before I can help with that."
                if _intent_type(graph_state) == "ambiguous"
                else "I'm sorry, I could not generate a response."
            )
            return ChatMessage(
                role="assistant",
                content=_safe_public_text(
                    public_message.content,
                    fallback_text,
                ),
            )
    return None


def _intent_type(graph_state: dict[str, object] | None) -> str | None:
    intent_decision = (graph_state or {}).get("intent_decision")
    intent_type = getattr(intent_decision, "intent_type", None)
    if intent_type is None:
        return None
    return str(intent_type)


def _build_response_message(
    result: InputProcessingResult,
    graph_state: dict[str, object] | None = None,
) -> str:
    assistant_message = _build_assistant_message(graph_state)
    if assistant_message is not None:
        return assistant_message.content

    failed_statuses = [
        status
        for status in result.attachment_statuses
        if status.status == "failed" and status.error is not None
    ]
    if result.success and failed_statuses:
        return "Input processed with some attachment issues."
    if result.success:
        return "Input processed successfully."
    if len(failed_statuses) == 1:
        return failed_statuses[0].error.message
    return "Input could not be processed."


def _safe_public_text(text: str, fallback: str) -> str:
    unsafe_markers = ("Traceback", 'File "', "site-packages", "RuntimeError", "Exception")
    if any(marker in text for marker in unsafe_markers):
        return fallback
    return text


def _build_internal_error_payload() -> dict[str, object]:
    return jsonable_encoder(
        ChatResponse(
            success=False,
            status=ChatStatus.SYSTEM_ERROR,
            message="The input could not be processed safely.",
        )
    )


def _build_classification_error_payload() -> dict[str, object]:
    return jsonable_encoder(
        ChatResponse(
            success=False,
            status=ChatStatus.CLASSIFICATION_ERROR,
            message="The request could not be classified right now. Please try again.",
        )
    )
