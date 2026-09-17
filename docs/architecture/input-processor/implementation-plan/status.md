# Input Processor Excel Integration Status

## Current Status

Milestone 1 is complete, and Milestone 2 tasks 1 through 8 are now implemented. The project has the Excel/spreadsheet foundation inside the Input Processor plus bounded worksheet extraction, spreadsheet structure preservation, cell-level privacy/prompt-boundary handling, deterministic preview generation, `combined_text` projection, mixed-modality orchestration coverage, expanded extraction/privacy/failure tests, and baseline spreadsheet performance measurements.

Current `.xlsx` behavior:

- `.xlsx` uploads are recognized during validation.
- Valid `.xlsx` package bytes route to the spreadsheet processor boundary.
- The default spreadsheet parser uses `openpyxl` through the provider boundary and opens workbook bytes in memory without permanent file paths.
- Valid workbooks are inspected for visible worksheet order, bounded dimensions, empty-sheet status, and bounded visible cells.
- Formula expressions, cached/displayed values when available, formula-like errors, merged ranges, and Excel Table metadata are preserved in provider-independent internal parser output.
- Textual cell values and formulas are bounded to the configured 5,000-character limit, marked when truncated, and masked for PII before they leave the spreadsheet parser boundary.
- Instruction-like spreadsheet cell text is retained as user-provided data and flagged as untrusted instead of being rejected or treated as processor instructions.
- Parser, corrupt workbook, protected workbook, and worksheet-limit failures return controlled attachment-scoped errors.
- If the user also provides usable text, the request can still succeed as text-only partial success.
- `NormalizedInput.spreadsheet_content` is populated for successfully processed `.xlsx` workbooks.
- Successful spreadsheet content is projected into `combined_text` under `<SPREADSHEET_CONTENT>`.

## Milestone 2 Performance Baseline

Task 8 added representative spreadsheet timing coverage without introducing hard spreadsheet-specific latency thresholds. The measurements below were recorded on this local development machine on 2026-09-17 using synthetic in-memory `.xlsx` workbooks and the existing `openpyxl` parser path.

| Case | Workbook inspection | Normalization | Preview generation | Combined-text generation | End-to-end Input Processor |
| --- | ---: | ---: | ---: | ---: | ---: |
| small workbook | 6.62 ms | 0.12 ms | 0.01 ms | 0.01 ms | 5.47 ms |
| five visible sheets at 50 x 50 | 342.50 ms | 30.45 ms | 0.67 ms | 2.38 ms | 352.00 ms |
| formula-heavy workbook | 8.29 ms | 4.01 ms | 0.04 ms | 0.05 ms | 11.71 ms |
| table-heavy workbook | 5.16 ms | 0.13 ms | 0.01 ms | 0.02 ms | 5.68 ms |
| merged-range-heavy workbook | 6.31 ms | 0.08 ms | 0.01 ms | 0.02 ms | 5.78 ms |
| long-cell workbook | 5.17 ms | 0.06 ms | 0.01 ms | 0.01 ms | 3.86 ms |
| PII-heavy workbook | 3.07 ms | 0.04 ms | 0.01 ms | 0.01 ms | 3.49 ms |

Baseline note:

- These values are informational and should be refreshed before making optimization or SLA decisions.
- The five-sheet 50 x 50 workbook is the current highest-cost representative case because it fills the configured visible sheet, row, and column boundaries.
- CI tests assert only that the timing stages are recorded and processing succeeds; they intentionally do not fail on elapsed time.

## Milestone 1 Completed Work

### 1. Spreadsheet Contract

Added provider-independent Pydantic models in `app/contracts/normalized_input.py`:

- `SpreadsheetContent`
- `SpreadsheetSheet`
- `SpreadsheetCell`
- `SpreadsheetTable`
- `SpreadsheetMetadata`

Extended `NormalizedInput` with:

```python
spreadsheet_content: list[SpreadsheetContent] = Field(default_factory=list)
```

Compatibility note:

- Existing callers that construct `NormalizedInput` without `spreadsheet_content` still work.
- Existing `user_query`, `image_content`, `pdf_content`, and `combined_text` behavior was preserved.
- Spreadsheet contract forbids provider/raw fields through `extra="forbid"`.

### 2. Dependency and Settings

Recorded parser dependency in `requirements.txt`:

```text
openpyxl>=3.1,<4
```

Added spreadsheet settings in `app/config/settings.py`:

- `spreadsheet_supported_extension = ".xlsx"`
- `spreadsheet_parser_package = "openpyxl"`
- `spreadsheet_max_visible_sheets = 5`
- `spreadsheet_max_rows_per_sheet = 50`
- `spreadsheet_max_columns_per_sheet = 50`
- `spreadsheet_max_text_cell_characters = 5000`
- `spreadsheet_preview_row_count = 5`

