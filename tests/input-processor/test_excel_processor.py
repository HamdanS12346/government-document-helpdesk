"""Spreadsheet parser boundary tests with deterministic provider outcomes."""

import pytest
from pydantic import ValidationError

from app.input_processing.errors import InputProcessingErrorCode
from app.input_processing.excel_processor import (
    ParsedWorkbook,
    ParsedWorksheet,
    PendingSpreadsheetParser,
    SpreadsheetInspectionResult,
    SpreadsheetInspectionStatus,
    SpreadsheetParser,
    SpreadsheetProcessingResult,
    inspect_spreadsheet_workbook,
    process_spreadsheet_attachment,
)
from app.input_processing.schemas import (
    Attachment,
    AttachmentProcessingError,
    InputModality,
    ValidatedAttachment,
)


def make_validated_xlsx() -> ValidatedAttachment:
    return ValidatedAttachment(
        attachment=Attachment(
            filename="applications.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            content=b"synthetic validated xlsx bytes",
        ),
        modality=InputModality.XLSX,
    )


class StaticSpreadsheetParser:
    def __init__(self, result: SpreadsheetInspectionResult) -> None:
        self.result = result
        self.calls = 0

    def inspect(self, content: bytes, filename: str) -> SpreadsheetInspectionResult:
        self.calls += 1
        assert content
        assert filename == "applications.xlsx"
        return self.result


class RaisingSpreadsheetParser:
    def __init__(self) -> None:
        self.calls = 0

    def inspect(self, content: bytes, filename: str) -> SpreadsheetInspectionResult:
        self.calls += 1
        raise RuntimeError("openpyxl internals should not leak")


class MalformedSpreadsheetParser:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls = 0

    def inspect(self, content: bytes, filename: str) -> object:
        self.calls += 1
        return self.result


def test_mock_provider_can_satisfy_spreadsheet_parser_interface() -> None:
    class MockSpreadsheetParser:
        def inspect(self, content: bytes, filename: str) -> SpreadsheetInspectionResult:
            assert content == b"workbook bytes"
            assert filename == "applications.xlsx"
            return SpreadsheetInspectionResult(
                status=SpreadsheetInspectionStatus.SUCCESS,
                workbook=ParsedWorkbook(
                    filename=filename,
                    worksheets=[
                        ParsedWorksheet(
                            name="Applicants",
                            position=1,
                            visible=True,
                            max_row=10,
                            max_column=4,
                        )
                    ],
                ),
            )

    parser: SpreadsheetParser = MockSpreadsheetParser()

    result = parser.inspect(b"workbook bytes", "applications.xlsx")

    assert result.status == SpreadsheetInspectionStatus.SUCCESS
    assert result.workbook is not None
    assert result.workbook.worksheets[0].name == "Applicants"


def test_pending_spreadsheet_parser_returns_controlled_unavailable_result() -> None:
    result = PendingSpreadsheetParser().inspect(
        b"workbook bytes",
        "applications.xlsx",
    )

    assert result == SpreadsheetInspectionResult(
        status=SpreadsheetInspectionStatus.UNAVAILABLE,
        message="Spreadsheet parser is not configured.",
    )


def test_inspect_spreadsheet_workbook_accepts_valid_provider_result() -> None:
    expected = SpreadsheetInspectionResult(
        status=SpreadsheetInspectionStatus.SUCCESS,
        workbook=ParsedWorkbook(
            filename="applications.xlsx",
            worksheets=[
                ParsedWorksheet(
                    name="Applicants",
                    position=1,
                    visible=True,
                    max_row=5,
                    max_column=2,
                )
            ],
        ),
    )
    parser = StaticSpreadsheetParser(expected)

    result = inspect_spreadsheet_workbook(
        content=b"workbook bytes",
        filename="applications.xlsx",
        parser=parser,
    )

    assert parser.calls == 1
    assert result == expected


def test_inspect_spreadsheet_workbook_returns_controlled_failure_for_exception() -> None:
    parser = RaisingSpreadsheetParser()

    result = inspect_spreadsheet_workbook(
        content=b"workbook bytes",
        filename="applications.xlsx",
        parser=parser,
    )

    assert parser.calls == 1
    assert result.status == SpreadsheetInspectionStatus.EXTRACTION_FAILURE
    assert result.message == "Spreadsheet content could not be inspected."
    assert "openpyxl" not in result.message


