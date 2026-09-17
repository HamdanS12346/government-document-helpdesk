# Milestone 2 - Excel Extraction and Input Processor Integration

## Goal

Implement `.xlsx` processing end to end inside the Input Processor: parse visible worksheets, enforce configured bounds, mask PII at the cell level, build structured `SpreadsheetContent`, project spreadsheet content into `combined_text`, and prove mixed-modality behavior through tests and manual live-call verification.

## Scope

The original extraction work keeps spreadsheet parsing inside the Input Processor flow. The implementation may expose spreadsheet content through the already-approved `NormalizedInput` contract, but uploaded workbooks remain request-scoped user content and must not become knowledge-base documents.

As of the current status, Milestone 2 tasks 1 through 9 are implemented and `.xlsx` uploads are already wired through frontend upload acceptance, the FastAPI `/chat` multipart path, graph handoff, and response generation. The continuation tasks below plan the remaining frontend/API polish needed for spreadsheets to feel first-class and consistent with the existing text, image, and PDF modalities.

These integration tasks may update the frontend, API response presentation, intent query construction, observability metadata, and documentation. They should not change spreadsheet parsing rules, raw upload storage policy, retrieval knowledge-base behavior, or shared contracts unless the contract change is explicit and documented.

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

### 10. Align frontend upload affordances with all supported modalities

- Update the composer accept list and visible hint text so `.xlsx` is presented alongside PDF, PNG, and JPEG.
- Keep multi-file selection, attachment-only requests, and text-with-attachment requests working exactly as they do for images and PDFs.
- Make file chips extension-aware enough to distinguish spreadsheets from PDFs/images without parsing file contents in the browser.
- Keep client-side checks lightweight: filename/extension and user-facing hints only. Backend validation remains authoritative.
- Do not add workbook preview, worksheet parsing, PII detection, or spreadsheet validation logic to the frontend.

Short description: The frontend should clearly communicate that spreadsheets are supported while preserving the backend as the only trusted upload-processing boundary.

### 11. Normalize attachment status display across modalities

- Ensure successful, failed, and skipped attachment statuses are displayed consistently for image, PDF, and spreadsheet uploads.
- Show the filename and a safe status label for each attachment when the backend returns `attachment_statuses`.
- Surface backend-safe error messages for failed `.xlsx` uploads without exposing stack traces, parser details, temporary paths, raw cell values, or raw workbook metadata.
- Preserve partial-success behavior in the UI: if text/image/PDF content succeeds while a spreadsheet fails, the assistant response remains visible and the failed workbook is shown as an attachment issue.
- Update generic failure copy that currently lists only PDF, PNG, or JPEG so it also names XLSX.

Short description: Users should understand which attachment worked and which one failed without learning internal parser or infrastructure details.

### 12. Add frontend-safe modality summaries without exposing `NormalizedInput`

- Keep the raw `normalized_input` object hidden from the browser transcript by default.
- Add an optional derived UI summary from public response fields only, such as counts/statuses by modality.
- Treat spreadsheets as request-scoped uploaded evidence, not official government sources or saved knowledge-base documents.
- Do not display extracted cell contents, workbook previews, `combined_text`, or masked/unmasked PII in the normal chat UI.
- If a debug-only view is later required, gate it clearly behind local/dev configuration and keep it out of the default citizen experience.

Short description: The frontend can acknowledge spreadsheet processing without turning normalized private content into user-visible debug output.

### 13. Include spreadsheet previews in intent classification context

- Update `app/intent/query_builder.py` so `normalized_input.spreadsheet_content` previews are rendered into the classifier query alongside image and PDF previews.
- Use workbook names and deterministic previews only; do not pass raw workbook bytes, parser objects, temporary paths, or full structured workbook dumps to intent classification.
- Keep per-preview bounding consistent with `MAX_PREVIEW_LENGTH`.
- Add intent tests proving spreadsheet-only, text-plus-spreadsheet, and mixed-modality inputs produce classifier queries containing spreadsheet preview context.
- Update schema/workflow docs that still describe intent previews as image/PDF-only.

Short description: Spreadsheet-only uploads should route and clarify as naturally as image/PDF uploads because the classifier can see bounded spreadsheet context.

### 14. Tighten `/chat` response typing for frontend consumption

- Review `app/contracts/chat.py` and `frontend/src/lib/api.ts` together so the frontend type reflects all stable public fields returned by `/chat`.
- Keep `normalized_input` typed as opaque or remove it from normal UI consumption; frontend logic should rely on `status`, `message`, `assistant_message`, `attachment_statuses`, `warnings`, `intent`, and `conversation_id`.
- If modality counts are needed by the frontend, add a safe derived summary field rather than requiring the frontend to inspect `normalized_input`.
- Keep the stable `status` values unchanged unless a new value is deliberately added to the contract and tests/docs are updated.
- Add API tests for spreadsheet success, spreadsheet failure, and mixed partial-success payload shape.

