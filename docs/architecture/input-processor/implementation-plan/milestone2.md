# Milestone 2 - Excel Extraction and Input Processor Integration

## Goal

Implement `.xlsx` processing end to end inside the Input Processor: parse visible worksheets, enforce configured bounds, mask PII at the cell level, build structured `SpreadsheetContent`, project spreadsheet content into `combined_text`, and prove mixed-modality behavior through tests and manual live-call verification.

## Scope

This milestone keeps spreadsheet work inside the Input Processor flow. The implementation may expose spreadsheet content through the already-approved `NormalizedInput` contract, but it must not change intent classification logic, retrieval behavior, response generation, memory storage, frontend upload UI, or graph routing. Uploaded workbooks remain request-scoped user content and must not become knowledge-base documents.

## Subtasks

### 1. Implement workbook validation and safe parser invocation

- Route validated `.xlsx` attachments from `processors.py` to the spreadsheet processor in deterministic attachment order.
- Open workbook bytes through the provider boundary without requiring filesystem paths.
- Reject parser failures as controlled attachment-scoped errors.
- Detect unsupported protected/encrypted workbooks where practical and return a safe failure.
- Ensure raw workbook bytes are discarded after processing and never placed into normalized output, graph state, logs, traces, or long-term memory.

Short description: This connects the router to the spreadsheet processor while preserving the same safe partial-success behavior used by images and PDFs.

### 2. Extract bounded visible worksheet content

- Process visible worksheets in workbook order.
- Enforce the maximum of five worksheets.
- Exclude hidden worksheets and do not intentionally include hidden rows or hidden columns.
- Preserve empty worksheets as valid structured sheets with an empty-sheet marker.
- Extract cells only within the configured 50-row by 50-column bounds.
- Preserve worksheet name, position, bounded dimensions, empty status, cell coordinates, row/column numbers, typed values, and safe warnings.
- Avoid materializing unbounded workbook matrices.

Short description: This makes extraction deterministic and resource-bounded. The processor should capture useful sheet structure without scanning the entire workbook.

### 3. Preserve formulas, cached values, merged ranges, and tables

- Store formula expressions as data and never execute or evaluate them.
- Preserve cached/displayed values separately when available and clearly mark missing cached values.
- Represent formula errors distinctly from normal strings where the parser exposes them.
- Preserve merged ranges such as `A1:C1`, including empty merged regions and anchor-cell values.
- Preserve Excel Table metadata where available: table name, reference/boundary, and column names.
- Avoid duplicating table content unnecessarily in `combined_text`.

Short description: This keeps spreadsheet semantics that matter for document reasoning while avoiding Excel execution or provider-specific leakage.

### 4. Apply cell-level bounding, PII masking, and untrusted-content marking

- Apply the 5,000-character textual cell limit deterministically.
- Mark truncated cells in structured output and add safe warnings using coordinates/counts, not raw values.
- Run PII masking after extraction and bounding, before normalized output is created.
- Mask values at the cell/value level while preserving coordinates, row/column relationships, table structure, and merged ranges.
- Treat instruction-like spreadsheet text as untrusted document data, not executable system or developer instructions.
- Do not reject ordinary government instructions merely because they contain words like "ignore", "instruction", or "system".

Short description: This is the privacy and prompt-boundary pass for spreadsheets. The output should remain useful while ensuring raw PII and workbook-originated instructions do not become control flow.

### 5. Build deterministic preview and combined-text projection

- Generate a deterministic spreadsheet preview without an LLM.
- Include workbook name, visible sheet names, bounded dimensions, empty-sheet status, and first-N row samples from each permitted visible sheet.
- Exclude hidden content from preview and `combined_text`.
- Add spreadsheet content to `combined_text` under a distinct section such as `<SPREADSHEET_CONTENT>`.
- Include workbook context, sheet names/order, row-column relationships, values, formulas/cached values, merged ranges, table metadata, empty-sheet markers, and safe limitation warnings.
- Ensure `combined_text` includes successful normalized content only and does not insert failed attachment error messages as document content.

Short description: This lets existing text-oriented downstream components receive spreadsheet context while preserving the structured spreadsheet contract for future richer use.

### 6. Integrate mixed-modality orchestration

- Extend the attachment processing tuple/result shape so images, PDFs, and spreadsheets can all return successful content independently.
- Preserve sequential multi-attachment processing and deterministic result order.
- Keep partial success behavior: a failed spreadsheet must not discard successful text, image, or PDF content.
- Treat spreadsheet-only requests as successful when at least one workbook yields usable normalized spreadsheet content, even when `user_query` is absent.
- Treat all-failed attachments with no usable text as `success=false`.
- Ensure existing image/PDF processors do not import or depend on spreadsheet code.

Short description: This folds Excel into the existing multimodal lane rather than creating a separate subsystem. The orchestrator remains a router and aggregator.

