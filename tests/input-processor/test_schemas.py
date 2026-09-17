"""Schema contract tests for the Input Processor."""

import pytest
from pydantic import ValidationError

from app.contracts.normalized_input import (
    NormalizedInput,
    SpreadsheetCell,
    SpreadsheetContent,
    SpreadsheetMetadata,
    SpreadsheetSheet,
    SpreadsheetTable,
)
from app.input_processing.schemas import (
    Attachment,
    AttachmentProcessingError,
    AttachmentProcessingStatus,
    AttachmentProcessingWarning,
    InputModality,
    InputProcessingErrorCode,
    InputProcessingWarningCode,
    InputProcessingResult,
    InputRequest,
    ValidatedAttachment,
)


def test_attachment_accepts_transient_bytes() -> None:
    attachment = Attachment(
        filename="sample.pdf",
        media_type="application/pdf",
        content=b"%PDF-1.4",
    )

    assert attachment.filename == "sample.pdf"
    assert attachment.media_type == "application/pdf"
    assert attachment.content == b"%PDF-1.4"


@pytest.mark.parametrize(
    "payload",
    [
        {"media_type": "application/pdf", "content": b"%PDF-1.4"},
        {"filename": "sample.pdf", "content": b"%PDF-1.4"},
        {"filename": "sample.pdf", "media_type": "application/pdf"},
        {"filename": "", "media_type": "application/pdf", "content": b"%PDF-1.4"},
        {"filename": "sample.pdf", "media_type": " ", "content": b"%PDF-1.4"},
        {"filename": "sample.pdf", "media_type": "application/pdf", "content": b""},
    ],
)
def test_attachment_rejects_missing_or_empty_required_fields(payload: dict) -> None:
    with pytest.raises(ValidationError):
        Attachment.model_validate(payload)


def test_attachment_rejects_non_byte_content() -> None:
    with pytest.raises(ValidationError):
        Attachment(
            filename="sample.pdf",
            media_type="application/pdf",
            content="not bytes",
        )


def test_attachment_rejects_api_or_path_specific_fields() -> None:
    with pytest.raises(ValidationError):
        Attachment.model_validate(
            {
                "filename": "sample.pdf",
                "media_type": "application/pdf",
                "content": b"%PDF-1.4",
                "file_path": "C:/tmp/sample.pdf",
            }
        )


def test_input_request_accepts_text_only_request() -> None:
    request = InputRequest(user_query="What does this document mean?")

    assert request.user_query == "What does this document mean?"
    assert request.attachments == []


def test_input_request_accepts_attachment_only_request() -> None:
    attachment = Attachment(
        filename="sample.png",
        media_type="image/png",
        content=b"\x89PNG\r\n\x1a\n",
    )

    request = InputRequest(attachments=[attachment])

    assert request.user_query is None
    assert request.attachments == [attachment]


def test_input_request_normalizes_blank_user_query_to_absent() -> None:
    request = InputRequest(user_query="   ")

    assert request.user_query is None


def test_input_request_rejects_malformed_attachment_objects() -> None:
    with pytest.raises(ValidationError):
        InputRequest.model_validate(
            {
                "attachments": [
                    {
                        "filename": "sample.pdf",
                        "media_type": "application/pdf",
                        "content": b"%PDF-1.4",
                        "upload_file": object(),
                    }
                ]
            }
        )


def test_input_request_rejects_non_attachment_items() -> None:
    with pytest.raises(ValidationError):
        InputRequest.model_validate({"attachments": [b"%PDF-1.4"]})


def test_validated_attachment_captures_supported_modality() -> None:
    attachment = Attachment(
        filename="sample.jpeg",
        media_type="image/jpeg",
        content=b"\xff\xd8\xff\xe0synthetic image bytes",
    )

    validated = ValidatedAttachment(
        attachment=attachment,
        modality=InputModality.JPEG,
    )

    assert validated.attachment == attachment
    assert validated.modality == InputModality.JPEG


def make_normalized_input() -> NormalizedInput:
    return NormalizedInput(
        user_query="What does this mean?",
        image_content=[],
        pdf_content=[],
        combined_text="What does this mean?",
    )


