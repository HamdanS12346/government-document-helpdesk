"""Safe metadata builders for observability."""

from collections.abc import Iterable, Mapping
from typing import Any

from app.contracts.intent_decision import IntentDecision
from app.contracts.normalized_input import NormalizedInput
from app.config import get_settings
from app.input_processing.schemas import InputProcessingResult, InputRequest
from guardrails.input_processor import mask_pii_in_text


TEXT_PREVIEW_MAX_CHARS = 4000


def build_chat_request_metadata(
    message: str | None,
    files: Iterable[Any],
) -> dict[str, Any]:
    """Build safe request metadata without reading upload bytes."""

    file_list = list(files)
    media_types = [
        str(getattr(file, "content_type", "") or "application/octet-stream")
        for file in file_list
    ]
    metadata = {
        "route": "/chat",
        "environment": get_settings().app_env,
        "application": get_settings().app_name,
        "has_message": bool(message and message.strip()),
        "message_length": len(message or ""),
        "attachment_count": len(file_list),
        "attachment_media_types": media_types,
        "image_count": sum(
            1 for media_type in media_types if media_type.startswith("image/")
        ),
        "pdf_count": sum(
            1 for media_type in media_types if media_type == "application/pdf"
        ),
    }
    _add_text_preview(metadata, "message_preview", message or "")
    return metadata


def build_input_request_metadata(request: InputRequest) -> dict[str, Any]:
    """Build safe metadata from an Input Processor request."""

    media_types = [attachment.media_type for attachment in request.attachments]
    metadata = {
        "has_user_query": bool(request.user_query),
        "user_query_length": len(request.user_query or ""),
        "attachment_count": len(request.attachments),
        "image_count": sum(
            1 for media_type in media_types if media_type.startswith("image/")
        ),
        "pdf_count": sum(
            1 for media_type in media_types if media_type == "application/pdf"
        ),
        "media_types": media_types,
    }
    _add_text_preview(metadata, "user_query_preview", request.user_query or "")
    return metadata


def build_input_processing_result_metadata(
    result: InputProcessingResult,
) -> dict[str, Any]:
    """Build safe metadata from an Input Processor result."""

    normalized_input = result.normalized_input
    if normalized_input is None:
        normalized_metadata: dict[str, Any] = {
            "normalized_user_query_length": 0,
            "combined_text_length": 0,
            "image_content_count": 0,
            "pdf_content_count": 0,
            "image_preview_lengths": [],
            "pdf_preview_lengths": [],
        }
    else:
        normalized_metadata = {
            "normalized_user_query_length": len(normalized_input.user_query),
            "combined_text_length": len(normalized_input.combined_text),
            "image_content_count": len(normalized_input.image_content),
            "pdf_content_count": len(normalized_input.pdf_content),
            "image_preview_lengths": [
                len(image.preview) for image in normalized_input.image_content
            ],
            "pdf_preview_lengths": [
                len(pdf.preview) for pdf in normalized_input.pdf_content
            ],
        }
        _add_text_preview(
            normalized_metadata,
            "normalized_user_query_preview",
            normalized_input.user_query,
        )
        _add_text_preview(
            normalized_metadata,
            "combined_text_preview",
            normalized_input.combined_text,
        )
        _add_text_preview_list(
            normalized_metadata,
            "image_previews",
            [image.preview for image in normalized_input.image_content],
        )
        _add_text_preview_list(
            normalized_metadata,
            "pdf_previews",
            [pdf.preview for pdf in normalized_input.pdf_content],
        )

    metadata = {
        "success": result.success,
        "warning_count": len(result.warnings),
        "attachment_statuses": [
            {
                "filename": status.filename,
                "status": status.status,
                "error_code": status.error.code if status.error is not None else None,
                "warning_count": len(status.warnings),
            }
            for status in result.attachment_statuses
        ],
        **normalized_metadata,
    }
    return metadata


def build_graph_state_metadata(graph_state: Mapping[str, Any]) -> dict[str, Any]:
    """Build safe metadata from graph output state."""

    decision = graph_state.get("intent_decision")
    metadata: dict[str, Any] = {
        "has_intent_decision": decision is not None,
        "has_documents": "documents" in graph_state,
        "has_retrieved_context": "retrieved_context" in graph_state,
    }
    if decision is not None:
        metadata.update(
            {
                "intent_type": str(getattr(decision, "intent_type", "")),
                "confidence_score": getattr(decision, "confidence_score", None),
                "classification_query_length": len(
                    getattr(decision, "query", "") or ""
                ),
            }
        )
        _add_text_preview(
            metadata,
            "classification_query_preview",
            getattr(decision, "query", "") or "",
        )
    return metadata


def build_normalized_input_metadata(
    normalized_input: NormalizedInput,
    *,
    messages: Iterable[Any] | None = None,
    conversation_summary: str | None = None,
) -> dict[str, Any]:
    """Build safe metadata from normalized input and optional memory context."""

    message_list = list(messages or [])
    metadata = {
        "normalized_user_query_length": len(normalized_input.user_query),
        "combined_text_length": len(normalized_input.combined_text),
        "image_content_count": len(normalized_input.image_content),
        "pdf_content_count": len(normalized_input.pdf_content),
        "messages_count": len(message_list),
        "has_conversation_summary": bool(conversation_summary),
        "conversation_summary_length": len(conversation_summary or ""),
    }
    _add_text_preview(
        metadata,
        "normalized_user_query_preview",
        normalized_input.user_query,
    )
    _add_text_preview(
        metadata,
        "combined_text_preview",
        normalized_input.combined_text,
    )
    _add_text_preview(
        metadata,
        "conversation_summary_preview",
        conversation_summary or "",
    )
    return metadata


