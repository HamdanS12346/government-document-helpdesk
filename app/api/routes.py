from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache
import logging
from typing import Annotated, Any

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.api.auth import AuthenticatedUser, get_optional_user, require_authenticated_user
from app.api.serialization import serialize_public_message
from app.config import get_settings
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
from app.memory import get_default_memory_manager
from app.memory.repository import get_default_memory_repository
from app.observability import flush_langfuse, start_observation
from app.observability.metadata import (
    build_chat_request_metadata,
    build_chat_graph_response_metadata,
    build_input_processing_result_metadata,
    build_input_request_metadata,
)


_DEFAULT_INVOKE_INTENT_RETRIEVER = invoke_intent_retriever_graph


router = APIRouter()


def _debug_print(*args: object, **kwargs: object) -> None:
    if get_settings().chat_debug_prints:
        print(*args, **kwargs)


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
    conversation_id: Annotated[str | None, Form()] = None,
    user: Annotated[AuthenticatedUser | None, Depends(get_optional_user)] = None,
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
                _debug_print(f"\n==================== Incoming Chat Request ====================", flush=True)
                _debug_print(f"Conversation ID: {conversation_id or '(none - starting new thread)'}", flush=True)
                _debug_print("\nNormalized input:", flush=True)
                _debug_print(result.normalized_input.model_dump_json(indent=2), flush=True)
                try:
                    user_id = user.id if user else None
                    graph_state = _invoke_chat_graph(
                        result,
                        conversation_id=conversation_id,
                        user_id=user_id,
                        memory_manager=get_default_memory_manager(),
                    )
                except Exception as exc:
                    logger.exception("Failed to invoke chat graph: %s", exc)
                    print(f"\n[ERROR] Chat graph invocation failed: {exc}", flush=True)
                    trace.update(output={"status": "classification_error"})
                    return JSONResponse(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        content=_build_classification_error_payload(),
                    )
                _debug_print("\nIntent decision:", flush=True)
                _debug_print(graph_state["intent_decision"].model_dump_json(indent=2), flush=True)
                response_status = _build_chat_status(result, graph_state)
                assistant_message = _build_assistant_message(graph_state)
                if assistant_message is not None:
                    _debug_print(
                        f"\n[Assistant response] (thread_id: {graph_state.get('thread_id')}):",
                        flush=True,
                    )
                    _debug_print(assistant_message.content, flush=True)
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
                _debug_print(result.model_dump_json(indent=2))
                trace.update(
                    output={
                        "status": "input_failed",
                        **build_input_processing_result_metadata(result),
                    }
                )
        except Exception as exc:
            logger.exception("Unhandled error in chat endpoint: %s", exc)
            print(f"\n[ERROR] Unhandled error in chat endpoint: {exc}", flush=True)
            trace.update(output={"status": "system_error"})
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=_build_internal_error_payload(),
            )
        finally:
            flush_langfuse()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=_build_response_payload(
            result,
            graph_state,
            conversation_id=conversation_id,
        ),
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
    conversation_id: str | None = None,
    user_id: str | None = None,
    memory_manager: Any | None = None,
    messages: Iterable[Any] | None = None,
    conversation_summary: str | None = None,
    clarification_round_count: int | None = None,
) -> dict[str, object]:
    """Invoke the chat graph with memory fields supplied by the API boundary."""

    memory_kwargs: dict[str, object] = {}
    if conversation_id is not None:
        memory_kwargs["thread_id"] = conversation_id
    if user_id is not None:
        memory_kwargs["user_id"] = user_id
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
        memory_manager=memory_manager,
        **memory_kwargs,
    )


def _build_response_payload(
    result: InputProcessingResult,
    graph_state: dict[str, object] | None = None,
    conversation_id: str | None = None,
) -> dict[str, object]:
    resolved_cid = (
        (graph_state or {}).get("thread_id")
        or conversation_id
    )
    response = ChatResponse(
        success=result.success,
        status=_build_chat_status(result, graph_state),
        message=_build_response_message(result, graph_state),
        assistant_message=_build_assistant_message(graph_state),
        attachment_statuses=result.attachment_statuses,
        warnings=result.warnings,
        normalized_input=result.normalized_input,
        intent=_build_intent_summary(graph_state),
        conversation_id=resolved_cid,
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


@router.get("/threads")
async def list_threads(
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> JSONResponse:
    """List all past conversation threads for the authenticated citizen."""
    repo = get_default_memory_repository()
    threads = repo.list_user_threads(user.id)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=[jsonable_encoder(t) for t in threads],
    )


@router.get("/threads/{thread_id}/messages")
async def get_thread_messages(
    thread_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> JSONResponse:
    """Fetch full transcript of messages for an owned conversation thread."""
    repo = get_default_memory_repository()
    thread = repo.get_thread(thread_id)
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation thread '{thread_id}' not found.",
        )
    if str(thread.user_id or "") != str(user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this conversation thread is denied.",
        )
    messages = repo.get_full_transcript(thread_id)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=[jsonable_encoder(m) for m in messages],
    )


@router.delete("/threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> JSONResponse:
    """Delete an owned conversation thread from history."""
    repo = get_default_memory_repository()
    thread = repo.get_thread(thread_id)
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation thread '{thread_id}' not found.",
        )
    if str(thread.user_id or "") != str(user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this conversation thread is denied.",
        )
    success = repo.delete_thread(thread_id, user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete conversation thread.",
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"success": True, "message": "Thread deleted successfully."},
    )