Short description: The API boundary should give the frontend enough safe structured information to render state without coupling UI logic to internal normalized contracts.

### 15. Extend observability metadata for spreadsheet counts and limits

- Add spreadsheet counts to safe request/result metadata where image and PDF counts already exist.
- Record safe lengths/counts such as `spreadsheet_content_count`, `spreadsheet_preview_lengths`, visible sheet counts, and warning counts when available.
- Do not capture workbook contents, cell values, raw bytes, filenames containing sensitive values beyond existing filename policy, parser stack traces, or temporary paths.
- Ensure Langfuse/text-preview settings still mask PII and respect capture configuration.
- Add metadata tests covering spreadsheet uploads and mixed-modality uploads.

Short description: Operators should be able to see whether spreadsheet processing happened without logging the spreadsheet itself.

### 16. Add frontend regression tests for spreadsheet UX

- Add or update component tests for the composer accept list, hint text, spreadsheet file chip rendering, empty-submit prevention, duplicate-submit prevention, and multi-attachment selection.
- Add hook tests for `.xlsx` uploads, attachment-only sends, mixed image/PDF/spreadsheet sends, partial-success responses, all-failed responses, clarification responses, and backend-unavailable fallback.
- Verify UI fallback copy mentions XLSX wherever the user is told which attachment types are valid.
- Keep tests focused on browser behavior; do not duplicate backend workbook parser tests in the frontend.
- Run `npm.cmd run lint` and `npm.cmd run build` before handoff.

Short description: The frontend should have its own regression coverage for spreadsheet support without becoming a spreadsheet parser test suite.

### 17. Complete end-to-end manual browser verification

- Start FastAPI on `http://localhost:8000` and Next.js on `http://localhost:3000`.
- Upload a valid `.xlsx` from the browser with no typed text and confirm the request succeeds when workbook content is usable.
- Upload text plus `.xlsx` and confirm the assistant response uses the workbook context when relevant.
- Upload image plus PDF plus `.xlsx` and confirm attachment chips/statuses preserve deterministic order and partial-success behavior.
- Upload an invalid workbook, unsupported `.xls`/`.xlsm`, or renamed non-spreadsheet file and confirm the UI shows a controlled safe failure.
- Trigger an ambiguous spreadsheet request and confirm the clarification question is displayed as a normal assistant message.
- Confirm browser-visible output does not expose raw `NormalizedInput`, `combined_text`, extracted cells, raw PII, stack traces, temporary paths, or parser details.

Short description: This validates the actual citizen-facing path, not just backend fixtures.

### 18. Update integration documentation and handoff notes

- Update `docs/architecture/frontend/README.md` to list `.xlsx` as a supported upload type and describe the safe display policy.
- Update `README.md` if the local flow, accepted file types, or test commands change.
- Update `docs/architecture/schema/intent_decision.md`, `docs/architecture/state-flow.md`, and related input-processor docs if spreadsheet previews are now classifier context.
- Keep `docs/architecture/input-processor/implementation-plan/status.md` current as tasks are completed.
- Record exact backend and frontend test commands run at handoff.

Short description: Documentation should match the live frontend/API behavior so the next implementer does not have to rediscover integration assumptions.

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

## Frontend Integration Continuation Checklist

- [ ] Composer accept list, attach tooltip, and hint text include `.xlsx`.
- [ ] File chips visually distinguish spreadsheet attachments from image/PDF attachments without reading workbook contents.
- [ ] Attachment status rendering handles success, failed, and skipped states for spreadsheets.
- [ ] Generic failed-attachment and unsupported-type copy mentions XLSX where applicable.
- [ ] Frontend does not display raw `normalized_input`, `combined_text`, extracted cell contents, raw PII, stack traces, parser details, or temporary paths.
- [ ] Spreadsheet preview context is included in intent classification queries with bounded length.
- [ ] Intent/schema/workflow docs no longer describe attachment classification context as image/PDF-only.
- [ ] `/chat` public response fields are sufficient for frontend rendering without inspecting internal normalized contracts.
- [ ] Safe observability metadata includes spreadsheet counts/lengths without spreadsheet content.
- [ ] API tests cover spreadsheet success, spreadsheet failure, and mixed partial-success payloads.
- [ ] Frontend tests cover spreadsheet upload UX, hook response handling, partial success, all-failed responses, clarification, and backend-unavailable fallback.
- [ ] Manual browser verification covers spreadsheet-only, text-plus-spreadsheet, all-modalities, invalid workbook, and ambiguous spreadsheet requests.
- [ ] `npm.cmd run lint`, `npm.cmd run build`, focused backend tests, and relevant full-suite checks are recorded in `status.md`.

## Handoff Notes

- The spreadsheet processor must not make uploaded workbook content authoritative government knowledge. It is user-provided evidence for the current request.
- Frontend `.xlsx` acceptance must stay aligned with backend validation and safe failure behavior.
- Any downstream use beyond normalized preview/combined text, such as upload-aware context building or citation presentation, belongs to a separate downstream milestone.