### 7. Add extraction, integration, and privacy tests

- Add extraction tests for strings, numbers, booleans, dates, blank cells, error cells, empty sheets, visible sheet order, hidden content exclusion, and deterministic cell ordering.
- Add structure tests for formulas, cached values, formula errors, merged ranges, table names, table references, and table headers.
- Add truncation tests for 4,999, 5,000, and 5,001-character values.
- Add preview and `combined_text` tests for determinism, bounded output, hidden-content exclusion, formula/cached-value labeling, empty-sheet markers, and warning projection.
- Add PII tests for ordinary cells and table cells, proving masked output and absence of raw PII from structured content and text projections.
- Add mixed-modality tests for text plus spreadsheet, image plus spreadsheet, PDF plus spreadsheet, all modalities together, spreadsheet-only input, spreadsheet failure with other successful content, and complete failure.
- Add failure tests for parser unavailable, provider exceptions, malformed provider output, corrupt workbook, worksheet extraction failure, PII failure, normalization failure, and unexpected exceptions.
- Add privacy/state tests proving raw workbook bytes, temporary paths, parser objects, and unmasked values do not enter graph-state updates.
- Run the full Input Processor test suite and then the broader `pytest` suite before handoff.

Short description: These tests prove the spreadsheet modality works on its own and in combination with existing modalities, while guarding privacy and compatibility.

### 8. Measure representative performance

- Measure small workbook processing latency.
- Measure five visible sheets at the configured row/column boundary.
- Measure formula-heavy, table-heavy, merged-range, long-cell, and PII-heavy workbooks.
- Record preview generation, normalization, combined-text generation, and end-to-end Input Processor latency.
- Do not introduce a hard spreadsheet-specific latency threshold until baseline data exists.

Short description: The limits should make performance predictable, but this milestone should collect real numbers before optimization decisions are made.

### 9. Complete manual live-call verification

- Start the backend path that exercises `InputRequest -> process_input -> InputProcessingResult`.
- The project owner uploads a `.xlsx` file of their choice.
- Verify the response/status shows successful spreadsheet processing or a controlled safe failure.
- Verify `NormalizedInput.spreadsheet_content` is populated for a valid workbook.
- Verify `combined_text` contains the spreadsheet projection.
- Verify hidden content is absent when the chosen workbook contains hidden sheets/rows/columns.
- Verify formula cells are represented as formula data and cached/displayed values are separate when available.
- Verify no raw bytes, parser objects, temporary paths, or unmasked PII appear in returned objects, logs, or graph-state updates.
- Repeat with at least one mixed-modality request if practical, such as text plus `.xlsx` or PDF plus `.xlsx`.

Short description: This is the final acceptance pass against a real user-selected workbook. It confirms the implementation behaves beyond synthetic fixtures.

## Milestone Checklist

- [ ] `.xlsx` attachments route through the Input Processor orchestrator to the spreadsheet processor.
- [ ] Workbook parsing works through a provider boundary and does not require permanent files.
- [ ] Five-sheet, 50-row, 50-column, and 5,000-character limits are enforced.
- [ ] Hidden sheets, hidden rows, and hidden columns are excluded from structured output, preview, and `combined_text`.
- [ ] Empty worksheets are represented without causing extraction failure.
- [ ] Formulas and cached/displayed values are preserved separately without execution.
- [ ] Merged ranges and Excel Table metadata are preserved.
- [ ] PII is masked at the cell/value level before normalized output is created.
- [ ] Instruction-like cell content remains untrusted data and does not affect processor control flow.
- [ ] Spreadsheet preview is deterministic, bounded, and non-LLM-generated.
- [ ] Spreadsheet content appears in `combined_text` without breaking image/PDF/text projections.
- [ ] Mixed-modality partial success works for text, image, PDF, and spreadsheet combinations.
- [ ] Complete failure returns `success=false` when no usable text or attachment content remains.
- [ ] Raw workbook bytes, temporary paths, parser objects, and unmasked PII do not enter `NormalizedInput`, graph state, logs, traces, memory, or knowledge storage.
- [ ] Provider, processor, validation, extraction, preview, mixed-modality, privacy, cleanup, failure, and regression tests pass.
- [ ] Representative performance measurements are recorded.
- [ ] Existing text, image, and PDF tests still pass.
- [ ] Manual live-call verification is completed by the project owner using a `.xlsx` file of their choice.

## Handoff Notes

- The spreadsheet processor must not make uploaded workbook content authoritative government knowledge. It is user-provided evidence for the current request.
- The implementation should not add frontend acceptance for `.xlsx` until backend validation and safe failure behavior are working.
- Any downstream use beyond normalized preview/combined text, such as upload-aware context building or citation presentation, belongs to a separate downstream milestone.