Environment override names:

```text
SPREADSHEET_SUPPORTED_EXTENSION
SPREADSHEET_PARSER_PACKAGE
SPREADSHEET_MAX_VISIBLE_SHEETS
SPREADSHEET_MAX_ROWS_PER_SHEET
SPREADSHEET_MAX_COLUMNS_PER_SHEET
SPREADSHEET_MAX_TEXT_CELL_CHARACTERS
SPREADSHEET_PREVIEW_ROW_COUNT
```

Out of scope for the MVP:

- `.xls`
- `.xlsm`
- protected/encrypted workbooks
- macros/VBA
- formula execution
- long-term upload storage

### 3. `.xlsx` Validation

Added `InputModality.XLSX` in `app/input_processing/schemas.py`.

Added spreadsheet validation support in `guardrails/input_processor.py`:

- accepted MIME type: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- required filename extension: `.xlsx`
- required ZIP signature
- required minimal OOXML workbook package parts:
  - `[Content_Types].xml`
  - `xl/workbook.xml`

Safe rejection now covers:

- `.xls`
- `.xlsm`
- `.csv` sent as spreadsheet MIME type
- renamed non-spreadsheet bytes
- corrupt ZIP-like bytes
- MIME/signature mismatches
- oversized files before signature/parser work

Validation happens before parser inspection.

### 4. Safe Error and Warning Categories

Added spreadsheet-specific error codes in `app/input_processing/errors.py`:

- `SPREADSHEET_WORKSHEET_LIMIT_EXCEEDED`
- `UNSUPPORTED_WORKBOOK_PROTECTION`

Added `InputProcessingWarningCode` with:

- `LOW_TEXT_CONTENT`
- `SUSPICIOUS_INSTRUCTION`
- `SPREADSHEET_ROW_LIMIT_APPLIED`
- `SPREADSHEET_COLUMN_LIMIT_APPLIED`
- `SPREADSHEET_CELL_TRUNCATED`
- `SPREADSHEET_HIDDEN_CONTENT_EXCLUDED`
- `SPREADSHEET_CACHED_FORMULA_VALUE_UNAVAILABLE`
- `SPREADSHEET_TABLE_METADATA_UNAVAILABLE`
- `SPREADSHEET_PARTIAL_WORKSHEET_EXTRACTION`

Rule:

- Spreadsheet errors and warnings must not include raw cell values, unmasked PII, parser stack traces, internal paths, raw workbook bytes, or sensitive workbook metadata beyond safe names/counts.

### 5. Parser Provider Boundary

Added `app/input_processing/excel_processor.py`.

Provider protocol:

```python
class SpreadsheetParser(Protocol):
    def inspect(self, content: bytes, filename: str) -> SpreadsheetInspectionResult:
        ...
```

Internal provider-independent models:

- `ParsedWorkbook`
- `ParsedWorksheet`
- `SpreadsheetInspectionStatus`
- `SpreadsheetInspectionResult`
- `SpreadsheetProcessingResult`

Pending parser:

- `PendingSpreadsheetParser` returns `SpreadsheetInspectionStatus.UNAVAILABLE`.
- The public error becomes `EXTRACTION_FAILURE: Spreadsheet parser is not configured.`

Current orchestration:

- `process_input()` accepts optional `spreadsheet_parser`.
- Validated `.xlsx` attachments route to `process_spreadsheet_attachment()`.
- The default `openpyxl` parser performs bounded internal visible-sheet and cell extraction, including formulas, cached/displayed values when available, merged ranges, Excel Table metadata, cell-level truncation, PII masking, and untrusted instruction-like text marking.
- Successful spreadsheet parser output is converted into `SpreadsheetContent` with deterministic preview text.
- Graph, intent, RAG, response, memory, API, and frontend logic were not changed.

### 6. Synthetic Fixture Strategy

Added spreadsheet fixture strategy docs:

- `tests/input-processor/fixtures/spreadsheets/README.md`

Added helper:

- `tests/input-processor/spreadsheet_fixture_helpers.py`

Current helper functions:

- `make_minimal_xlsx_package_bytes()`
- `make_incomplete_xlsx_package_bytes()`
- `make_corrupt_zip_like_xlsx_bytes()`

Fixture policy:

- Prefer generated workbook bytes in tests.
- Do not commit real citizen files, production exports, credentials, private data, or genuine PII.
- Commit binary `.xlsx` files only when real-parser compatibility requires it and the fixture is small, stable, and documented.

Planned fixture IDs:

