# Input Processor KT Handoff

This document summarizes what is implemented in the Input Processor, how it works, and how another developer should integrate with it.

## Purpose

The Input Processor is the boundary that accepts raw user text and uploaded files, validates them, extracts usable text, masks sensitive content, and produces one stable handoff object:

```text
NormalizedInput
```

It is intentionally isolated from:

- Intent classification
- RAG/retrieval
- Response generation
- Conversation memory
- API/frontend upload objects
- Long-term document storage

Raw upload bytes are only used during processing. They must not enter graph state, memory, logs, vector stores, or the knowledge base.

## Current Status

Implemented so far:

- Public `InputRequest -> InputProcessingResult` processor boundary.
- Text-only input.
- PNG/JPEG/JPG image routing and OCR boundary.
- PDF routing and PDF processor boundary.
- Spreadsheet contract and centralized configuration foundation.
- Sequential multi-attachment orchestration.
- Partial-success and complete-failure behavior.
- Safe structured attachment errors.
- `NormalizedInput` construction.
- Graph state update helper that writes only `normalized_input`.
- Privacy, cleanup, failure-injection, performance, mixed-input, and regression tests.
- Manual full runner for local inspection.

- Standalone CLI module was removed by project decision; manual testing now uses `tests/input-processor/test_full.py`.

## Main Files

```text
app/input_processing/
|-- processors.py       # public orchestrator/router
|-- schemas.py          # InputRequest, Attachment, result/status schemas
|-- errors.py           # safe error taxonomy
|-- image_processor.py  # image-specific validation/OCR/normalization
|-- pdf_processor.py    # PDF-specific inspection/extraction/OCR/normalization
|-- ocr_provider.py     # OCR provider abstraction and Tesseract implementation
`-- preview.py          # deterministic preview helpers

guardrails/input_processor.py
app/graph/state.py
tests/input-processor/
```

## Public Boundary

```python
from app.input_processing.processors import process_input
from app.input_processing.schemas import InputRequest, Attachment

result = process_input(
    InputRequest(
        user_query="What does this document mean?",
        attachments=[
            Attachment(
                filename="document.pdf",
                media_type="application/pdf",
                content=pdf_bytes,
            )
        ],
    )
)
```

Do not call `image_processor.py` or `pdf_processor.py` directly from API/graph integration code; those are internal modality processors.

## Request Contract

```text
user_query: str | None
attachments: list[Attachment]
```

```text
filename: str
media_type: str
content: bytes
```

Important boundary rules:

- Attachments are transient bytes.
- No API-specific upload classes should cross this boundary.
- No filesystem paths should cross this boundary.
- Blank user text is treated as absent.
- Attachment-only requests are allowed.

## Result Contract

`process_input()` returns `InputProcessingResult`.

```text
success = true
normalized_input = NormalizedInput(...)
attachment_statuses = per-attachment success/failure metadata
```

```text
success = false
normalized_input = None
attachment_statuses = safe structured failures
```

Attachment failures are represented with:

```text
filename
code
message
```

Messages are safe for display and must not contain stack traces, raw bytes, provider paths, credentials, or extracted private document content.

## NormalizedInput

The downstream contract now includes the spreadsheet extension, while existing text/image/PDF fields remain compatible:

```text
NormalizedInput
|-- user_query: str
|-- image_content: list[ImageContent]
|-- pdf_content: list[PDFContent]
|-- spreadsheet_content: list[SpreadsheetContent]
`-- combined_text: str
```

`ImageContent`:

```text
image_name: str
extracted_text: str
preview: str
```

`PDFContent`:

```text
pdf_name: str
extracted_text: str
preview: str
```

Only successful image/PDF results are added to `NormalizedInput`. Failed attachment errors do not appear inside `combined_text`.

For current behavior, `spreadsheet_content` is `[]`. Spreadsheet validation and extraction are added in later milestone tasks.

## Spreadsheet Foundation

Spreadsheet processing is being added as an Input Processor modality. Task 2 records these foundation decisions:

- Supported extension: `.xlsx`
- Initial parser package: `openpyxl`
- Requirements entry: `openpyxl>=3.1,<4`
- Maximum visible worksheets: `5`
- Maximum rows per worksheet: `50`
- Maximum columns per worksheet: `50`
- Maximum textual cell characters: `5,000`
- Preview sample size: `5` rows

