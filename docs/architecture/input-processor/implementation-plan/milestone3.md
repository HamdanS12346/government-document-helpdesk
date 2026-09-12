# Milestone 3 - Image Processor, OCR Provider, and Image Guardrail Tests

## Goal
Process supported PNG/JPEG/JPG attachments through an OCR provider boundary and produce safe `ImageContent`.

## Scope Rules
* Keep image-specific logic inside `app/input_processing/image_processor.py`.
* Keep OCR implementation behind `OCRProvider`.
* Do not route PDFs from the image processor.
* Do not construct the overall `NormalizedInput` inside the image processor.
* Do not fabricate text when OCR fails or returns unusable content.

## Tasks

### Task 1 - Define OCR provider interface
* Add a narrow `OCRProvider` interface focused on text extraction.
* Support success, empty result, low/unusable result, timeout/unavailable, and provider exception outcomes.
* Keep provider return values deterministic for tests.

### Task 2 - Add Tesseract provider implementation
* Implement Tesseract behind the provider interface.
* Keep provider-specific config out of orchestrator code.
* Handle missing Tesseract executable as a controlled provider failure.
* Do not require downstream components to import or know about Tesseract.

### Task 3 - Implement image processing flow
* Accept already-validated image attachment bytes.
* Open/inspect image safely.
* Run OCR provider.
* Apply PII detection/masking to extracted text.
* Apply document-content safety handling.
* Build deterministic preview.
* Return `ImageContent` or a structured failure.

### Task 4 - Handle empty/unreadable OCR
* Treat empty OCR output as unusable content unless policy says otherwise.
* Return a controlled warning/failure for unreadable images.
* Do not invent document text.
* Keep image-quality thresholds marked TBD if not finalized.

### Task 5 - Preserve legitimate document instructions
* Ensure images containing normal form instructions remain processable.
* Examples: "Attach address proof", "Do not fill below this line".
* Do not reject based only on words like `instruction`, `ignore`, or `system`.

### Task 6 - Handle AI-directed document text safely
* Treat injection-like OCR text as untrusted document data.
* Ensure OCR text cannot change processor control flow, routing, credentials, policy, or prompts.
* Preserve safe extracted content after masking/safety handling according to the defined policy.

### Task 7 - Enforce privacy during image processing
* Do not log raw image bytes.
* Do not log full OCR text or unmasked PII.
* Do not store raw images after processing.
* Ensure cleanup occurs on success, OCR failure, PII failure, and unexpected exceptions.

### Task 8 - Add mock OCR unit tests
* Use deterministic mock providers for most image tests.
* Test OCR success, empty output, low/unusable output, provider exception, timeout/unavailable, and malformed provider response.
* Verify image processor behavior through its public boundary.

### Task 9 - Add real-provider image integration tests
* Add a small representative set using actual Tesseract if available.
* Skip or mark tests clearly when the system binary is unavailable.
* Avoid brittle exact OCR assertions; check meaningful text presence and required behavior.

### Task 10 - Add image fixture files
* `IMG-001`: clear readable PNG/JPEG with fictional government-style text.
* `IMG-002`: clear image with no meaningful text.
* `IMG-003`: blurry image.
* `IMG-004`: severely unreadable image.
* `IMG-005`: image containing fictional PII-like values.
* `IMG-006`: image containing legitimate government instructions.
* `IMG-007`: image containing AI-directed injection-like text.
* `IMG-008`: unsupported image format or invalid image bytes.

### Task 11 - Add image processor tests
* Verify accepted supported images become `ImageContent`.
* Verify `image_name`, `extracted_text`, and `preview`.
* Verify preview is capped at 500 characters.
* Verify PII masking runs after OCR.
* Verify unreadable/empty OCR produces controlled failure or warning.
* Verify unsupported/invalid images never reach OCR.

### Task 12 - Add privacy and cleanup tests for images
* Verify raw bytes do not enter result/state-like structures.
* Verify logs/traces avoid raw OCR text and unmasked PII where applicable.
* Verify temporary image data is cleaned up on all paths.

## Files Expected
* `app/input_processing/ocr_provider.py`
* `app/input_processing/image_processor.py`
* `app/input_processing/preview.py`
* `guardrails/input_processor.py`
* `tests/input-processor/test_image_processor.py`
* `tests/input-processor/test_privacy.py`
* `tests/input-processor/test_cleanup.py`
* image fixtures under `tests/input-processor/fixtures/images/`

## Test Fixtures To Create
* Clear PNG/JPEG with fictional form text.
* Blank/no-text image.
* Blurry image.
* Unreadable image.
* Image with fictional PII-like data.
* Image with legitimate instructions.
* Image with injection-like text.
* Invalid image bytes and unsupported extension sample.

## Exit Criteria
* Image processor is isolated and testable.
* OCR is replaceable through `OCRProvider`.
* Supported images produce `ImageContent`.
* Empty/unreadable/OCR-failure cases produce controlled results.
* PII masking and prompt-injection boundaries are covered.
* Raw image content is not persisted or leaked.