def test_inspect_spreadsheet_workbook_returns_controlled_failure_for_malformed_response() -> None:
    parser = MalformedSpreadsheetParser({"status": "success"})

    result = inspect_spreadsheet_workbook(
        content=b"workbook bytes",
        filename="applications.xlsx",
        parser=parser,
    )

    assert parser.calls == 1
    assert result.status == SpreadsheetInspectionStatus.MALFORMED_RESPONSE
    assert result.message == "Spreadsheet parser returned an invalid result."


def test_process_spreadsheet_attachment_returns_pending_parser_failure() -> None:
    result = process_spreadsheet_attachment(
        make_validated_xlsx(),
        PendingSpreadsheetParser(),
    )

    assert result.spreadsheet_content is None
    assert result.inspection_result is None
    assert result.error is not None
    assert result.error.code == InputProcessingErrorCode.EXTRACTION_FAILURE
    assert result.error.message == "Spreadsheet parser is not configured."


def test_process_spreadsheet_attachment_maps_unsupported_protection_safely() -> None:
    parser = StaticSpreadsheetParser(
        SpreadsheetInspectionResult(
            status=SpreadsheetInspectionStatus.UNSUPPORTED_PROTECTION,
            message="Protected or encrypted workbooks are not supported.",
        )
    )

    result = process_spreadsheet_attachment(make_validated_xlsx(), parser)

    assert result.error is not None
    assert result.error.code == InputProcessingErrorCode.UNSUPPORTED_WORKBOOK_PROTECTION
    assert result.error.message == "Protected or encrypted workbooks are not supported."


@pytest.mark.parametrize(
    ("status", "expected_code"),
    [
        (SpreadsheetInspectionStatus.TIMEOUT, InputProcessingErrorCode.EXTRACTION_FAILURE),
        (
            SpreadsheetInspectionStatus.CORRUPT_WORKBOOK,
            InputProcessingErrorCode.UNREADABLE_CONTENT,
        ),
        (
            SpreadsheetInspectionStatus.MALFORMED_RESPONSE,
            InputProcessingErrorCode.UNREADABLE_CONTENT,
        ),
    ],
)
def test_process_spreadsheet_attachment_maps_provider_failures_safely(
    status: SpreadsheetInspectionStatus,
    expected_code: InputProcessingErrorCode,
) -> None:
    parser = StaticSpreadsheetParser(
        SpreadsheetInspectionResult(
            status=status,
            message="Spreadsheet content could not be processed safely.",
        )
    )

    result = process_spreadsheet_attachment(make_validated_xlsx(), parser)

    assert result.error is not None
    assert result.error.code == expected_code
    assert result.error.message == "Spreadsheet content could not be processed safely."


def test_process_spreadsheet_attachment_rejects_non_xlsx_without_parser_call() -> None:
    parser = StaticSpreadsheetParser(
        SpreadsheetInspectionResult(
            status=SpreadsheetInspectionStatus.UNAVAILABLE,
            message="Spreadsheet parser is not configured.",
        )
    )
    validated = ValidatedAttachment(
        attachment=Attachment(
            filename="sample.pdf",
            media_type="application/pdf",
            content=b"%PDF-1.4",
        ),
        modality=InputModality.PDF,
    )

    result = process_spreadsheet_attachment(validated, parser)

    assert parser.calls == 0
    assert result.error is not None
    assert result.error.code == InputProcessingErrorCode.UNSUPPORTED_FORMAT


def test_spreadsheet_processing_result_requires_one_outcome() -> None:
    with pytest.raises(ValidationError, match="requires exactly one outcome field"):
        SpreadsheetProcessingResult()

    with pytest.raises(ValidationError, match="requires exactly one outcome field"):
        SpreadsheetProcessingResult(
            inspection_result=SpreadsheetInspectionResult(
                status=SpreadsheetInspectionStatus.UNAVAILABLE,
                message="Spreadsheet parser is not configured.",
            ),
            error=AttachmentProcessingError(
                filename="applications.xlsx",
                code=InputProcessingErrorCode.EXTRACTION_FAILURE,
                message="Spreadsheet parser is not configured.",
            ),
        )
