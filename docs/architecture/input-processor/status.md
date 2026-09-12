# Input Processor Status

## Current Position

Milestones 1, 2, and 3 are complete on branch:

```text
feature/input-processor
```

Latest verified test run:

```text
.venv\Scripts\python.exe -m pytest
177 passed
```

Next work: start `docs/architecture/input-processor/implementation-plan/milestone4.md` for PDF processing.

## What Exists

- Shared contracts exist: `NormalizedInput`, `ImageContent`, `PDFContent`.
- `GraphState` has `normalized_input`; raw uploads are kept out of graph state.
- Input Processor schemas exist: `Attachment`, `InputRequest`, `InputProcessingResult`, attachment statuses/errors/warnings, `ValidatedAttachment`.
- Pre-processing guardrails exist for input presence, supported MIME types, byte signatures, file size `< 10 MB`, and PDF page count.
- PII masking and untrusted document-text boundaries exist in `guardrails/input_processor.py`.
- Image OCR is implemented through `OCRProvider` and `TesseractOCRProvider`.
- `image_processor.py` turns validated PNG/JPEG bytes into `ImageContent` or safe attachment-scoped failures.
- Image tests cover OCR success, empty/unusable OCR, provider failure, malformed provider response, PII masking, prompt-injection-like text, privacy, cleanup, and real Tesseract integration when available.
- Synthetic image fixtures exist for clear, blank, blurry, unreadable, PII-like, instruction-like, injection-like, invalid, and unsupported image cases.

## Still Pending

- PDF processor implementation is not done.
- Public orchestrator in `app/input_processing/processors.py` is still a scaffold.
- No full `InputRequest -> InputProcessingResult -> NormalizedInput` flow yet.
- No CLI support yet.
- No Docling/PDF provider implementation yet.

## Important Constraints

- Do not change shared contracts unless explicitly requested.
- Keep image logic in `app/input_processing/image_processor.py`.
- Keep PDF logic in `app/input_processing/pdf_processor.py`.
- Keep orchestration only in `app/input_processing/processors.py`.
- Raw uploaded bytes must stay transient and must not enter graph state, logs, traces, memory, vector stores, or fixture data.
- Test fixtures must remain synthetic and safe; no real citizen documents or real PII.
- PDF page limit conflict is still explicit: architecture mentions 5 pages, current project requirement/code uses 10 pages.

## Suggested Next Step

Begin Milestone 4 Task 1: define the PDF provider/extractor boundary before implementing PDF extraction paths.
