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
