"""Input Processor orchestration tests."""

from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter

from app.contracts.normalized_input import ImageContent, PDFContent
from app.input_processing import processors
from app.input_processing import pdf_processor
from app.input_processing.errors import InputProcessingErrorCode
from app.input_processing.image_processor import ImageProcessingResult
from app.input_processing.ocr_provider import OCRResult, OCRStatus
from app.input_processing.pdf_processor import (
    PDFClassificationResult,
    PDFDocumentType,
    PDFPageText,
    PDFProcessingResult,
)
from app.input_processing.processors import process_input
from app.input_processing.schemas import Attachment, InputRequest


FIXTURES = Path(__file__).parent / "fixtures"
VALID_IMAGE = FIXTURES / "images" / "valid" / "fictional_form.png"


class StaticOCRProvider:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    def extract_text(self, image_content: bytes) -> OCRResult:
        self.calls += 1
        assert image_content
        return OCRResult(status=OCRStatus.SUCCESS, text=self.text)


def make_pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def make_png_attachment(filename: str = "sample.png") -> Attachment:
    return Attachment(
        filename=filename,
        media_type="image/png",
        content=b"\x89PNG\r\n\x1a\nsynthetic image bytes",
    )


def make_jpeg_attachment(filename: str = "sample.jpg") -> Attachment:
    return Attachment(
        filename=filename,
        media_type="image/jpeg",
        content=b"\xff\xd8\xff\xe0synthetic image bytes",
    )


def make_pdf_attachment(filename: str = "sample.pdf") -> Attachment:
    return Attachment(
        filename=filename,
        media_type="application/pdf",
        content=make_pdf_bytes(),
    )


def expected_combined_text(
    *,
    user_query: str | None = None,
    image_texts: list[str] | None = None,
    pdf_texts: list[str] | None = None,
) -> str:
    parts = []
    if user_query and user_query.strip():
        parts.append(f"<USER_QUERY>\n{user_query}")
    if image_texts:
        image_text = "\n\n".join(image_texts)
        parts.append(f"<IMAGE_CONTENT>\n{image_text}")
    if pdf_texts:
        pdf_text = "\n\n".join(pdf_texts)
        parts.append(f"<PDF_CONTENT>\n{pdf_text}")
    return "\n\n".join(parts)


def test_process_input_rejects_empty_request_safely() -> None:
    result = process_input(InputRequest())

    assert result.success is False
    assert result.normalized_input is None
    assert len(result.attachment_statuses) == 1
    assert result.attachment_statuses[0].error is not None
    assert result.attachment_statuses[0].error.code == InputProcessingErrorCode.INVALID_INPUT
    assert result.attachment_statuses[0].error.message == (
        "Provide a question, an attachment, or both."
    )


def test_process_input_normalizes_text_only_request() -> None:
    result = process_input(InputRequest(user_query="What does this document mean?"))

    assert result.success is True
    assert result.normalized_input is not None
    assert result.normalized_input.user_query == "What does this document mean?"
    assert result.normalized_input.image_content == []
    assert result.normalized_input.pdf_content == []
    assert result.normalized_input.combined_text == expected_combined_text(
        user_query="What does this document mean?"
    )
    assert result.attachment_statuses == []


def test_process_input_processes_user_text_and_image_attachment() -> None:
    ocr_provider = StaticOCRProvider("Image document text")
    request = InputRequest(
        user_query="Please read this.",
        attachments=[
            Attachment(
                filename="fictional_form.png",
                media_type="image/png",
                content=VALID_IMAGE.read_bytes(),
            )
        ],
    )

    result = process_input(request, ocr_provider=ocr_provider)

    assert ocr_provider.calls == 1
    assert result.success is True
    assert result.normalized_input is not None
    assert result.normalized_input.image_content[0].image_name == "fictional_form.png"
    assert result.normalized_input.image_content[0].extracted_text == "Image document text"
    assert result.normalized_input.pdf_content == []
    assert result.normalized_input.combined_text == expected_combined_text(
        user_query="Please read this.",
        image_texts=["Image document text"],
    )
    assert result.attachment_statuses[0].status == "success"


