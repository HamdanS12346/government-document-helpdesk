# Milestone 5 - Orchestration, CLI, Integration Tests, and Readiness

## Goal
Connect schemas, guardrails, image processing, PDF processing, normalization, CLI execution, and integration tests into one complete Input Processor boundary.

## Scope Rules
* `processors.py` is the orchestrator/router only.
* Do not put OCR, PDF parsing, provider config, or image preprocessing logic in `processors.py`.
* Only `NormalizedInput` should leave the subsystem for graph state.
* Do not persist raw attachments.
* Do not add downstream RAG, intent, response, or final API behavior.

## Tasks

### Task 1 - Implement public processor entrypoint
* Accept `InputRequest`.
* Validate input presence.
* Process user text and attachments.
* Return `InputProcessingResult`.
* Keep API/frontend-specific upload objects outside this boundary.

### Task 2 - Implement sequential attachment orchestration
* Process attachments one by one.
* Validate each attachment independently.
* Route PNG/JPEG/JPG to `image_processor`.
* Route PDF to `pdf_processor`.
* Keep each attachment independently processable for future parallelization.

### Task 3 - Implement partial-success behavior
* Preserve successful image/PDF content when another attachment fails.
* Attach safe structured errors to failed attachments.
* Do not insert failed attachment errors into `combined_text`.
* Return overall success when usable text or at least one attachment result remains.

### Task 4 - Implement complete-failure behavior
* Return `success = false` when every attachment fails and no usable user text exists.
* Return a safe error without stack traces, internal paths, provider details, credentials, or document content.
* Ensure cleanup still occurs.

### Task 5 - Construct `NormalizedInput`
* Preserve `user_query` as supplied, or an empty string/defined value according to schema policy.
* Populate `image_content` with successful `ImageContent` only.
* Populate `pdf_content` with successful `PDFContent` only.
* Build `combined_text` from user query plus successful extracted content.
* Do not change the `NormalizedInput` contract.

### Task 6 - Integrate with graph state boundary
* Write only `normalized_input` into `GraphState`.
* Do not write raw attachment bytes, frontend upload objects, temporary paths, provider objects, or `InputProcessingResult` into graph state unless a future contract approves it.
* Confirm downstream nodes can use `NormalizedInput.user_query`, previews, and `combined_text`.

### Task 7 - Add CLI boundary
* Add a CLI path that constructs `InputRequest` from text and file inputs.
* Route through the same public Input Processor entrypoint.
* Display success/failure safely.
* Do not print full unmasked OCR/PDF content for production-like documents.
* Do not call `image_processor` or `pdf_processor` directly from CLI.

### Task 8 - Add end-to-end orchestration tests
* Test text only.
* Test text + image.
* Test text + PDF.
* Test text + image + PDF.
* Test image + PDF without user text.
* Test multiple images and multiple PDFs.
* Test text-only success when all attachments fail but user text is usable.
* Test complete failure when no usable content remains.

### Task 9 - Add full mixed-input matrix
* `MIX-001`: text only.
* `MIX-002`: text + image.
* `MIX-003`: text + PDF.
* `MIX-004`: text + image + PDF.
* `MIX-005`: image + PDF.
* `MIX-006`: image only.
* `MIX-007`: PDF only.
* `MIX-008`: text + failed image + successful PDF.
* `MIX-009`: text + failed image + failed PDF.
* `MIX-010`: failed image + failed PDF with no user text.

### Task 10 - Add state integration tests
* Verify `normalized_input` is written.
* Verify raw bytes are absent from graph state.
* Verify upload objects and temporary paths are absent.
* Verify `InputProcessingResult` does not leak into graph state unless explicitly approved.

### Task 11 - Add privacy and cleanup tests
* Verify raw uploads are absent from state, memory-like structures, logs/traces where applicable, and knowledge/vector stores.
* Verify cleanup after success, validation failure, OCR failure, PDF extraction failure, PII processing failure, and unexpected exception.
* Verify user uploads are not treated as authoritative knowledge-base documents.

### Task 12 - Add failure-injection tests
* Simulate OCR unavailable, timeout, exception, and malformed response.
* Simulate PDF provider unavailable, timeout, exception, and malformed response.
* Simulate PII detector unavailable/exception.
* Simulate invalid files, corrupt PDFs, unreadable images, and unexpected processor exceptions.
* Verify failure classification, partial/complete success behavior, cleanup, and privacy boundaries.

### Task 13 - Add performance measurement tests
* Measure validation, image OCR, PDF inspection, PDF extraction, PDF OCR, PII detection, normalization, and total Input Processor time.
* Include text-only, clear image, difficult image, text PDF, scanned PDF, mixed PDF, and multiple attachments.
* Do not invent hard per-modality thresholds until requirements are finalized.

### Task 14 - Add regression test process
* Add a location/naming pattern for regression tests.
* Convert discovered bugs into permanent deterministic fixtures.
* Include examples for missed form fields, empty scanned PDF output, mixed PDF page loss, raw upload entering state, PII trace leakage, legitimate instruction rejection, and injection-like content affecting routing.

### Task 15 - Final verification pass
* Run focused tests under `tests/input-processor/`.
* Run full `pytest`.
* Inspect `git diff`.
* Confirm no `.env`, raw private documents, large temp files, credentials, or unmasked PII fixtures are included.
* Confirm docs and tests explicitly keep unresolved decisions marked TBD.

## Files Expected
* `app/input_processing/processors.py`
* `app/input_processing/schemas.py`
* `app/input_processing/errors.py`
* `app/input_processing/image_processor.py`
* `app/input_processing/pdf_processor.py`
* `app/input_processing/ocr_provider.py`
* `app/input_processing/preview.py`
* `guardrails/input_processor.py`
* `app/graph/state.py`
* CLI entrypoint chosen by the project structure
* `tests/input-processor/test_processors.py`
* `tests/input-processor/test_state_integration.py`
* `tests/input-processor/test_cli_boundary.py`
* `tests/input-processor/test_privacy.py`
* `tests/input-processor/test_cleanup.py`
* `tests/input-processor/test_failures.py`
* `tests/input-processor/test_performance.py`

## Test Fixtures To Complete
* All image fixtures from Milestone 3.
* All PDF fixtures from Milestone 4.
* Text fixtures for normal query, empty query, PII-like synthetic text, legitimate instructions, and injection-like content.
* Mixed request fixture definitions combining successful and failing attachments.
* Regression fixtures for every bug discovered during implementation.

## Exit Criteria
* The public Input Processor boundary works end to end.
* `NormalizedInput` is preserved exactly as the downstream contract.
* Partial success and complete failure behavior are correct.
* Image/PDF processors remain isolated.
* Guardrails enforce validation, PII handling, prompt-injection boundaries, privacy, and safe errors.
* CLI uses the same public boundary as future API integration.
* Graph state receives `normalized_input` only.
* Focused and full tests pass or any failures are clearly documented.
* No secrets, raw private documents, large generated files, or unsafe logs are committed.
