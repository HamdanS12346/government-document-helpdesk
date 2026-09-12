# Input Processor Status

## Milestone 1 Status

Milestone 1 setup/scaffolding is complete.

Completed:

- Confirmed branch: `feature/input-processor`.
- Confirmed starting point was clean before work began.
- Verified `.venv` exists and project dependencies install/import correctly.
- Confirmed Input Processor dependencies import: `pydantic`, `pypdf`, `pdfplumber`, `PIL`/`pillow`, `pytesseract`, `pytest`.
- Installed external Tesseract OCR on Windows and verified `pytesseract` can call it after adding Tesseract to `PATH`.
- Added README setup note explaining that `pytesseract` requires the external Tesseract executable.
- Verified `.env.example` exists, local `.env` exists, and `.env` is ignored/not tracked.
- Added `NormalizedInput`, `ImageContent`, and `PDFContent` Pydantic contracts without changing the documented fields.
- Added `GraphState` with `normalized_input` and planned workflow fields, excluding raw uploads, upload objects, temp paths, OCR provider objects, and `InputProcessingResult`.
- Added Input Processor package skeleton under `app/input_processing/`.
- Added Input Processor guardrail skeleton at `guardrails/input_processor.py`.
- Added placeholder test modules under `tests/input-processor/`.
- Created fixture folder structure under `tests/input-processor/fixtures/`.
- Added one fixture README at `tests/input-processor/fixtures/README.md` documenting synthetic/safe fixture rules.
- Ran baseline `pytest`.

Baseline test result:

```text
collected 0 items
no tests ran
```

This is expected for now because test files are placeholders only.

## Current Boundaries

- No OCR implementation added yet.
- No PDF extraction implementation added yet.
- No graph routing added.
- No Docling dependency added; Docling remains pending/proposed.
- No raw uploads are stored in graph state.
- Fixture folders contain no real documents or private data.

## Next Step

Continue with the next milestone from `docs/architecture/input-processor/implementation-plan/`, preserving the same boundary: Input Processor code only, with shared contract changes made deliberately and documented.
