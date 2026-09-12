# Input Processor Status

## Current Summary

Milestone 1 and Milestone 2 are complete for the Input Processor scope.

Current implementation position: Milestone 3 is complete through Task 9; next task is Task 10 image fixture files.

Current branch:

```text
feature/input-processor
```

Current verified test result:

```text
.venv\Scripts\python.exe -m pytest
155 passed
```

## Milestone 1 Completed

- Verified local setup, `.venv`, dependency imports, and external Tesseract availability.
- Added README note that `pytesseract` requires the external Tesseract executable.
- Added shared `NormalizedInput`, `ImageContent`, and `PDFContent` contracts without changing documented fields.
- Added `GraphState.normalized_input` and kept raw uploads out of graph state.
- Added Input Processor package scaffolding under `app/input_processing/`.
- Added guardrail scaffold at `guardrails/input_processor.py`.
- Added test scaffolding and synthetic fixture folder documentation under `tests/input-processor/fixtures/`.

## Milestone 2 Completed

Implemented contracts and cheap pre-processing guardrails before OCR/PDF extraction.

Code added:

- `app/input_processing/schemas.py`
  - `Attachment`
  - `InputRequest`
  - `InputProcessingResult`
  - attachment status/error/warning schemas
  - `InputModality`
  - `ValidatedAttachment`
- `app/input_processing/errors.py`
  - `InputProcessingErrorCode`
  - controlled `InputProcessingError`
- `app/input_processing/preview.py`
  - deterministic image preview, first 500 characters
  - deterministic PDF preview, 200 characters per page
- `guardrails/input_processor.py`
  - input presence validation
  - supported MIME validation
  - PNG/JPEG/PDF signature validation
  - `< 10 MB` attachment size validation
  - PDF page-count validation shell
  - initial PII masking boundary
  - prompt-injection/document-text trust boundary

Validation behavior now covered:

- Accept text-only requests.
- Accept attachment-only requests.
- Reject completely empty requests.
- Accept only `image/png`, `image/jpeg`, and `application/pdf`.
- Treat `.jpg` and `.jpeg` as JPEG when declared as `image/jpeg` and bytes match.
- Do not trust filename extensions alone.
- Reject MIME/signature mismatch safely.
- Reject oversized files before expensive processing.
- Validate PDF page count before PDF processing.
- Return controlled errors without stack traces, raw bytes, paths, or document text.

Configured limits:

- `MAX_ATTACHMENT_SIZE_BYTES = 10 MB`; enforced as file size `< 10 MB`.
- `MAX_PDF_PAGE_COUNT = 10`.
- The architecture docs still note a 5-vs-10 page discrepancy; code keeps this configurable and currently follows the confirmed 10-page project requirement.

Synthetic fixtures added:

- `tests/input-processor/fixtures/images/valid/fictional_form.png`
- `tests/input-processor/fixtures/images/valid/fictional_form.jpg`
- `tests/input-processor/fixtures/images/invalid/not_an_image.png`
- `tests/input-processor/fixtures/images/invalid/not_an_image.jpg`
- `tests/input-processor/fixtures/pdfs/text/one_page_fixture.pdf`
- `tests/input-processor/fixtures/pdfs/invalid/not_a_pdf.pdf`

Oversized upload coverage is generated in test code, not committed as a large file.

## Tests Added

- `tests/input-processor/test_schemas.py`
- `tests/input-processor/test_validation.py`
- `tests/input-processor/test_guardrails.py`
- `tests/input-processor/test_preview.py`

Current coverage includes:

- request schemas
- processing result schemas
- error taxonomy
- safe error payload shape
- input presence validation
- supported media-type validation
- file signature validation
- file-size boundaries
- PDF page-count boundaries
- deterministic previews
- PII mask-and-continue boundary
- PII detector failure handling
- prompt-injection content boundary
- synthetic validation fixtures

## Current Boundaries

- No OCR implementation yet.
- No image processor extraction behavior yet.
- No PDF extraction behavior yet.
- No orchestration logic in `processors.py` yet beyond scaffolding.
- No CLI path yet.
- No Docling dependency added; Docling remains pending/proposed.
- No raw uploads are stored in graph state.
- No broad shared contract changes were made beyond the milestone 1 `NormalizedInput`/`GraphState` setup.
- Fixture data is synthetic and safe; no real citizen documents or real PII were added.

## Next Step

Continue with the next implementation milestone after `milestone2.md`.

Likely next work:

- define or implement the public Input Processor orchestrator in `app/input_processing/processors.py`
- add OCR provider abstraction wiring if not already finalized
- begin image processing behavior behind `image_processor.py`
- keep raw attachment bytes transient and out of graph state
- continue adding tests in `tests/input-processor/`
