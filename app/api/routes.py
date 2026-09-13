"""HTTP routes for the FastAPI application."""

from dataclasses import dataclass
from functools import cache
from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.graph.graph import invoke_input_intent_graph
from app.input_processing.processors import process_input
from app.input_processing.schemas import Attachment, InputProcessingResult, InputRequest
from app.intent.classifier import OpenAIIntentClassifier


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
    try:
        uploaded_files = await _read_uploaded_files(files or [])
        attachments = _build_attachments(uploaded_files)
        request = InputRequest(user_query=message, attachments=attachments)
        result = process_input(request)
        if result.success and result.normalized_input is not None:
            print("Normalized input:", flush=True)
            print(result.normalized_input.model_dump_json(indent=2), flush=True)
            try:
                graph_state = invoke_input_intent_graph(
                    result,
                    _build_intent_classifier(),
                )
            except Exception:
                return JSONResponse(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    content=_build_classification_error_payload(),
                )
            print("\nIntent decision:", flush=True)
            print(graph_state["intent_decision"].model_dump_json(indent=2), flush=True)
        else:
            print(result.model_dump_json(indent=2))
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_build_internal_error_payload(),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=_build_response_payload(result),
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


def _build_response_payload(result: InputProcessingResult) -> dict[str, object]:
    return jsonable_encoder(
        {
            "success": result.success,
            "message": _build_response_message(result),
            "attachment_statuses": result.attachment_statuses,
            "warnings": result.warnings,
            "normalized_input": result.normalized_input,
        }
    )


def _build_response_message(result: InputProcessingResult) -> str:
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


def _build_internal_error_payload() -> dict[str, object]:
    return {
        "success": False,
        "message": "The input could not be processed safely.",
        "attachment_statuses": [],
        "warnings": [],
        "normalized_input": None,
    }


def _build_classification_error_payload() -> dict[str, object]:
    return {
        "success": False,
        "message": "The request could not be classified right now. Please try again.",
        "attachment_statuses": [],
        "warnings": [],
        "normalized_input": None,
    }
