# Milestone 1 - Excel Input Foundation

## Goal

Establish the `.xlsx` modality foundation inside the Input Processor without changing downstream workflow behavior. This milestone should make the system ready to recognize spreadsheet uploads, define the normalized contract, add the parser dependency decision, and prove validation/provider boundaries with focused tests before broad extraction logic is added.

## Scope

This milestone is limited to the Input Processor ownership area and its contracts/docs. Do not change intent, RAG, response, memory, frontend, or graph routing behavior. Any shared-contract touch, such as extending `NormalizedInput`, must be documented and reviewed because downstream nodes consume that object.

## Subtasks

### 1. Finalize the spreadsheet contract

- Define the final Pydantic models for `SpreadsheetContent`, `SpreadsheetSheet`, `SpreadsheetCell`, `SpreadsheetTable`, and spreadsheet metadata.
- Add `spreadsheet_content: list[SpreadsheetContent]` to `NormalizedInput` only after confirming the field name and serialization shape.
- Keep the models provider-independent: no `openpyxl` workbook, worksheet, cell, file handle, temporary path, or raw bytes may appear in the contract.
- Preserve current `user_query`, `image_content`, `pdf_content`, and `combined_text` behavior so existing modalities remain compatible.

Short description: This creates the stable data shape that leaves the Input Processor. The spreadsheet contract should hold bounded, masked, serializable workbook content while preserving the existing text/image/PDF contract.

### 2. Record dependency and configuration decisions

- Add `openpyxl` as the initial `.xlsx` parser candidate in the implementation decision notes and requirements update plan.
- Define centralized spreadsheet settings:
  - supported extension: `.xlsx`
  - maximum visible worksheets: 5
  - maximum rows per worksheet: 50
  - maximum columns per worksheet: 50
  - maximum textual cell characters: 5,000
  - preview sample size
- Make these limits injectable in tests rather than hard-coding values across the processor.
- Document that `.xls`, `.xlsm`, protected/encrypted workbooks, macros, VBA, formula execution, and long-term upload storage are outside the MVP.

Short description: This makes spreadsheet limits explicit before code depends on them. The future implementation should have one source of truth for workbook bounds and parser selection.

### 3. Extend modality validation for `.xlsx`

- Add an `XLSX` value to the input modality enum.
- Extend supported media-type handling for the accepted `.xlsx` MIME type while still requiring file-signature/package validation.
- Validate that an `.xlsx` upload is an Office Open XML ZIP package before parser extraction.
- Reject renamed or malformed files safely, including `.xls`, `.xlsm`, empty files, corrupt ZIP packages, and MIME/signature mismatches.
- Ensure validation happens before expensive workbook inspection or cell extraction.

Short description: This adds spreadsheet recognition at the same boundary used by images and PDFs. Validation must be cheap, deterministic, and safe before any workbook parser runs.

### 4. Define spreadsheet-safe error and warning categories

- Reuse existing safe error categories where they fit: `UNSUPPORTED_FORMAT`, `SIGNATURE_MISMATCH`, `FILE_TOO_LARGE`, `UNREADABLE_CONTENT`, `EXTRACTION_FAILURE`, `PII_PROCESSING_FAILURE`, and `INTERNAL_PROCESSING_ERROR`.
- Add spreadsheet-specific categories only if reuse would make failures unclear, such as worksheet limit exceeded or unsupported workbook protection.
- Define safe warnings for bounded processing, including row/column truncation, cell truncation, hidden content exclusion, unavailable cached formula values, optional table metadata failure, and partial worksheet extraction.
- Confirm that errors and warnings never echo raw cell values, unmasked PII, parser stack traces, internal paths, or raw workbook metadata beyond safe names/counts.

Short description: This keeps failures understandable without leaking workbook content. The future processor should be able to return partial success while still explaining limitations safely.

### 5. Introduce the parser provider boundary

- Create a narrow provider protocol conceptually shaped like `SpreadsheetParser.inspect(content: bytes, filename: str) -> ParsedWorkbook`.
- Keep provider output internal to `app/input_processing/excel_processor.py` or equivalent; normalize it before building public `SpreadsheetContent`.
- Add a pending/unavailable parser implementation if the dependency is not installed yet, mirroring the controlled failure style used for pending PDF extraction.
- Ensure the parser never executes formulas, macros, embedded commands, external links, or cell-provided instructions.

Short description: This isolates `openpyxl` behind an Input Processor boundary. Future parser replacement should not require graph, intent, or response changes.

### 6. Create synthetic workbook fixture strategy

- Add a fixture helper plan under the Input Processor test area for generating deterministic `.xlsx` files.
- Cover safe fictional data only; do not use real citizen records, credentials, or private documents.
- Prepare fixture groups for:
  - valid workbook
  - five-sheet boundary
  - six-sheet rejection
  - 50-row and 50-column boundaries
  - 51-row and 51-column behavior
  - empty workbook/sheet
  - hidden sheet, hidden row, hidden column
  - formulas with cached/displayed values where available
  - merged ranges
  - Excel Tables
  - long cells at 4,999, 5,000, and 5,001 characters
  - fictional PII
  - instruction-like cell content
  - corrupt or renamed non-spreadsheet bytes

Short description: This gives implementation a reliable test bed before complex normalization. Fixtures should prove behavior, privacy, and boundaries without depending on user files.

### 7. Add foundation tests

- Add schema tests for spreadsheet contract serialization and `NormalizedInput` compatibility.
- Add validation tests for `.xlsx` acceptance, unsupported workbook types, signature mismatches, empty/corrupt files, size limits, and validation-before-extraction.
- Add provider-contract tests using mocks for success, unavailable parser, malformed provider output, parser exceptions, and safe failure conversion.
- Add privacy tests proving raw workbook bytes and parser objects do not enter `NormalizedInput`, `combined_text`, or graph-state updates.
- Run existing Input Processor tests to confirm text, image, and PDF behavior remains unchanged.

Short description: These tests lock the foundation before extraction is implemented. The goal is to catch contract and validation regressions early.

## Milestone Checklist

- [ ] `SpreadsheetContent` and nested schema fields are finalized and documented.
- [ ] `NormalizedInput` spreadsheet extension is explicitly reviewed and backward compatible.
- [ ] `openpyxl` dependency decision and configuration limits are recorded.
- [ ] `.xlsx` modality validation is designed to check extension, MIME type, signature/package shape, and size before extraction.
- [ ] Unsupported `.xls`, `.xlsm`, protected/encrypted, corrupt, empty, and renamed files have safe failure behavior.
- [ ] Spreadsheet provider boundary is defined and does not leak parser-specific objects.
- [ ] Safe spreadsheet error/warning semantics are documented.
- [ ] Synthetic fixture plan exists for validation, structure, PII, prompt-injection-like content, and limits.
- [ ] Foundation tests are planned for schemas, validation, provider failures, privacy, and regression protection.
- [ ] Existing text, image, and PDF behavior is not changed by this milestone.
- [ ] No downstream intent, RAG, response, memory, frontend, or graph routing logic is modified.
- [ ] Manual live-call verification is scheduled: the project owner will upload a `.xlsx` file of their choice and confirm the system returns controlled validation/status output without raw workbook leakage.

## Handoff Notes

- This milestone does not need to answer spreadsheet questions yet. It prepares safe acceptance, contracts, dependency configuration, and provider boundaries.
- If the implementation cannot add `openpyxl` immediately, the parser should return a controlled unavailable outcome rather than crashing.
- Any contract update must be called out clearly in the PR because `NormalizedInput` is shared across workflow nodes.
