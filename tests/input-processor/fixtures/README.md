# Input Processor Fixtures

Fixtures in this folder must be synthetic, deterministic, and safe to commit.

Do not add real citizen documents, real government application records, credentials, raw private data, or genuine PII. Realistic document layouts may be used only with fictional names, fictional identifiers, and fictional addresses.

Folder intent:

- `images/valid/`: clear synthetic images with readable text.
- `images/blurry/`: synthetic blurry images for OCR/readability tests.
- `images/unreadable/`: synthetic images that should fail extraction safely.
- `images/injection/`: synthetic images containing document text that resembles prompt injection.
- `pdfs/text/`: synthetic text-based PDFs.
- `pdfs/scanned/`: synthetic scanned/image-based PDFs.
- `pdfs/mixed/`: synthetic PDFs with text and scanned pages.
- `pdfs/over_page_limit/`: synthetic PDFs exceeding the configured page limit.
- `pdfs/invalid/`: malformed or invalid synthetic PDF fixtures.
- `text/`: synthetic text-only input fixtures.

Milestone 2 validation fixtures:

- `images/valid/fictional_form.png`: tiny synthetic PNG with fictional text.
- `images/valid/fictional_form.jpg`: tiny synthetic JPEG with fictional text.
- `images/invalid/not_an_image.png`: invalid bytes using a `.png` name.
- `images/invalid/not_an_image.jpg`: invalid bytes using a `.jpg` name.
- `pdfs/text/one_page_fixture.pdf`: small one-page synthetic PDF.
- `pdfs/invalid/not_a_pdf.pdf`: invalid bytes using a `.pdf` name.

Milestone 3 image fixtures:

- `images/valid/img_001_clear_form.png`: IMG-001 clear readable synthetic government-style text.
- `images/blank/img_002_blank_no_text.png`: IMG-002 clear image with no meaningful text.
- `images/blurry/img_003_blurry_form.png`: IMG-003 blurry synthetic form image.
- `images/unreadable/img_004_severely_unreadable.png`: IMG-004 severely unreadable synthetic image.
- `images/pii/img_005_fictional_pii.png`: IMG-005 synthetic image with fictional PII-like values.
- `images/instructions/img_006_legitimate_instructions.png`: IMG-006 normal form instructions.
- `images/injection/img_007_ai_directed_text.png`: IMG-007 injection-like document text.
- `images/invalid/img_008_invalid_image_bytes.png`: IMG-008 invalid image bytes.
- `images/unsupported/img_008_unsupported_format.gif`: IMG-008 unsupported image format sample.

Milestone 4 PDF fixtures:

- `pdfs/text/pdf_001_text_based.pdf`: PDF-001 text-based fictional government-style PDF.
- `pdfs/scanned/pdf_002_scanned.pdf`: PDF-002 scanned/image-based synthetic PDF.
- `pdfs/mixed/pdf_003_mixed.pdf`: PDF-003 mixed PDF with one text page and one scanned page.
- `pdfs/forms/pdf_004_simple_form.pdf`: PDF-004 simple form PDF with labels and fictional values.
- `pdfs/tables/pdf_005_table.pdf`: PDF-005 synthetic table PDF.
- `pdfs/pii/pdf_006_fictional_pii.pdf`: PDF-006 PDF with fictional PII-like values.
- `pdfs/instructions/pdf_007_legitimate_instructions.pdf`: PDF-007 PDF with legitimate government-style instructions.
- `pdfs/injection/pdf_008_ai_directed_text.pdf`: PDF-008 PDF with AI-directed injection-like text.
- `pdfs/invalid/pdf_009_corrupt.pdf`: PDF-009 corrupt/invalid PDF.
- `pdfs/over_page_limit/pdf_010_over_page_limit.pdf`: PDF-010 PDF exceeding the configured page limit.
- `pdfs/over_page_limit/below_limit_4_pages.pdf`: PDF below the configured page limit.
- `pdfs/over_page_limit/at_limit_5_pages.pdf`: PDF at the configured page limit.

Oversized upload fixtures should be generated in test code rather than committed.