def test_process_input_processes_user_text_and_pdf_attachment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_classify_pdf_content(pdf_content: bytes) -> PDFClassificationResult:
        assert pdf_content
        return PDFClassificationResult(
            document_type=PDFDocumentType.TEXT_BASED,
            pages=[PDFPageText(page_number=1, text="PDF document text")],
        )

    monkeypatch.setattr(pdf_processor, "classify_pdf_content", fake_classify_pdf_content)
    request = InputRequest(
        user_query="Please explain this.",
        attachments=[
            Attachment(
                filename="sample.pdf",
                media_type="application/pdf",
                content=make_pdf_bytes(),
            )
        ],
    )

    result = process_input(request)

    assert result.success is True
    assert result.normalized_input is not None
    assert result.normalized_input.image_content == []
    assert result.normalized_input.pdf_content[0].pdf_name == "sample.pdf"
    assert result.normalized_input.pdf_content[0].extracted_text == "PDF document text"
    assert result.normalized_input.combined_text == expected_combined_text(
        user_query="Please explain this.",
        pdf_texts=["PDF document text"],
    )
    assert result.attachment_statuses[0].status == "success"


def test_process_input_routes_png_jpeg_and_pdf_to_matching_processors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    routed_modalities: list[tuple[str, str]] = []

    def fake_process_image_attachment(validated_attachment, ocr_provider):
        routed_modalities.append(
            (validated_attachment.attachment.filename, validated_attachment.modality)
        )
        return ImageProcessingResult(
            image_content=ImageContent(
                image_name=validated_attachment.attachment.filename,
                extracted_text=f"{validated_attachment.attachment.filename} text",
                preview=f"{validated_attachment.attachment.filename} text",
            )
        )

    def fake_process_pdf_attachment(
        validated_attachment,
        pdf_extractor,
        *,
        ocr_provider=None,
        page_image_extractor=None,
    ):
        routed_modalities.append(
            (validated_attachment.attachment.filename, validated_attachment.modality)
        )
        return PDFProcessingResult(
            pdf_content=PDFContent(
                pdf_name=validated_attachment.attachment.filename,
                extracted_text=f"{validated_attachment.attachment.filename} text",
                preview=f"{validated_attachment.attachment.filename} text",
            )
        )

    monkeypatch.setattr(processors, "process_image_attachment", fake_process_image_attachment)
    monkeypatch.setattr(processors, "process_pdf_attachment", fake_process_pdf_attachment)

    result = process_input(
        InputRequest(
            attachments=[
                make_png_attachment("one.png"),
                make_jpeg_attachment("two.jpg"),
                make_pdf_attachment("three.pdf"),
            ]
        ),
        ocr_provider=StaticOCRProvider("unused"),
    )

    assert result.success is True
    assert routed_modalities == [
        ("one.png", "png"),
        ("two.jpg", "jpeg"),
        ("three.pdf", "pdf"),
    ]
    assert result.normalized_input is not None
    assert [content.image_name for content in result.normalized_input.image_content] == [
        "one.png",
        "two.jpg",
    ]
    assert [content.pdf_name for content in result.normalized_input.pdf_content] == [
        "three.pdf"
    ]