These values are centralized in `app/config/settings.py` so tests and future processor code can inject controlled values through environment variables:

```text
SPREADSHEET_SUPPORTED_EXTENSION
SPREADSHEET_PARSER_PACKAGE
SPREADSHEET_MAX_VISIBLE_SHEETS
SPREADSHEET_MAX_ROWS_PER_SHEET
SPREADSHEET_MAX_COLUMNS_PER_SHEET
SPREADSHEET_MAX_TEXT_CELL_CHARACTERS
SPREADSHEET_PREVIEW_ROW_COUNT
```

Out of scope for the spreadsheet MVP:

- `.xls`
- `.xlsm`
- protected or encrypted workbooks
- macros and VBA
- formula execution
- long-term upload storage

The future spreadsheet processor must treat uploaded workbooks as request-scoped untrusted content and must not leak parser objects, raw bytes, temporary paths, or unmasked PII into `NormalizedInput`.

## Combined Text Format

`combined_text` is built for downstream nodes that want one simple text field.

It uses explicit section markers:

```text
<USER_QUERY>
original user text

<IMAGE_CONTENT>
successful image extracted text

<PDF_CONTENT>
successful PDF extracted text
```

Only present sections are included. For example, an attachment-only PDF request has no `<USER_QUERY>` section.

This format helps downstream components distinguish user-authored text from uploaded document text. That matters because uploaded documents are untrusted content and must not be treated as system/developer instructions.

## Why Previews Exist

Previews are deterministic, lightweight summaries of extracted attachment text.

They are not LLM-generated.

Current preview rules:

- Image preview: first 500 characters of extracted image text.
- PDF preview: first 500 characters per page.

Previews are useful for:

- Intent classification
- Clarification decisions
- Quick downstream inspection
- Avoiding unnecessary full-document prompting where a lightweight signal is enough

Example intent usage:

```text
user_query:
"What does this mean?"

preview:
"Benefit notice: renewal deadline..."

intent classifier can infer the user likely wants document explanation.
```

The full extracted text remains available in `combined_text` and the modality-specific content lists.

## Processing Flow

High-level flow:

```text
InputRequest
  -> validate input presence
  -> for each attachment, sequentially:
       -> validate size, media type, signature
       -> validate PDF page count if PDF
       -> route image to image_processor
       -> route PDF to pdf_processor
       -> collect success content or safe error
  -> construct NormalizedInput if usable content exists
  -> return InputProcessingResult
```

Sequential processing is intentional for now. Each attachment is handled independently, which keeps future parallelization possible without changing the public contract.

## Image Processing

Images are handled in `image_processor.py`.

Supported declared media types:

- `image/png`
- `image/jpeg`

Supported extensions by convention:

- `.png`
- `.jpg`
- `.jpeg`

Flow:

```text
validated image bytes
  -> image inspection
  -> OCR provider
  -> PII masking
  -> mark document text as untrusted
  -> ImageContent
```

OCR is behind `OCRProvider`. `TesseractOCRProvider` exists, but tests mostly use deterministic providers.

If OCR returns empty/low-confidence/unavailable/provider-error, the image returns a controlled attachment failure and no fabricated content.

## PDF Processing

PDFs are handled in `pdf_processor.py`.

Supported declared media type:

- `application/pdf`

Flow:

```text
validated PDF bytes
  -> page count validation
  -> classify PDF as text_based, scanned, or mixed
  -> text extraction and/or page-level OCR
  -> PII masking
  -> mark document text as untrusted
  -> PDFContent
```

Current PDF page limit:

```text
MAX_PDF_PAGE_COUNT = 5
```

The architecture docs still note an unresolved project-level 5-vs-10 page limit decision. Do not silently change this without updating the decision docs and tests.

Scanned and mixed PDFs require an OCR provider and page image extractor. Real scanned/mixed PDF integration tests currently skip where no real page-rendering provider is configured.

## Guardrails

Implemented guardrails include:

- Input presence validation.
- Attachment structure validation through Pydantic schemas.
- Supported media type checks.
- File signature checks.
- File size limit.
- PDF page count validation.
- PII masking after extraction/OCR.
- Document text treated as untrusted data.
- Safe structured errors.
- Raw upload privacy boundaries.