def build_intent_decision_metadata(decision: IntentDecision) -> dict[str, Any]:
    """Build safe metadata from an intent decision."""

    metadata = {
        "intent_type": str(decision.intent_type),
        "confidence_score": decision.confidence_score,
        "classification_query_length": len(decision.query),
    }
    _add_text_preview(metadata, "classification_query_preview", decision.query)
    return metadata


def build_documents_metadata(documents: Iterable[Any]) -> dict[str, Any]:
    """Build safe metadata from retrieved documents without document text."""

    document_list = list(documents or [])
    metadata = {
        "document_count": len(document_list),
        "document_ids": [_get_document_field(doc, "id") for doc in document_list],
        "parent_document_ids": [
            _get_metadata_field(doc, "document_id") for doc in document_list
        ],
        "document_names": [
            _get_metadata_field(doc, "document_name") for doc in document_list
        ],
        "scores": [_get_document_field(doc, "score") for doc in document_list],
    }
    _add_text_preview_list(
        metadata,
        "document_text_previews",
        [str(_get_document_field(doc, "text_content") or "") for doc in document_list],
    )
    return metadata


def build_query_rewrite_input_metadata(
    retrieval_input: str,
    *,
    used_combined_text: bool,
    messages: Iterable[Any] | None = None,
    conversation_summary: str | None = None,
    attachment_preview_count: int = 0,
) -> dict[str, Any]:
    """Build safe metadata for query rewriting."""

    metadata = {
        "retrieval_input_length": len(retrieval_input),
        "used_combined_text": used_combined_text,
        "messages_count": len(list(messages or [])),
        "has_conversation_summary": bool(conversation_summary),
        "conversation_summary_length": len(conversation_summary or ""),
        "attachment_preview_count": attachment_preview_count,
    }
    _add_text_preview(metadata, "retrieval_input_preview", retrieval_input)
    _add_text_preview(
        metadata,
        "conversation_summary_preview",
        conversation_summary or "",
    )
    return metadata


def build_query_rewrite_output_metadata(
    retrieval_input: str,
    rewritten_query: str,
) -> dict[str, Any]:
    """Build safe metadata for query rewrite output."""

    metadata = {
        "rewritten_query_length": len(rewritten_query),
        "query_changed": rewritten_query != retrieval_input,
    }
    _add_text_preview(metadata, "rewritten_query_preview", rewritten_query)
    return metadata


def build_retrieved_context_metadata(retrieved_context: Any) -> dict[str, Any]:
    """Build safe metadata from context builder output."""

    sources = list(getattr(retrieved_context, "sources", []) or [])
    formatted_context = getattr(retrieved_context, "formatted_context", "") or ""
    metadata = {
        "total_documents_retrieved": getattr(
            retrieved_context,
            "total_documents_retrieved",
            0,
        ),
        "documents_used": getattr(retrieved_context, "documents_used", 0),
        "source_count": len(sources),
        "source_chunk_ids": [getattr(source, "chunk_id", None) for source in sources],
        "source_document_names": [
            getattr(source, "document_name", None) for source in sources
        ],
        "has_relevant_documents": getattr(
            retrieved_context,
            "has_relevant_documents",
            False,
        ),
        "truncated": getattr(retrieved_context, "truncated", False),
        "fallback_applied": getattr(retrieved_context, "fallback_applied", False),
        "formatted_context_length": len(formatted_context),
    }
    _add_text_preview(metadata, "formatted_context_preview", formatted_context)
    return metadata


def _get_document_field(document: Any, field_name: str) -> Any:
    if isinstance(document, Mapping):
        return document.get(field_name)
    return getattr(document, field_name, None)


def _get_metadata_field(document: Any, field_name: str) -> Any:
    metadata = _get_document_field(document, "metadata")
    if isinstance(metadata, Mapping):
        return metadata.get(field_name)
    return getattr(metadata, field_name, None)


def _add_text_preview(metadata: dict[str, Any], key: str, text: str) -> None:
    if not get_settings().langfuse_capture_text or not text:
        return
    metadata[key] = _safe_text_preview(text)


def _add_text_preview_list(
    metadata: dict[str, Any],
    key: str,
    values: Iterable[str],
) -> None:
    if not get_settings().langfuse_capture_text:
        return
    previews = [_safe_text_preview(value) for value in values if value]
    if previews:
        metadata[key] = previews


def _safe_text_preview(text: str) -> str:
    masked = mask_pii_in_text(text).text
    if len(masked) <= TEXT_PREVIEW_MAX_CHARS:
        return masked
    return f"{masked[:TEXT_PREVIEW_MAX_CHARS]}... [truncated]"


__all__ = [
    "build_chat_request_metadata",
    "build_documents_metadata",
    "build_graph_state_metadata",
    "build_intent_decision_metadata",
    "build_input_processing_result_metadata",
    "build_input_request_metadata",
    "build_normalized_input_metadata",
    "build_query_rewrite_input_metadata",
    "build_query_rewrite_output_metadata",
    "build_retrieved_context_metadata",
    "TEXT_PREVIEW_MAX_CHARS",
]