def test_process_input_processes_attachments_sequentially(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    def fake_process_image_attachment(validated_attachment, ocr_provider):
        events.append(validated_attachment.attachment.filename)
        return ImageProcessingResult(
            image_content=ImageContent(
                image_name=validated_attachment.attachment.filename,
                extracted_text=validated_attachment.attachment.filename,
                preview=validated_attachment.attachment.filename,
            )
        )

    monkeypatch.setattr(processors, "process_image_attachment", fake_process_image_attachment)

    result = process_input(
        InputRequest(
            attachments=[
                make_png_attachment("first.png"),
                make_jpeg_attachment("second.jpg"),
            ]
        ),
        ocr_provider=StaticOCRProvider("unused"),
    )

    assert result.success is True
    assert events == ["first.png", "second.jpg"]
    assert [status.filename for status in result.attachment_statuses] == [
        "first.png",
        "second.jpg",
    ]


def test_process_input_validates_each_attachment_independently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_calls: list[str] = []

    def fake_process_image_attachment(validated_attachment, ocr_provider):
        image_calls.append(validated_attachment.attachment.filename)
        return ImageProcessingResult(
            image_content=ImageContent(
                image_name=validated_attachment.attachment.filename,
                extracted_text="valid image text",
                preview="valid image text",
            )
        )

    monkeypatch.setattr(processors, "process_image_attachment", fake_process_image_attachment)

    result = process_input(
        InputRequest(
            attachments=[
                make_png_attachment("valid.png"),
                Attachment(
                    filename="bad.pdf",
                    media_type="application/pdf",
                    content=b"not a pdf",
                ),
            ]
        ),
        ocr_provider=StaticOCRProvider("unused"),
    )

    assert image_calls == ["valid.png"]
    assert result.success is True
    assert [status.status for status in result.attachment_statuses] == [
        "success",
        "failed",
    ]
    assert result.attachment_statuses[1].error is not None
    assert (
        result.attachment_statuses[1].error.code
        == InputProcessingErrorCode.SIGNATURE_MISMATCH
    )


def test_process_input_preserves_successful_content_when_attachment_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_process_image_attachment(validated_attachment, ocr_provider):
        return ImageProcessingResult(
            image_content=ImageContent(
                image_name=validated_attachment.attachment.filename,
                extracted_text="successful image text",
                preview="successful image text",
            )
        )

    monkeypatch.setattr(processors, "process_image_attachment", fake_process_image_attachment)

    result = process_input(
        InputRequest(
            attachments=[
                make_png_attachment("good.png"),
                Attachment(
                    filename="bad.gif",
                    media_type="image/gif",
                    content=b"GIF89a synthetic bytes",
                ),
            ]
        ),
        ocr_provider=StaticOCRProvider("unused"),
    )

    assert result.success is True
    assert result.normalized_input is not None
    assert result.normalized_input.image_content[0].extracted_text == (
        "successful image text"
    )
    assert result.normalized_input.combined_text == expected_combined_text(
        image_texts=["successful image text"]
    )
    assert [status.status for status in result.attachment_statuses] == [
        "success",
        "failed",
    ]


def test_process_input_keeps_failed_attachment_errors_out_of_combined_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_process_pdf_attachment(
        validated_attachment,
        pdf_extractor,
        *,
        ocr_provider=None,
        page_image_extractor=None,
    ):
        return PDFProcessingResult(
            pdf_content=PDFContent(
                pdf_name=validated_attachment.attachment.filename,
                extracted_text="successful pdf text",
                preview="successful pdf text",
            )
        )

    monkeypatch.setattr(processors, "process_pdf_attachment", fake_process_pdf_attachment)

    result = process_input(
        InputRequest(
            user_query="Please review these.",
            attachments=[
                Attachment(
                    filename="failed.png",
                    media_type="image/png",
                    content=b"not a png",
                ),
                make_pdf_attachment("good.pdf"),
            ],
        ),
        ocr_provider=StaticOCRProvider("unused"),
    )

    assert result.success is True
    assert result.normalized_input is not None
    assert result.attachment_statuses[0].error is not None
    failed_message = result.attachment_statuses[0].error.message
    assert result.normalized_input.combined_text == expected_combined_text(
        user_query="Please review these.",
        pdf_texts=["successful pdf text"],
    )
    assert failed_message not in result.normalized_input.combined_text
    assert "failed.png" not in result.normalized_input.combined_text
    assert "SIGNATURE_MISMATCH" not in result.normalized_input.combined_text


def test_process_input_returns_text_only_success_when_attachment_fails() -> None:
    result = process_input(
        InputRequest(
            user_query="What documents do I need?",
            attachments=[
                Attachment(
                    filename="bad.pdf",
                    media_type="application/pdf",
                    content=b"not a pdf",
                )
            ],
        )
    )

    assert result.success is True
    assert result.normalized_input is not None
    assert result.normalized_input.user_query == "What documents do I need?"
    assert result.normalized_input.image_content == []
    assert result.normalized_input.pdf_content == []
    assert result.normalized_input.combined_text == expected_combined_text(
        user_query="What documents do I need?"
    )
    assert result.attachment_statuses[0].status == "failed"
    assert result.attachment_statuses[0].error is not None
    assert (
        result.attachment_statuses[0].error.code
        == InputProcessingErrorCode.SIGNATURE_MISMATCH
    )


def test_process_input_attaches_safe_structured_errors_for_failed_attachments() -> None:
    result = process_input(
        InputRequest(
            attachments=[
                Attachment(
                    filename="bad.pdf",
                    media_type="application/pdf",
                    content=b"not a pdf",
                )
            ],
        )
    )

    assert result.success is False
    assert result.normalized_input is None
    assert len(result.attachment_statuses) == 1
    status = result.attachment_statuses[0]
    assert status.status == "failed"
    assert status.error is not None
    assert status.error.model_dump(mode="json") == {
        "filename": "bad.pdf",
        "code": "SIGNATURE_MISMATCH",
        "message": "The declared file type does not match the uploaded content.",
    }
    assert "traceback" not in status.error.message.lower()
    assert "C:\\" not in status.error.message
    assert "not a pdf" not in status.error.message


def test_process_input_returns_complete_failure_when_every_attachment_fails() -> None:
    result = process_input(
        InputRequest(
            attachments=[
                Attachment(
                    filename="bad-image.png",
                    media_type="image/png",
                    content=b"not a png",
                ),
                Attachment(
                    filename="bad-pdf.pdf",
                    media_type="application/pdf",
                    content=b"not a pdf",
                ),
            ],
        )
    )

    assert result.success is False
    assert result.normalized_input is None
    assert [status.status for status in result.attachment_statuses] == [
        "failed",
        "failed",
    ]
    assert all(status.error is not None for status in result.attachment_statuses)


def test_complete_failure_errors_do_not_expose_internal_or_document_content() -> None:
    raw_content = b"%PDF-1.4\nsynthetic private upload bytes\nmissing eof marker"
    result = process_input(
        InputRequest(
            attachments=[
                Attachment(
                    filename="private.pdf",
                    media_type="application/pdf",
                    content=raw_content,
                )
            ],
        )
    )

    assert result.success is False
    assert result.normalized_input is None
    payload = result.model_dump(mode="json")
    payload_text = str(payload)
    assert "traceback" not in payload_text.lower()
    assert "synthetic private upload bytes" not in payload_text
    assert str(raw_content) not in payload_text
    assert "C:\\" not in payload_text
    assert "site-packages" not in payload_text


def test_complete_failure_wraps_unexpected_processor_exception_safely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raising_process_image_attachment(validated_attachment, ocr_provider):
        raise RuntimeError("internal provider path C:\\tmp\\private-image.png")

    monkeypatch.setattr(
        processors,
        "process_image_attachment",
        raising_process_image_attachment,
    )

    result = process_input(
        InputRequest(attachments=[make_png_attachment("private-image.png")]),
        ocr_provider=StaticOCRProvider("unused"),
    )

    assert result.success is False
    assert result.normalized_input is None
    assert len(result.attachment_statuses) == 1
    status = result.attachment_statuses[0]
    assert status.error is not None
    assert status.error.code == InputProcessingErrorCode.INTERNAL_PROCESSING_ERROR
    assert status.error.message == "This attachment could not be processed safely."
    assert "C:\\tmp" not in status.error.message
    assert "provider path" not in status.error.message


def test_process_input_preserves_user_query_exactly_in_normalized_input() -> None:
    user_query = "  Please explain this form exactly as uploaded.  "

    result = process_input(InputRequest(user_query=user_query))

    assert result.success is True
    assert result.normalized_input is not None
    assert result.normalized_input.user_query == user_query
    assert result.normalized_input.combined_text == expected_combined_text(
        user_query=user_query
    )


def test_process_input_uses_empty_user_query_for_attachment_only_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_process_image_attachment(validated_attachment, ocr_provider):
        return ImageProcessingResult(
            image_content=ImageContent(
                image_name=validated_attachment.attachment.filename,
                extracted_text="attachment-only text",
                preview="attachment-only text",
            )
        )

    monkeypatch.setattr(processors, "process_image_attachment", fake_process_image_attachment)

    result = process_input(
        InputRequest(attachments=[make_png_attachment("attachment.png")]),
        ocr_provider=StaticOCRProvider("unused"),
    )

    assert result.success is True
    assert result.normalized_input is not None
    assert result.normalized_input.user_query == ""
    assert result.normalized_input.combined_text == expected_combined_text(
        image_texts=["attachment-only text"]
    )


def test_process_input_populates_only_successful_image_and_pdf_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_process_image_attachment(validated_attachment, ocr_provider):
        return ImageProcessingResult(
            image_content=ImageContent(
                image_name=validated_attachment.attachment.filename,
                extracted_text="image text",
                preview="image text",
            )
        )

    def fake_process_pdf_attachment(
        validated_attachment,
        pdf_extractor,
        *,
        ocr_provider=None,
        page_image_extractor=None,
    ):
        return PDFProcessingResult(
            pdf_content=PDFContent(
                pdf_name=validated_attachment.attachment.filename,
                extracted_text="pdf text",
                preview="pdf text",
            )
        )

    monkeypatch.setattr(processors, "process_image_attachment", fake_process_image_attachment)
    monkeypatch.setattr(processors, "process_pdf_attachment", fake_process_pdf_attachment)

    result = process_input(
        InputRequest(
            user_query="Question text",
            attachments=[
                make_png_attachment("good.png"),
                Attachment(
                    filename="bad.jpg",
                    media_type="image/jpeg",
                    content=b"not a jpeg",
                ),
                make_pdf_attachment("good.pdf"),
                Attachment(
                    filename="bad.pdf",
                    media_type="application/pdf",
                    content=b"not a pdf",
                ),
            ],
        ),
        ocr_provider=StaticOCRProvider("unused"),
    )

    assert result.success is True
    assert result.normalized_input is not None
    assert [content.image_name for content in result.normalized_input.image_content] == [
        "good.png"
    ]
    assert [content.pdf_name for content in result.normalized_input.pdf_content] == [
        "good.pdf"
    ]
    assert [status.status for status in result.attachment_statuses] == [
        "success",
        "failed",
        "success",
        "failed",
    ]


def test_process_input_builds_combined_text_from_user_query_images_and_pdfs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_process_image_attachment(validated_attachment, ocr_provider):
        return ImageProcessingResult(
            image_content=ImageContent(
                image_name=validated_attachment.attachment.filename,
                extracted_text="image extracted text",
                preview="image extracted text",
            )
        )

    def fake_process_pdf_attachment(
        validated_attachment,
        pdf_extractor,
        *,
        ocr_provider=None,
        page_image_extractor=None,
    ):
        return PDFProcessingResult(
            pdf_content=PDFContent(
                pdf_name=validated_attachment.attachment.filename,
                extracted_text="pdf extracted text",
                preview="pdf extracted text",
            )
        )

    monkeypatch.setattr(processors, "process_image_attachment", fake_process_image_attachment)
    monkeypatch.setattr(processors, "process_pdf_attachment", fake_process_pdf_attachment)

    result = process_input(
        InputRequest(
            user_query="user question",
            attachments=[
                make_png_attachment("image.png"),
                make_pdf_attachment("document.pdf"),
            ],
        ),
        ocr_provider=StaticOCRProvider("unused"),
    )

    assert result.success is True
    assert result.normalized_input is not None
    assert result.normalized_input.combined_text == expected_combined_text(
        user_query="user question",
        image_texts=["image extracted text"],
        pdf_texts=["pdf extracted text"],
    )
    assert not hasattr(result.normalized_input, "attachment_statuses")
    assert not hasattr(result.normalized_input, "raw_attachment_bytes")


def test_e2e_orchestration_text_only() -> None:
    result = process_input(InputRequest(user_query="Text only request"))

    assert result.success is True
    assert result.normalized_input is not None
    assert result.normalized_input.user_query == "Text only request"
    assert result.normalized_input.image_content == []
    assert result.normalized_input.pdf_content == []
    assert result.normalized_input.combined_text == expected_combined_text(
        user_query="Text only request"
    )


def test_e2e_orchestration_text_and_image(monkeypatch: pytest.MonkeyPatch) -> None:
    install_successful_attachment_processors(monkeypatch)

    result = process_input(
        InputRequest(
            user_query="Text plus image",
            attachments=[make_png_attachment("image.png")],
        ),
        ocr_provider=StaticOCRProvider("unused"),
    )

    assert result.success is True
    assert result.normalized_input is not None
    assert [content.image_name for content in result.normalized_input.image_content] == [
        "image.png"
    ]
    assert result.normalized_input.pdf_content == []
    assert result.normalized_input.combined_text == expected_combined_text(
        user_query="Text plus image",
        image_texts=["image.png text"],
    )


def test_e2e_orchestration_text_and_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    install_successful_attachment_processors(monkeypatch)

    result = process_input(
        InputRequest(
            user_query="Text plus PDF",
            attachments=[make_pdf_attachment("document.pdf")],
        ),
        ocr_provider=StaticOCRProvider("unused"),
    )

    assert result.success is True
    assert result.normalized_input is not None
    assert result.normalized_input.image_content == []
    assert [content.pdf_name for content in result.normalized_input.pdf_content] == [
        "document.pdf"
    ]
    assert result.normalized_input.combined_text == expected_combined_text(
        user_query="Text plus PDF",
        pdf_texts=["document.pdf text"],
    )


def test_e2e_orchestration_text_image_and_pdf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_successful_attachment_processors(monkeypatch)

    result = process_input(
        InputRequest(
            user_query="Full request",
            attachments=[
                make_png_attachment("image.png"),
                make_pdf_attachment("document.pdf"),
            ],
        ),
        ocr_provider=StaticOCRProvider("unused"),
    )

    assert result.success is True
    assert result.normalized_input is not None
    assert [content.image_name for content in result.normalized_input.image_content] == [
        "image.png"
    ]
    assert [content.pdf_name for content in result.normalized_input.pdf_content] == [
        "document.pdf"
    ]
    assert result.normalized_input.combined_text == expected_combined_text(
        user_query="Full request",
        image_texts=["image.png text"],
        pdf_texts=["document.pdf text"],
    )


def test_e2e_orchestration_image_and_pdf_without_user_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_successful_attachment_processors(monkeypatch)

    result = process_input(
        InputRequest(
            attachments=[
                make_png_attachment("image.png"),
                make_pdf_attachment("document.pdf"),
            ],
        ),
        ocr_provider=StaticOCRProvider("unused"),
    )

    assert result.success is True
    assert result.normalized_input is not None
    assert result.normalized_input.user_query == ""
    assert result.normalized_input.combined_text == expected_combined_text(
        image_texts=["image.png text"],
        pdf_texts=["document.pdf text"],
    )


def test_e2e_orchestration_multiple_images_and_multiple_pdfs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_successful_attachment_processors(monkeypatch)

    result = process_input(
        InputRequest(
            user_query="Many files",
            attachments=[
                make_png_attachment("one.png"),
                make_jpeg_attachment("two.jpg"),
                make_pdf_attachment("three.pdf"),
                make_pdf_attachment("four.pdf"),
            ],
        ),
        ocr_provider=StaticOCRProvider("unused"),
    )

    assert result.success is True
    assert result.normalized_input is not None
    assert [content.image_name for content in result.normalized_input.image_content] == [
        "one.png",
        "two.jpg",
    ]
    assert [content.pdf_name for content in result.normalized_input.pdf_content] == [
        "three.pdf",
        "four.pdf",
    ]
    assert result.normalized_input.combined_text == expected_combined_text(
        user_query="Many files",
        image_texts=["one.png text", "two.jpg text"],
        pdf_texts=["three.pdf text", "four.pdf text"],
    )


def test_e2e_orchestration_text_only_success_when_all_attachments_fail() -> None:
    result = process_input(
        InputRequest(
            user_query="Text survives",
            attachments=[
                Attachment(
                    filename="bad.png",
                    media_type="image/png",
                    content=b"not a png",
                ),
                Attachment(
                    filename="bad.pdf",
                    media_type="application/pdf",
                    content=b"not a pdf",
                ),
            ],
        )
    )

    assert result.success is True
    assert result.normalized_input is not None
    assert result.normalized_input.combined_text == expected_combined_text(
        user_query="Text survives"
    )
    assert [status.status for status in result.attachment_statuses] == [
        "failed",
        "failed",
    ]


def test_e2e_orchestration_complete_failure_when_no_usable_content_remains() -> None:
    result = process_input(
        InputRequest(
            attachments=[
                Attachment(
                    filename="bad.png",
                    media_type="image/png",
                    content=b"not a png",
                ),
                Attachment(
                    filename="bad.pdf",
                    media_type="application/pdf",
                    content=b"not a pdf",
                ),
            ],
        )
    )

    assert result.success is False
    assert result.normalized_input is None
    assert [status.status for status in result.attachment_statuses] == [
        "failed",
        "failed",
    ]


def install_successful_attachment_processors(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_process_image_attachment(validated_attachment, ocr_provider):
        filename = validated_attachment.attachment.filename
        return ImageProcessingResult(
            image_content=ImageContent(
                image_name=filename,
                extracted_text=f"{filename} text",
                preview=f"{filename} text",
            )
        )

    def fake_process_pdf_attachment(
        validated_attachment,
        pdf_extractor,
        *,
        ocr_provider=None,
        page_image_extractor=None,
    ):
        filename = validated_attachment.attachment.filename
        return PDFProcessingResult(
            pdf_content=PDFContent(
                pdf_name=filename,
                extracted_text=f"{filename} text",
                preview=f"{filename} text",
            )
        )

    monkeypatch.setattr(processors, "process_image_attachment", fake_process_image_attachment)
    monkeypatch.setattr(processors, "process_pdf_attachment", fake_process_pdf_attachment)


@pytest.mark.parametrize(
    (
        "case_id",
        "user_query",
        "attachments",
        "expected_success",
        "expected_combined_text",
        "expected_image_names",
        "expected_pdf_names",
        "expected_statuses",
    ),
    [
        (
            "MIX-001",
            "text only",
            [],
            True,
            expected_combined_text(user_query="text only"),
            [],
            [],
            [],
        ),
        (
            "MIX-002",
            "text plus image",
            [make_png_attachment("image.png")],
            True,
            expected_combined_text(
                user_query="text plus image",
                image_texts=["image.png text"],
            ),
            ["image.png"],
            [],
            ["success"],
        ),
        (
            "MIX-003",
            "text plus pdf",
            [make_pdf_attachment("document.pdf")],
            True,
            expected_combined_text(
                user_query="text plus pdf",
                pdf_texts=["document.pdf text"],
            ),
            [],
            ["document.pdf"],
            ["success"],
        ),
        (
            "MIX-004",
            "text plus both",
            [make_png_attachment("image.png"), make_pdf_attachment("document.pdf")],
            True,
            expected_combined_text(
                user_query="text plus both",
                image_texts=["image.png text"],
                pdf_texts=["document.pdf text"],
            ),
            ["image.png"],
            ["document.pdf"],
            ["success", "success"],
        ),
        (
            "MIX-005",
            None,
            [make_png_attachment("image.png"), make_pdf_attachment("document.pdf")],
            True,
            expected_combined_text(
                image_texts=["image.png text"],
                pdf_texts=["document.pdf text"],
            ),
            ["image.png"],
            ["document.pdf"],
            ["success", "success"],
        ),
        (
            "MIX-006",
            None,
            [make_png_attachment("image.png")],
            True,
            expected_combined_text(image_texts=["image.png text"]),
            ["image.png"],
            [],
            ["success"],
        ),
        (
            "MIX-007",
            None,
            [make_pdf_attachment("document.pdf")],
            True,
            expected_combined_text(pdf_texts=["document.pdf text"]),
            [],
            ["document.pdf"],
            ["success"],
        ),
        (
            "MIX-008",
            "text plus failed image plus pdf",
            [
                Attachment(
                    filename="failed.png",
                    media_type="image/png",
                    content=b"not a png",
                ),
                make_pdf_attachment("document.pdf"),
            ],
            True,
            expected_combined_text(
                user_query="text plus failed image plus pdf",
                pdf_texts=["document.pdf text"],
            ),
            [],
            ["document.pdf"],
            ["failed", "success"],
        ),
        (
            "MIX-009",
            "text plus failed files",
            [
                Attachment(
                    filename="failed.png",
                    media_type="image/png",
                    content=b"not a png",
                ),
                Attachment(
                    filename="failed.pdf",
                    media_type="application/pdf",
                    content=b"not a pdf",
                ),
            ],
            True,
            expected_combined_text(user_query="text plus failed files"),
            [],
            [],
            ["failed", "failed"],
        ),
        (
            "MIX-010",
            None,
            [
                Attachment(
                    filename="failed.png",
                    media_type="image/png",
                    content=b"not a png",
                ),
                Attachment(
                    filename="failed.pdf",
                    media_type="application/pdf",
                    content=b"not a pdf",
                ),
            ],
            False,
            None,
            [],
            [],
            ["failed", "failed"],
        ),
    ],
)
def test_full_mixed_input_matrix(
    case_id: str,
    user_query: str | None,
    attachments: list[Attachment],
    expected_success: bool,
    expected_combined_text: str | None,
    expected_image_names: list[str],
    expected_pdf_names: list[str],
    expected_statuses: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_successful_attachment_processors(monkeypatch)

    result = process_input(
        InputRequest(user_query=user_query, attachments=attachments),
        ocr_provider=StaticOCRProvider("unused"),
    )

    assert result.success is expected_success, case_id
    assert [status.status for status in result.attachment_statuses] == expected_statuses

    if expected_success:
        assert result.normalized_input is not None
        assert result.normalized_input.combined_text == expected_combined_text
        assert [
            content.image_name for content in result.normalized_input.image_content
        ] == expected_image_names
        assert [
            content.pdf_name for content in result.normalized_input.pdf_content
        ] == expected_pdf_names
    else:
        assert result.normalized_input is None