- `XLSX-001` valid workbook
- `XLSX-002` five-sheet boundary
- `XLSX-003` six-sheet rejection
- `XLSX-004` 50-row boundary
- `XLSX-005` 50-column boundary
- `XLSX-006` 51-row behavior
- `XLSX-007` 51-column behavior
- `XLSX-008` empty workbook/sheet
- `XLSX-009` hidden sheet/row/column
- `XLSX-010` formulas with cached/displayed values where available
- `XLSX-011` merged ranges
- `XLSX-012` Excel Tables
- `XLSX-013` long cells at 4,999, 5,000, and 5,001 characters
- `XLSX-014` fictional PII-like values
- `XLSX-015` legitimate instruction-like content
- `XLSX-016` AI-directed instruction-like content treated as data
- `XLSX-017` corrupt or renamed non-spreadsheet bytes

### 7. Foundation Tests

Added or extended tests for:

- spreadsheet schema serialization
- `NormalizedInput` backward compatibility
- config defaults and environment overrides
- `.xlsx` MIME/extension/signature/package validation
- unsupported `.xls`/`.xlsm`/renamed/corrupt rejection
- validation-before-parser behavior
- provider protocol success/unavailable/malformed/exception/timeout/corrupt/protected-workbook outcomes
- raw workbook bytes and parser details excluded from results and graph state
- helper-generated spreadsheet bytes
- existing text/image/PDF behavior regression protection

## Important Files

Core code:

- `app/contracts/normalized_input.py`
- `app/contracts/__init__.py`
- `app/config/settings.py`
- `app/input_processing/schemas.py`
- `app/input_processing/errors.py`
- `app/input_processing/excel_processor.py`
- `app/input_processing/processors.py`
- `guardrails/input_processor.py`
- `requirements.txt`

Docs:

- `docs/architecture/schema/normalized_input.md`
- `docs/architecture/input-processor/README.md`
- `docs/architecture/input-processor/guardrails.md`
- `docs/architecture/input-processor/testing.md`
- `tests/input-processor/fixtures/README.md`
- `tests/input-processor/fixtures/spreadsheets/README.md`

Tests:

- `tests/input-processor/test_schemas.py`
- `tests/input-processor/test_spreadsheet_settings.py`
- `tests/input-processor/test_validation.py`
- `tests/input-processor/test_processors.py`
- `tests/input-processor/test_excel_processor.py`
- `tests/input-processor/test_spreadsheet_fixtures.py`
- `tests/input-processor/test_privacy.py`
- `tests/input-processor/test_state_integration.py`

## Latest Test Results

Focused task 7 foundation test run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\input-processor\test_schemas.py tests\input-processor\test_validation.py tests\input-processor\test_excel_processor.py tests\input-processor\test_processors.py tests\input-processor\test_privacy.py tests\input-processor\test_state_integration.py
```

Result:

```text
178 passed
```

Full Input Processor suite:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\input-processor
```

Result:

```text
477 passed, 2 skipped
```

Skipped tests are existing scanned/mixed PDF integration checks that require real page-rendering provider support.

## Milestone 2 Starting Point

Start with `docs/architecture/input-processor/implementation-plan/milestone2.md`.

Milestone 2 should assume:

- The `NormalizedInput.spreadsheet_content` contract exists.
- `.xlsx` validation and routing already exist.
- `process_input()` can receive `spreadsheet_parser=...`.
- `excel_processor.py` owns spreadsheet parser/provider work.
- `processors.py` should remain orchestration only.
- The parser must not leak `openpyxl` objects into contracts.
- Raw workbook bytes must never enter `NormalizedInput`, graph state, logs, traces, memory, or vector/knowledge storage.
- Formula text is data only. Do not execute formulas, macros, VBA, external links, embedded commands, or cell-provided instructions.
- Hidden sheets, rows, and columns must be excluded from structured output, preview, combined text, warnings, logs, and telemetry.
- `combined_text` includes successful spreadsheet content under `<SPREADSHEET_CONTENT>`.
- Spreadsheet-only requests can now succeed when at least one workbook produces `SpreadsheetContent`.
- Mixed requests with text, image, PDF, and spreadsheet attachments preserve deterministic attachment status order and successful content from each modality independently.
- Failed spreadsheet attachments do not discard successful text, image, or PDF content.

Recommended next implementation order:

1. Implement real `openpyxl`-backed parser inspection behind `SpreadsheetParser`.
2. Keep validation-before-parser behavior intact.
3. Convert provider workbook information into provider-independent internal models.
4. Enforce worksheet limits before broad extraction.
5. Add extraction fixtures using generated synthetic workbooks.
6. Continue with representative performance measurement from task 8.

## Known Limitations After Milestone 2 Task 7

- Representative performance measurements are still pending.
- No frontend `.xlsx` upload advertising yet.
- No manual live-call verification with owner-selected `.xlsx` yet.

## Commit Message Used/Suggested

```text
feat: add xlsx input foundation
```