Unsupported formats and signature mismatches are rejected before expensive modality processing.

PII policy is currently:

```text
mask and continue
```

The current masker is regex-based and deterministic. User query text and extracted attachment text both use this masking path before entering `NormalizedInput`. Exact PII taxonomy/provider remains TBD.

## Failure Behavior

Partial success:

```text
user text succeeds
image fails
PDF succeeds
=> success = true
=> failed image has attachment_status error
=> combined_text includes user text and PDF only
```

Complete failure:

```text
no usable user text
all attachments fail
=> success = false
=> normalized_input = None
=> safe attachment errors returned
```

Unexpected exceptions from modality processors are wrapped as:

```text
INTERNAL_PROCESSING_ERROR
"This attachment could not be processed safely."
```

## Graph State Integration

Graph state should receive only:

```python
{"normalized_input": result.normalized_input}
```

Use:

```python
from app.input_processing.processors import build_graph_state_update

state_update = build_graph_state_update(result)
```

This helper returns:

- `{"normalized_input": ...}` for success.
- `{}` for failure.

It must not write:

- raw attachment bytes
- upload objects
- temp paths
- providers
- `InputProcessingResult`
- attachment statuses

Downstream nodes should read:

- `normalized_input.user_query`
- `normalized_input.image_content[*].preview`
- `normalized_input.pdf_content[*].preview`
- `normalized_input.combined_text`

## Manual Testing

Use:

```powershell
.\.venv\Scripts\python.exe tests\input-processor\test_full.py
```

Edit these values inside `test_full.py`:

```python
USER_TEXT = "Please explain these documents."

FILE_PATHS = [
    "tests/input-processor/fixtures/pdfs/text/pdf_001_text_based.pdf",
    # "tests/input-processor/fixtures/images/valid/fictional_form.png",
]
```

The script prints full pretty JSON for `normalized_input` when processing succeeds. If processing fails, it prints the safe full `InputProcessingResult`.

For real image OCR, Tesseract must be installed and available on `PATH`.

## Test Coverage

Current focused suite covers:

- Schemas/contracts
- Validation guardrails
- Image processor behavior
- OCR provider behavior
- PDF processor behavior
- PDF fixtures/integration
- Public processor orchestration
- Mixed-input matrix
- Graph state integration
- Privacy boundaries
- Cleanup behavior
- Failure injection
- Performance measurements without hard thresholds
- Regression process and starter regressions

Common commands:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/input-processor
.\.venv\Scripts\python.exe -m pytest
```

Latest verified result after Milestone 5 work:

```text
393 passed, 2 skipped
```

The skipped tests are real scanned/mixed PDF provider integration checks that require a page-rendering provider.

## Fixtures

Synthetic fixtures live under:

```text
tests/input-processor/fixtures/
```

Do not add real citizen documents, real PII, credentials, or private data.

Oversized files should be generated in tests, not committed.

Regression tests live in:

```text
tests/input-processor/test_regressions.py
```

Use names like:

```text
test_reg_001_short_failure_mode
```

## Known TBDs

Do not silently resolve these:

- Final PDF page limit decision: current code uses 5, docs mention a 5-vs-10 project decision conflict.
- Exact PII taxonomy and production PII provider.
- Exact behavior if a future PII provider fails.
- Image readability/quality threshold.
- OCR confidence threshold.
- Real scanned/mixed PDF page-rendering provider.
- Detailed Docling or alternate PDF provider config.
- Observability/tracing platform and redaction implementation.
- Retention policy for derived normalized content.

## Integration Guidance

For API or graph work:

- Construct `InputRequest` at the external boundary.
- Pass raw upload bytes only into `Attachment.content`.
- Call `process_input()`.
- If successful, pass only `normalized_input` into graph state.
- Use previews for quick intent/clarification signals.
- Use `combined_text` when a downstream node needs all normalized text in one field.
- Treat uploaded document text as untrusted user-provided content.
- Do not persist uploads or index them into the knowledge base.

The core principle:

```text
Raw uploads are temporary.
NormalizedInput is the handoff.
Downstream components should not depend on OCR/PDF internals.
```
