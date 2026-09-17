# Input Processor Excel Integration Status

## Current Status

Milestone 1 is complete, and Milestone 2 tasks 1 through 16 are now implemented. The project has Excel/spreadsheet support wired from frontend upload through the backend Input Processor, graph handoff, and response-generation path. It includes bounded worksheet extraction, spreadsheet structure preservation, cell-level privacy/prompt-boundary handling, deterministic preview generation, `combined_text` projection, mixed-modality orchestration coverage, expanded extraction/privacy/failure tests, baseline spreadsheet performance measurements, a manual root runner for validating the real fixture workbook, frontend upload affordances that present `.xlsx` alongside PDF, PNG, and JPEG, normalized attachment status display for all supported upload modalities, frontend-safe attachment summaries derived from public response fields only, bounded spreadsheet preview context in intent classification queries, a typed public `/chat` attachment summary for frontend consumption, safe observability metadata for spreadsheet counts and limits, and focused frontend regression coverage for spreadsheet upload UX helper behavior.

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
- The frontend file picker accepts `.xlsx` uploads and sends them through the existing multipart `/chat` API path.
- The frontend composer hint/attach tooltip list `.xlsx`, and file chips distinguish spreadsheet, PDF, image, and generic file attachments by filename extension only.
- The chat UI renders backend `attachment_statuses` for assistant messages with filename, safe status labels, and sanitized failed-attachment details while preserving partial-success assistant responses.
- The chat UI derives modality/status counts from `attachment_statuses` only and does not render `NormalizedInput`, `combined_text`, spreadsheet previews, extracted cells, or PII-bearing workbook content in the transcript.
- Intent classification receives workbook names and bounded spreadsheet previews from `normalized_input.spreadsheet_content`, alongside image and PDF previews, without receiving raw workbook bytes, full structured spreadsheet dumps, or `combined_text`.
- The `/chat` response includes `attachment_summary` with safe counts by modality and processing outcome, so frontend rendering does not need to inspect `normalized_input`.
- Observability metadata includes spreadsheet upload/content counts, preview lengths, visible/processed/hidden sheet counts, and warning counts without adding spreadsheet preview text, cell values, raw workbook bytes, parser details, or internal paths.
- Frontend upload/status helper tests cover `.xlsx` acceptance copy, extension-aware attachment kinds, status labels, safe failed-status text, all-failed supported-type copy, spreadsheet-only summaries, mixed partial-success summaries, all-failed/skipped summaries, and empty response summaries.
- The response generator treats spreadsheet content as attachment context, so the final LLM prompt can see the user's query plus workbook preview/projection instead of only the typed text.
- `test.py` at the repository root runs the real `tests/input-processor/fixtures/spreadsheets/aadhar_update.xlsx` fixture through `process_input()` and prints the resulting `NormalizedInput`.

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
- Intent, RAG, memory, and graph routing logic remain unchanged. API upload forwarding, frontend file acceptance, and response-generation attachment context were updated so `.xlsx` content can work end to end.

### 6. Synthetic Fixture Strategy

Added spreadsheet fixture strategy docs:

- `tests/input-processor/fixtures/spreadsheets/README.md`

Added helper:

- `tests/input-processor/spreadsheet_fixture_helpers.py`

Current helper functions:

- `make_minimal_xlsx_package_bytes()`
- `make_incomplete_xlsx_package_bytes()`
- `make_corrupt_zip_like_xlsx_bytes()`
- `make_openpyxl_xlsx_bytes()`
- `make_structured_xlsx_bytes()`
- `make_privacy_xlsx_bytes()`
- `make_typed_values_xlsx_bytes()`
- `make_boundary_xlsx_bytes()`
- `make_formula_heavy_xlsx_bytes()`
- `make_table_heavy_xlsx_bytes()`
- `make_merged_range_heavy_xlsx_bytes()`

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

Frontend/API/response integration:

- `frontend/src/components/Composer.tsx`
- `frontend/src/hooks/useChat.ts`
- `app/api/routes.py`
- `app/response/generator.py`
- `test.py`

Tests:

- `tests/input-processor/test_schemas.py`
- `tests/input-processor/test_spreadsheet_settings.py`
- `tests/input-processor/test_validation.py`
- `tests/input-processor/test_processors.py`
- `tests/input-processor/test_excel_processor.py`
- `tests/input-processor/test_spreadsheet_fixtures.py`
- `tests/input-processor/test_privacy.py`
- `tests/input-processor/test_state_integration.py`
- `tests/input-processor/test_performance.py`
- `tests/api/test_chat.py`
- `tests/response/test_generator.py`

## Latest Test Results

