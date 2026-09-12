# Milestone 4 - PDF Processor, Page Validation, and PDF Fixture Coverage

## Goal
Process supported PDFs through a replaceable PDF extraction boundary, including text-based, scanned, and mixed PDFs.

## Scope Rules
* Keep PDF-specific logic inside `app/input_processing/pdf_processor.py`.
* Keep Docling or any PDF provider behind an internal interface.
* Do not expose provider-specific objects through `InputProcessingResult` or `NormalizedInput`.
* Do not OCR machine-readable text unnecessarily.
* Do not treat mixed PDFs as unsupported.
* Enforce configured PDF page limit before expensive processing.

## Tasks

### Task 1 - Define PDF provider/extractor boundary
* Add an interface for PDF inspection/extraction.
* Support text, scanned, mixed, extraction failure, timeout/unavailable, malformed response, and corrupt PDF outcomes.
* Keep Docling as an implementation detail or pending provider if not finalized.

### Task 2 - Implement PDF page-count validation
* Count pages before running extraction/OCR.
* Use a single configurable page-limit value.
* Keep the 5-vs-10 page conflict explicit until resolved.
* Reject over-limit PDFs before Docling/OCR.

### Task 3 - Implement PDF classification
* Classify PDFs as:
  * text-based
  * scanned
  * mixed
* Keep classification internal to the PDF processor.
* Return controlled failures for corrupt or unreadable PDFs.

### Task 4 - Implement text-based PDF path
* Extract machine-readable text.
* Avoid unnecessary OCR for already-readable text.
* Apply PII masking and document-content safety.
* Build `PDFContent`.

### Task 5 - Implement scanned PDF path
* Render or extract page images as needed.
* Use `OCRProvider` at page level.
* Combine page-level OCR results deterministically.
* Handle unreadable pages without fabricating text.

### Task 6 - Implement mixed PDF path
* Extract machine-readable pages/regions through PDF extraction.
* OCR scanned pages/regions.
* Combine successful content in document order.
* Do not discard successful pages only because another page failed unless the final policy requires failure.

### Task 7 - Implement PDF preview behavior
* Use the PDF preview rule of 200 characters per page.
* Keep preview deterministic and LLM-free.
* Ensure failed attachments do not add error text to `combined_text`.

### Task 8 - Apply post-extraction guardrails
* Run PII detection/masking after PDF extraction/OCR.
* Treat document instructions as untrusted content.
* Preserve ordinary government-form instructions.
* Do not use keyword-only rejection for prompt-injection handling.

### Task 9 - Enforce PDF privacy and cleanup
* Do not persist raw PDFs.
* Do not add uploaded PDFs to the knowledge base or vector store.
* Do not log raw PDF text or unmasked PII.
* Ensure cleanup on success, validation failure, extraction failure, OCR failure, PII failure, and unexpected exception.

### Task 10 - Add mock provider tests
* Test text PDF extraction.
* Test scanned PDF OCR path.
* Test mixed PDF extraction plus OCR path.
* Test provider unavailable, timeout, malformed response, and exception.
* Test corrupt/invalid PDF controlled failure.

### Task 11 - Add real-provider PDF integration tests
* Use a small representative set against the configured provider when available.
* Skip clearly when the provider or system dependency is unavailable.
* Avoid brittle exact extraction assertions; verify meaningful content and contract behavior.

### Task 12 - Add PDF fixture files
* `PDF-001`: text-based PDF with fictional government-style text.
* `PDF-002`: scanned PDF generated from an image fixture.
* `PDF-003`: mixed PDF with one text page and one scanned page.
* `PDF-004`: simple form PDF with labels and fictional values.
* `PDF-005`: table PDF with synthetic tabular values.
* `PDF-006`: PDF containing fictional PII-like values.
* `PDF-007`: PDF containing legitimate government instructions.
* `PDF-008`: PDF containing AI-directed injection-like text.
* `PDF-009`: corrupt/invalid PDF.
* `PDF-010`: PDF exceeding the configured page limit.

### Task 13 - Add PDF processor tests
* Verify `pdf_name`, `extracted_text`, and `preview`.
* Verify preview is page-aware and deterministic.
* Verify over-limit PDFs are rejected before extraction/OCR.
* Verify text/scanned/mixed PDFs are supported.
* Verify extraction failures do not fabricate content.
* Verify PII masking and safety boundaries.

## Files Expected
* `app/input_processing/pdf_processor.py`
* `app/input_processing/ocr_provider.py`
* `app/input_processing/preview.py`
* `guardrails/input_processor.py`
* `tests/input-processor/test_pdf_processor.py`
* `tests/input-processor/test_failures.py`
* `tests/input-processor/test_privacy.py`
* `tests/input-processor/test_cleanup.py`
* PDF fixtures under `tests/input-processor/fixtures/pdfs/`

## Test Fixtures To Create
* Text PDF.
* Scanned PDF.
* Mixed text/scanned PDF.
* Form PDF.
* Table PDF.
* PDF with fictional PII-like values.
* PDF with legitimate instructions.
* PDF with injection-like text.
* Corrupt PDF.
* PDF below, at, and above configured page limit.

## Exit Criteria
* PDF processor is isolated and testable.
* Text, scanned, and mixed PDFs are supported.
* Page-limit validation runs before expensive processing.
* PDF failures are controlled and attachment-scoped.
* Raw PDF content is not persisted or leaked.
* PDF fixtures cover success, failure, privacy, and security behavior.