def make_spreadsheet_content() -> SpreadsheetContent:
    return SpreadsheetContent(
        workbook_name="applications.xlsx",
        sheets=[
            SpreadsheetSheet(
                name="Applicants",
                position=1,
                max_row=2,
                max_column=3,
                is_empty=False,
                cells=[
                    SpreadsheetCell(
                        coordinate="A1",
                        row=1,
                        column=1,
                        value="Applicant",
                        value_type="string",
                    ),
                    SpreadsheetCell(
                        coordinate="B2",
                        row=2,
                        column=2,
                        value=42,
                        value_type="number",
                    ),
                    SpreadsheetCell(
                        coordinate="C2",
                        row=2,
                        column=3,
                        value=None,
                        value_type="formula",
                        formula="=SUM(B2:B2)",
                        cached_value=42,
                    ),
                ],
                merged_ranges=["A1:C1"],
                tables=[
                    SpreadsheetTable(
                        name="ApplicantTable",
                        reference="A1:C2",
                        columns=["Applicant", "Count", "Total"],
                    )
                ],
            )
        ],
        preview="Workbook: applications.xlsx\nSheet: Applicants",
        warnings=["Hidden sheets were excluded."],
        metadata=SpreadsheetMetadata(
            workbook_name="applications.xlsx",
            processed_sheet_count=1,
            total_visible_sheet_count=1,
            hidden_sheet_count=0,
            max_sheets=5,
            max_rows_per_sheet=50,
            max_columns_per_sheet=50,
            max_text_cell_characters=5000,
            preview_row_count=5,
        ),
    )


def test_spreadsheet_contract_serializes_provider_independent_content() -> None:
    spreadsheet = make_spreadsheet_content()

    payload = spreadsheet.model_dump(mode="json")

    assert payload["workbook_name"] == "applications.xlsx"
    assert payload["sheets"][0]["cells"][2]["formula"] == "=SUM(B2:B2)"
    assert payload["sheets"][0]["cells"][2]["cached_value"] == 42
    assert payload["sheets"][0]["tables"][0]["columns"] == [
        "Applicant",
        "Count",
        "Total",
    ]
    assert "raw_bytes" not in payload
    assert "file_path" not in payload
    assert "workbook_object" not in payload


def test_spreadsheet_contract_rejects_provider_specific_or_raw_fields() -> None:
    payload = make_spreadsheet_content().model_dump()
    payload["raw_bytes"] = b"PK\x03\x04"

    with pytest.raises(ValidationError):
        SpreadsheetContent.model_validate(payload)


def test_normalized_input_accepts_spreadsheet_content() -> None:
    normalized_input = NormalizedInput(
        user_query="Explain this sheet.",
        image_content=[],
        pdf_content=[],
        spreadsheet_content=[make_spreadsheet_content()],
        combined_text="<USER_QUERY>\nExplain this sheet.",
    )

    payload = normalized_input.model_dump(mode="json")

    assert payload["spreadsheet_content"][0]["workbook_name"] == "applications.xlsx"


def test_normalized_input_defaults_spreadsheet_content_for_existing_callers() -> None:
    normalized_input = make_normalized_input()

    assert normalized_input.spreadsheet_content == []


def test_input_processing_result_accepts_full_success() -> None:
    result = InputProcessingResult(
        success=True,
        normalized_input=make_normalized_input(),
        attachment_statuses=[
            AttachmentProcessingStatus(filename="sample.pdf", status="success")
        ],
    )

    assert result.success is True
    assert result.normalized_input is not None
    assert result.attachment_statuses[0].status == "success"


def test_input_processing_result_accepts_partial_success() -> None:
    error = AttachmentProcessingError(
        filename="bad.pdf",
        code=InputProcessingErrorCode.EXTRACTION_FAILURE,
        message="This attachment could not be processed.",
    )

    result = InputProcessingResult(
        success=True,
        normalized_input=make_normalized_input(),
        attachment_statuses=[
            AttachmentProcessingStatus(filename="good.pdf", status="success"),
            AttachmentProcessingStatus(
                filename="bad.pdf",
                status="failed",
                error=error,
            ),
        ],
    )

    assert result.success is True
    assert result.normalized_input is not None
    assert [status.status for status in result.attachment_statuses] == [
        "success",
        "failed",
    ]


def test_input_processing_result_accepts_complete_failure() -> None:
    error = AttachmentProcessingError(
        filename="bad.pdf",
        code=InputProcessingErrorCode.UNREADABLE_CONTENT,
        message="No readable content could be extracted from this attachment.",
    )

    result = InputProcessingResult(
        success=False,
        attachment_statuses=[
            AttachmentProcessingStatus(
                filename="bad.pdf",
                status="failed",
                error=error,
            )
        ],
    )

    assert result.success is False
    assert result.normalized_input is None


def test_successful_result_requires_normalized_input() -> None:
    with pytest.raises(ValidationError):
        InputProcessingResult(success=True)


def test_failed_result_rejects_normalized_input() -> None:
    with pytest.raises(ValidationError):
        InputProcessingResult(
            success=False,
            normalized_input=make_normalized_input(),
        )


def test_failed_attachment_status_requires_error() -> None:
    with pytest.raises(ValidationError):
        AttachmentProcessingStatus(filename="bad.pdf", status="failed")


