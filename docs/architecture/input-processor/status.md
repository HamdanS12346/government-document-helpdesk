# Input Processor Status

## Current Position

Milestones 1, 2, and 3 are complete.

Milestone 4 is complete through Task 12 on the PDF processor workstream.

Latest verified test run:

```text
.venv\Scripts\python.exe -m pytest
310 passed, 2 skipped
```

Next work: continue `docs/architecture/input-processor/implementation-plan/milestone4.md` with Task 13 - Add PDF processor tests.

## Milestone 4 Completed So Far

- Task 1: PDF provider/extractor boundary exists in `app/input_processing/pdf_processor.py`.
- Task 2: PDF page-count validation runs before extraction/OCR.
- Task 3: PDFs are classified internally as `text_based`, `scanned`, or `mixed`.
- Task 4: Text-based PDFs build `PDFContent` from machine-readable text without OCR.
- Task 5: Scanned PDFs use page-image extraction plus page-level `OCRProvider`.
- Task 6: Mixed PDFs combine machine-readable page text and scanned-page OCR in document order.
- Task 7: PDF previews use the deterministic 200-characters-per-page rule.
- Task 8: PDF post-extraction guardrails apply PII masking and preserve document text as untrusted data.
- Task 9: PDF privacy/cleanup coverage exists; raw PDF bytes are not persisted or exposed in results/state-like payloads.
- Task 10: Mock-provider failure tests exist, including unavailable, timeout, malformed response, exception, and corrupt PDF cases.
- Task 11: Real `pypdf` integration tests exist for generated text PDFs and invalid PDF failure; scanned/mixed real-provider tests skip because no real rendering provider is configured yet.
- Task 12: Synthetic PDF fixtures exist for PDF-001 through PDF-010, plus below-limit and at-limit page-count fixtures.

## Important Current Behavior

- Active PDF page limit is `5` via `MAX_PDF_PAGE_COUNT` in `app/input_processing/pdf_processor.py`.
- `guardrails/input_processor.py` imports and delegates PDF page-count validation to the PDF processor.
- `PDFContent` remains the public normalized PDF contract; provider-specific objects do not leak out.
- `PDFProcessingResult` contains exactly one of `pdf_content`, `extraction_result`, or `error`.
- Text-based PDFs skip OCR and page-image extraction.
- Scanned PDFs require both `ocr_provider` and `page_image_extractor`.
- Mixed PDFs require both `ocr_provider` and `page_image_extractor`.
- Empty/low-confidence scanned pages do not fabricate text; successful pages can still survive where policy allows.
- Failed PDF attachments do not create `pdf_content` and do not add error text to any combined-text-like content.

## Key Files Touched In Milestone 4

- `app/input_processing/pdf_processor.py`
- `tests/input-processor/test_pdf_processor.py`
- `tests/input-processor/test_failures.py`
- `tests/input-processor/test_pdf_integration.py`
- `tests/input-processor/test_pdf_fixtures.py`
- `tests/input-processor/test_cleanup.py`
- `tests/input-processor/test_privacy.py`
- `tests/input-processor/fixtures/README.md`
- PDF fixtures under `tests/input-processor/fixtures/pdfs/`

## PDF Fixtures Added

- `pdfs/text/pdf_001_text_based.pdf`
- `pdfs/scanned/pdf_002_scanned.pdf`
- `pdfs/mixed/pdf_003_mixed.pdf`
- `pdfs/forms/pdf_004_simple_form.pdf`
- `pdfs/tables/pdf_005_table.pdf`
- `pdfs/pii/pdf_006_fictional_pii.pdf`
- `pdfs/instructions/pdf_007_legitimate_instructions.pdf`
- `pdfs/injection/pdf_008_ai_directed_text.pdf`
- `pdfs/invalid/pdf_009_corrupt.pdf`
- `pdfs/over_page_limit/pdf_010_over_page_limit.pdf`
- `pdfs/over_page_limit/below_limit_4_pages.pdf`
- `pdfs/over_page_limit/at_limit_5_pages.pdf`

## Still Pending

- Milestone 4 Task 13: add/verify final PDF processor tests from the task checklist.
- Public orchestrator in `app/input_processing/processors.py` is still a scaffold.
- No full `InputRequest -> InputProcessingResult -> NormalizedInput` flow yet.
- No CLI support yet.
- No concrete Docling/PDF provider implementation yet.
- No real scanned/mixed PDF rendering provider integration yet.

## Constraints To Preserve

- Do not change shared contracts unless explicitly requested.
- Keep PDF-specific logic in `app/input_processing/pdf_processor.py`.
- Keep orchestration in `app/input_processing/processors.py`.
- Keep image logic in `app/input_processing/image_processor.py`.
- Raw uploaded bytes must stay transient and must not enter graph state, logs, traces, memory, vector stores, or fixture data.
- Test fixtures must remain synthetic and safe; no real citizen documents or real PII.
