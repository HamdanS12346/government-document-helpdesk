"""CLI boundary tests for the Input Processor."""

from app.contracts.normalized_input import ImageContent, NormalizedInput, PDFContent
from app.input_processing import cli
from app.input_processing.errors import InputProcessingErrorCode
from app.input_processing.schemas import (
    AttachmentProcessingError,
    AttachmentProcessingStatus,
    InputProcessingResult,
)


def test_cli_constructs_input_request_and_uses_public_processor(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    attachment_path = tmp_path / "sample.pdf"
    attachment_path.write_bytes(b"%PDF-1.4\nsynthetic bytes\n%%EOF")
    captured_requests = []

    def fake_process_input(request):
        captured_requests.append(request)
        return InputProcessingResult(
            success=True,
            normalized_input=NormalizedInput(
                user_query=request.user_query or "",
                image_content=[],
                pdf_content=[
                    PDFContent(
                        pdf_name="sample.pdf",
                        extracted_text="full extracted text should not print",
                        preview="safe pdf preview",
                    )
                ],
                combined_text="combined text should not print",
            ),
            attachment_statuses=[
                AttachmentProcessingStatus(filename="sample.pdf", status="success")
            ],
        )

    monkeypatch.setattr(cli, "process_input", fake_process_input)

    exit_code = cli.main(["--text", "Explain this.", "--file", str(attachment_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.user_query == "Explain this."
    assert len(request.attachments) == 1
    assert request.attachments[0].filename == "sample.pdf"
    assert request.attachments[0].media_type == "application/pdf"
    assert request.attachments[0].content == b"%PDF-1.4\nsynthetic bytes\n%%EOF"
    assert "Input Processor: success" in output
    assert "PDFs processed: 1" in output
    assert "safe pdf preview" in output
    assert "full extracted text should not print" not in output
    assert "combined text should not print" not in output


def test_cli_displays_failure_safely(monkeypatch, capsys) -> None:
    def fake_process_input(request):
        return InputProcessingResult(
            success=False,
            attachment_statuses=[
                AttachmentProcessingStatus(
                    filename="bad.pdf",
                    status="failed",
                    error=AttachmentProcessingError(
                        filename="bad.pdf",
                        code=InputProcessingErrorCode.SIGNATURE_MISMATCH,
                        message="The declared file type does not match the uploaded content.",
                    ),
                )
            ],
        )

    monkeypatch.setattr(cli, "process_input", fake_process_input)

    exit_code = cli.main(["--text", "   "])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "Input Processor: failed" in output
    assert "bad.pdf: failed (SIGNATURE_MISMATCH)" in output
    assert "traceback" not in output.lower()
    assert "C:\\" not in output


def test_cli_does_not_print_full_unmasked_extracted_document_text(
    monkeypatch,
    capsys,
) -> None:
    sensitive_tail = " PAN ABCDE1234F phone 9876543210"
    long_preview = ("safe preview text " * 20) + sensitive_tail

    def fake_process_input(request):
        return InputProcessingResult(
            success=True,
            normalized_input=NormalizedInput(
                user_query="",
                image_content=[
                    ImageContent(
                        image_name="form.png",
                        extracted_text=f"full text{long_preview}",
                        preview=long_preview,
                    )
                ],
                pdf_content=[],
                combined_text=f"full text{long_preview}",
            ),
            attachment_statuses=[
                AttachmentProcessingStatus(filename="form.png", status="success")
            ],
        )

    monkeypatch.setattr(cli, "process_input", fake_process_input)

    exit_code = cli.main(["--text", "Check this"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert len(output) < len(long_preview) + 200
    assert "ABCDE1234F" not in output
    assert "9876543210" not in output
    assert "full text" not in output