Focused task 9/frontend and response integration checks:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\response\test_generator.py -q
.\.venv\Scripts\python.exe -m pytest tests\api\test_chat.py -q
.\.venv\Scripts\python.exe test.py
npm.cmd run lint
npm.cmd run build
```

Result:

```text
17 passed
39 passed
test.py printed NormalizedInput for aadhar_update.xlsx
frontend lint passed
frontend build passed
```

Task 10 frontend affordance check:

```powershell
npm.cmd run lint
```

Result:

```text
Failed on pre-existing frontend lint issues outside the Task 10 change:
- frontend/src/components/Sidebar.tsx react-hooks/set-state-in-effect
- frontend/src/components/RightPanel.tsx unused useState warning
- frontend/src/hooks/useChat.ts unused ChatApiResponse warning
```

Task 11 frontend attachment status check:

```powershell
npm.cmd run lint
```

Result:

```text
Failed on the same pre-existing frontend lint issues outside the Task 11 change:
- frontend/src/components/Sidebar.tsx react-hooks/set-state-in-effect
- frontend/src/components/RightPanel.tsx unused useState warning
- frontend/src/hooks/useChat.ts unused ChatApiResponse warning
```

Task 12 frontend-safe summary checks:

```powershell
npm.cmd run lint
rg -n "normalized_input|combined_text|spreadsheet_content|preview|extracted|cell" frontend/src -S
```

Result:

```text
Lint failed on the same pre-existing frontend issues outside the Task 12 change:
- frontend/src/components/Sidebar.tsx react-hooks/set-state-in-effect
- frontend/src/components/RightPanel.tsx unused useState warning
- frontend/src/hooks/useChat.ts unused ChatApiResponse warning

Frontend content scan found no transcript/UI rendering of normalized input, combined text, spreadsheet content, previews, extracted content, or cells. The only match was the opaque normalized_input field in frontend/src/lib/api.ts.
```

Task 13 intent spreadsheet preview checks:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_intent_classifier.py tests\test_input_intent_graph.py -q
```

Result:

```text
16 passed, 1 warning
```

Task 14 typed `/chat` response checks:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\api\test_chat.py -q
npm.cmd run lint
npm.cmd run build
```

Result:

```text
41 passed, 2 warnings

Frontend lint still failed on pre-existing issues outside the Task 14 changes:
- frontend/src/components/Sidebar.tsx react-hooks/set-state-in-effect
- frontend/src/components/RightPanel.tsx unused useState warning

Frontend build failed while fetching the Google Fonts Inter resource from fonts.googleapis.com through next/font. The build reached production compilation before the network/proxy font fetch failure.
```

Task 15 safe spreadsheet observability checks:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\observability\test_langfuse.py -q
.\.venv\Scripts\python.exe -m pytest tests\api\test_chat.py -q
```

Result:

```text
19 passed
41 passed, 2 warnings
```

Task 16 frontend regression checks:

```powershell
npm.cmd run test
npm.cmd exec tsc -- --noEmit
npm.cmd run lint
npm.cmd run build
```

Result:

```text
9 frontend tests passed. Node emitted a MODULE_TYPELESS_PACKAGE_JSON warning for the TypeScript test file, but the test run succeeded.
TypeScript check passed.

Frontend lint still failed on pre-existing issues outside the Task 16 changes:
- frontend/src/components/Sidebar.tsx react-hooks/set-state-in-effect
- frontend/src/components/RightPanel.tsx unused useState warning

Frontend build still failed while fetching the Google Fonts Inter resource from fonts.googleapis.com through next/font.
```

Focused backend integration checks:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\api tests\response tests\input-processor -q
```

Result:

```text
591 passed, 2 skipped
```

Skipped tests are existing scanned/mixed PDF integration checks that require real page-rendering provider support.

Full backend suite after the latest response-guardrail cleanup:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Result:

```text
977 passed, 2 skipped
```

## Milestone 2 Operating Notes

The Excel work is implemented against `docs/architecture/input-processor/implementation-plan/milestone2.md`. Current operating assumptions:

- The `NormalizedInput.spreadsheet_content` contract exists.
- `.xlsx` validation, routing, frontend file acceptance, and API upload forwarding already exist.
- `process_input()` can receive `spreadsheet_parser=...`.
- `excel_processor.py` owns spreadsheet parser/provider work.
- `processors.py` should remain orchestration only.
- The parser must not leak `openpyxl` objects into contracts.
- Raw workbook bytes must never enter `NormalizedInput`, graph state, logs, traces, memory, or vector/knowledge storage.
- Formula text is data only. Do not execute formulas, macros, VBA, external links, embedded commands, or cell-provided instructions.
- Hidden sheets, rows, and columns must be excluded from structured output, preview, combined text, warnings, logs, and telemetry.
- `combined_text` includes successful spreadsheet content under `<SPREADSHEET_CONTENT>`.
- Response generation uses `combined_text` when spreadsheet content is present, so uploaded workbook context reaches the final answer prompt.
- Spreadsheet-only requests can now succeed when at least one workbook produces `SpreadsheetContent`.
- Mixed requests with text, image, PDF, and spreadsheet attachments preserve deterministic attachment status order and successful content from each modality independently.
- Failed spreadsheet attachments do not discard successful text, image, or PDF content.

Recommended manual verification order:

1. Use the frontend to manually upload `tests/input-processor/fixtures/spreadsheets/aadhar_update.xlsx` or another owner-selected `.xlsx` workbook.
2. Confirm the `/chat` response contains populated `normalized_input.spreadsheet_content`.
3. Confirm `combined_text` contains `<SPREADSHEET_CONTENT>`.
4. Confirm the final assistant response uses the spreadsheet context.
5. Repeat with text plus `.xlsx` and one mixed-modality request if practical.

## Known Limitations After Milestone 2 Task 9

- `.xls`, `.xlsm`, CSV-as-spreadsheet, protected/encrypted workbooks, macros/VBA, and formula execution remain intentionally out of scope.
- Manual browser verification depends on local services and external LLM/network availability.
- Spreadsheet uploads are request-scoped user content only; they are not stored as knowledge-base documents.

## Commit Message Used/Suggested

```text
feat: add xlsx input processing
```
