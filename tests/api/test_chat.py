"""API boundary tests for frontend input processing."""

from fastapi.testclient import TestClient
import pytest

from app.api import routes
from app.api.main import app
from app.contracts.normalized_input import NormalizedInput
from app.input_processing.errors import InputProcessingErrorCode
from app.input_processing.schemas import (
    Attachment,
    AttachmentProcessingError,
    AttachmentProcessingStatus,
    InputProcessingResult,
    InputRequest,
)


def test_chat_allows_local_frontend_origin() -> None:
    client = TestClient(app)

    response = client.options(
        "/chat",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_chat_accepts_text_only_input() -> None:
    client = TestClient(app)

    response = client.post("/chat", data={"message": "Please explain this notice."})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["message"] == "Input processed successfully."
    assert payload["attachment_statuses"] == []
    assert payload["warnings"] == []
    assert payload["normalized_input"] == {
        "user_query": "Please explain this notice.",
        "image_content": [],
        "pdf_content": [],
        "combined_text": "<USER_QUERY>\nPlease explain this notice.",
    }


def test_chat_accepts_attachment_only_input(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_process_input(request: InputRequest) -> InputProcessingResult:
        assert request.user_query is None
        assert len(request.attachments) == 1
        assert request.attachments[0].filename == "notice.png"
        return InputProcessingResult(
            success=True,
            normalized_input=NormalizedInput(
                user_query="",
                image_content=[],
                pdf_content=[],
                combined_text="<IMAGE_CONTENT>\nAttachment text",
            ),
        )

    monkeypatch.setattr(routes, "process_input", fake_process_input)
    client = TestClient(app)

    response = client.post(
        "/chat",
        files=[("files", ("notice.png", b"\x89PNG\r\n\x1a\nimage", "image/png"))],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["message"] == "Input processed successfully."
    assert payload["normalized_input"]["user_query"] == ""
    assert payload["normalized_input"]["combined_text"] == "<IMAGE_CONTENT>\nAttachment text"


def test_chat_converts_uploads_to_attachment_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_request: InputRequest | None = None

    def fake_process_input(request: InputRequest) -> InputProcessingResult:
        nonlocal captured_request
        captured_request = request
        return InputProcessingResult(
            success=True,
            normalized_input=NormalizedInput(
                user_query="",
                image_content=[],
                pdf_content=[],
                combined_text="<IMAGE_CONTENT>\nAttachment text",
            ),
        )

    monkeypatch.setattr(routes, "process_input", fake_process_input)
    client = TestClient(app)

    response = client.post(
        "/chat",
        files=[
            (
                "files",
                ("notice.png", b"\x89PNG\r\n\x1a\nimage bytes", "image/png"),
            )
        ],
    )

    assert response.status_code == 200
    assert captured_request is not None
    assert len(captured_request.attachments) == 1
    attachment = captured_request.attachments[0]
    assert isinstance(attachment, Attachment)
    assert attachment.filename == "notice.png"
    assert attachment.media_type == "image/png"
    assert attachment.content == b"\x89PNG\r\n\x1a\nimage bytes"
    assert not isinstance(attachment.content, str)


def test_chat_preserves_multiple_uploaded_files_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_request: InputRequest | None = None

    def fake_process_input(request: InputRequest) -> InputProcessingResult:
        nonlocal captured_request
        captured_request = request
        return InputProcessingResult(
            success=True,
            normalized_input=NormalizedInput(
                user_query="",
                image_content=[],
                pdf_content=[],
                combined_text="<IMAGE_CONTENT>\nAttachment text",
            ),
        )

    monkeypatch.setattr(routes, "process_input", fake_process_input)
    client = TestClient(app)

    response = client.post(
        "/chat",
        files=[
            ("files", ("first.png", b"\x89PNG\r\n\x1a\nfirst", "image/png")),
            ("files", ("second.jpg", b"\xff\xd8\xff\xe0second", "image/jpeg")),
            ("files", ("third.pdf", b"%PDF-1.4\nthird", "application/pdf")),
        ],
    )

    assert response.status_code == 200
    assert captured_request is not None
    assert [
        attachment.filename for attachment in captured_request.attachments
    ] == [
        "first.png",
        "second.jpg",
        "third.pdf",
    ]
    assert [
        attachment.media_type for attachment in captured_request.attachments
    ] == [
        "image/png",
        "image/jpeg",
        "application/pdf",
    ]


def test_chat_accepts_mixed_image_and_pdf_attachments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_request: InputRequest | None = None

    def fake_process_input(request: InputRequest) -> InputProcessingResult:
        nonlocal captured_request
        captured_request = request
        return InputProcessingResult(
            success=True,
            normalized_input=NormalizedInput(
                user_query="Please review these.",
                image_content=[],
                pdf_content=[],
                combined_text="<USER_QUERY>\nPlease review these.",
            ),
        )

    monkeypatch.setattr(routes, "process_input", fake_process_input)
    client = TestClient(app)

    response = client.post(
        "/chat",
        data={"message": "Please review these."},
        files=[
            ("files", ("image.png", b"\x89PNG\r\n\x1a\nimage", "image/png")),
            ("files", ("document.pdf", b"%PDF-1.4\ndocument", "application/pdf")),
        ],
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert captured_request is not None
    assert captured_request.user_query == "Please review these."
    assert [
        (attachment.filename, attachment.media_type)
        for attachment in captured_request.attachments
    ] == [
        ("image.png", "image/png"),
        ("document.pdf", "application/pdf"),
    ]


def test_chat_returns_safe_input_processor_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_process_input(request: InputRequest) -> InputProcessingResult:
        return InputProcessingResult(
            success=False,
            attachment_statuses=[
                AttachmentProcessingStatus(
                    filename="document.pdf",
                    status="failed",
                    error=AttachmentProcessingError(
                        filename="document.pdf",
                        code=InputProcessingErrorCode.PDF_PAGE_LIMIT_EXCEEDED,
                        message="This PDF has too many pages. Upload a PDF with 5 pages or fewer.",
                    ),
                )
            ],
        )

    monkeypatch.setattr(routes, "process_input", fake_process_input)
    client = TestClient(app)

    response = client.post(
        "/chat",
        files=[("files", ("document.pdf", b"%PDF-1.4\ncontent", "application/pdf"))],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["message"] == (
        "This PDF has too many pages. Upload a PDF with 5 pages or fewer."
    )
    assert payload["normalized_input"] is None
    assert payload["attachment_statuses"] == [
        {
            "filename": "document.pdf",
            "status": "failed",
            "error": {
                "filename": "document.pdf",
                "code": "PDF_PAGE_LIMIT_EXCEEDED",
                "message": "This PDF has too many pages. Upload a PDF with 5 pages or fewer.",
            },
            "warnings": [],
        }
    ]
    response_text = response.text
    assert "Traceback" not in response_text
    assert "site-packages" not in response_text
    assert "content" not in response_text


def test_chat_hides_unexpected_exception_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raising_process_input(request: InputRequest) -> InputProcessingResult:
        raise RuntimeError("Traceback secret_token C:\\private\\provider.py")

    monkeypatch.setattr(routes, "process_input", raising_process_input)
    client = TestClient(app)

    response = client.post("/chat", data={"message": "hello"})

    assert response.status_code == 500
    assert response.json() == {
        "success": False,
        "message": "The input could not be processed safely.",
        "attachment_statuses": [],
        "warnings": [],
        "normalized_input": None,
    }
    response_text = response.text
    assert "Traceback" not in response_text
    assert "secret_token" not in response_text
    assert "C:\\private" not in response_text
    assert "provider.py" not in response_text