def test_successful_attachment_status_rejects_error() -> None:
    with pytest.raises(ValidationError):
        AttachmentProcessingStatus(
            filename="good.pdf",
            status="success",
            error=AttachmentProcessingError(
                filename="good.pdf",
                code=InputProcessingErrorCode.UNSUPPORTED_FORMAT,
                message="This file type is not supported.",
            ),
        )


def test_attachment_processing_status_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        AttachmentProcessingStatus(filename="sample.pdf", status="pending")


def test_result_warnings_are_safe_structured_objects() -> None:
    warning = AttachmentProcessingWarning(
        filename="sample.pdf",
        code="LOW_TEXT_CONTENT",
        message="Only limited text was extracted from this attachment.",
    )

    result = InputProcessingResult(
        success=True,
        normalized_input=make_normalized_input(),
        warnings=[warning],
    )

    assert result.warnings == [warning]


def test_input_processing_result_rejects_raw_or_debug_fields() -> None:
    with pytest.raises(ValidationError):
        InputProcessingResult.model_validate(
            {
                "success": True,
                "normalized_input": make_normalized_input(),
                "raw_attachment_bytes": b"%PDF-1.4",
            }
        )


def test_error_taxonomy_includes_required_categories() -> None:
    required_codes = {
        "INVALID_INPUT",
        "UNSUPPORTED_FORMAT",
        "SIGNATURE_MISMATCH",
        "FILE_TOO_LARGE",
        "PDF_PAGE_LIMIT_EXCEEDED",
        "SPREADSHEET_WORKSHEET_LIMIT_EXCEEDED",
        "UNSUPPORTED_WORKBOOK_PROTECTION",
        "OCR_FAILURE",
        "EXTRACTION_FAILURE",
        "UNREADABLE_CONTENT",
        "PII_PROCESSING_FAILURE",
        "SAFETY_REJECTION",
        "INTERNAL_PROCESSING_ERROR",
    }

    assert {code.value for code in InputProcessingErrorCode} == required_codes


def test_warning_taxonomy_includes_spreadsheet_safe_categories() -> None:
    required_codes = {
        "LOW_TEXT_CONTENT",
        "SUSPICIOUS_INSTRUCTION",
        "SPREADSHEET_ROW_LIMIT_APPLIED",
        "SPREADSHEET_COLUMN_LIMIT_APPLIED",
        "SPREADSHEET_CELL_TRUNCATED",
        "SPREADSHEET_HIDDEN_CONTENT_EXCLUDED",
        "SPREADSHEET_CACHED_FORMULA_VALUE_UNAVAILABLE",
        "SPREADSHEET_TABLE_METADATA_UNAVAILABLE",
        "SPREADSHEET_PARTIAL_WORKSHEET_EXTRACTION",
    }

    assert {code.value for code in InputProcessingWarningCode} == required_codes


def test_spreadsheet_error_and_warning_messages_do_not_require_raw_content() -> None:
    error = AttachmentProcessingError(
        filename="applications.xlsx",
        code=InputProcessingErrorCode.SPREADSHEET_WORKSHEET_LIMIT_EXCEEDED,
        message="This workbook has too many visible worksheets.",
    )
    warning = AttachmentProcessingWarning(
        filename="applications.xlsx",
        code=InputProcessingWarningCode.SPREADSHEET_HIDDEN_CONTENT_EXCLUDED,
        message="Hidden spreadsheet content was excluded.",
    )

    payload_text = str(
        {
            "error": error.model_dump(mode="json"),
            "warning": warning.model_dump(mode="json"),
        }
    )

    assert "raw" not in payload_text.lower()
    assert "cell value" not in payload_text.lower()
    assert "traceback" not in payload_text.lower()
    assert "C:\\" not in payload_text


def test_attachment_processing_error_rejects_unknown_error_code() -> None:
    with pytest.raises(ValidationError):
        AttachmentProcessingError(
            filename="bad.pdf",
            code="PATH_LEAKING_DEBUG_ERROR",
            message="This attachment could not be processed.",
        )


def test_attachment_processing_error_is_structured_for_safe_display() -> None:
    error = AttachmentProcessingError(
        filename="bad.pdf",
        code=InputProcessingErrorCode.SIGNATURE_MISMATCH,
        message="The declared file type does not match the uploaded content.",
    )

    payload = error.model_dump(mode="json")

    assert payload == {
        "filename": "bad.pdf",
        "code": "SIGNATURE_MISMATCH",
        "message": "The declared file type does not match the uploaded content.",
    }
    assert "traceback" not in payload
    assert "path" not in payload
    assert "content" not in payload
