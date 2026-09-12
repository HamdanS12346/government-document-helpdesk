# Milestone 1 - Setup, Dependency Check, State Contract, and Skeleton

## Goal
Prepare the local environment and create the minimum contract/skeleton needed before modality processing starts.

## Scope Rules
* Keep implementation focused on Input Processor setup and contracts.
* Do not change `NormalizedInput` fields.
* Do not persist raw uploads.
* Do not add new dependencies without confirming they are needed and updating `requirements.txt`.
* Do not implement OCR/PDF extraction yet.

## Tasks

### Task 1 - Confirm branch and clean starting point
* Confirm the branch is `feature/input-processor`.
* Run `git status` and note any existing untracked/modified files.
* Do not overwrite teammate or unrelated work.

### Task 2 - Create and activate `.venv`
* Create `.venv` if it does not exist.
* Activate it from PowerShell.
* Confirm `python` and `pip` resolve inside `.venv`.

### Task 3 - Install current project dependencies
* Run `python -m pip install --upgrade pip`.
* Run `pip install -r requirements.txt`.
* Confirm existing packages needed by the Input Processor are importable:
  * `pydantic`
  * `pypdf`
  * `pdfplumber`
  * `PIL`
  * `pytesseract`
  * `pytest`

### Task 4 - Check external/system dependency readiness
* Check whether the Tesseract executable is installed and available to `pytesseract`.
* If Tesseract is missing, document the install step needed for the machine before real OCR integration.
* Check whether Docling is already a confirmed dependency.
* If Docling is not present, do not add it yet; keep PDF extraction behind an interface so the provider can be finalized later.

### Task 5 - Confirm environment files
* Confirm `.env.example` exists.
* Create `.env` locally if missing.
* Verify `.env` is not committed.
* Do not store credentials, uploads, OCR output, or private document content in config files.

### Task 6 - Create/verify graph state contract
* Create or verify `app/graph/state.py`.
* Include `normalized_input` in the state contract.
* Keep graph state free of raw bytes, upload objects, temporary paths, OCR provider objects, and `InputProcessingResult` unless later explicitly approved.
* Do not add graph routing in this milestone.

### Task 7 - Create Input Processor package skeleton
* Create the package under `app/input_processing/`.
* Add the minimum module files needed for later milestones:
  * `__init__.py`
  * `schemas.py`
  * `processors.py`
  * `image_processor.py`
  * `pdf_processor.py`
  * `ocr_provider.py`
  * `preview.py`
  * `errors.py`
* Keep files small and mostly structural in this milestone.

### Task 8 - Create guardrail module skeleton
* Create `guardrails/input_processor.py`.
* Define the boundary for validation and safety checks.
* Do not put OCR, PDF parsing, or graph logic in the guardrail module.

### Task 9 - Create test folder skeleton
* Create `tests/input-processor/`.
* Add test module placeholders for:
  * `test_schemas.py`
  * `test_validation.py`
  * `test_guardrails.py`
  * `test_processors.py`
  * `test_state_integration.py`
  * `test_privacy.py`
  * `test_cleanup.py`
* Keep tests aligned with public contracts first.

### Task 10 - Create fixture folder skeleton
* Create synthetic fixture folders only, without real citizen documents:
  * `tests/input-processor/fixtures/images/valid/`
  * `tests/input-processor/fixtures/images/blurry/`
  * `tests/input-processor/fixtures/images/unreadable/`
  * `tests/input-processor/fixtures/images/injection/`
  * `tests/input-processor/fixtures/pdfs/text/`
  * `tests/input-processor/fixtures/pdfs/scanned/`
  * `tests/input-processor/fixtures/pdfs/mixed/`
  * `tests/input-processor/fixtures/pdfs/over_page_limit/`
  * `tests/input-processor/fixtures/pdfs/invalid/`
  * `tests/input-processor/fixtures/text/`

### Task 11 - Add fixture README files
* Add short README notes explaining each fixture folder.
* State that fixtures must be synthetic, deterministic, and safe to commit.
* State that realistic layouts may be used only with fictional data.

### Task 12 - Run baseline tests
* Run `pytest`.
* If the suite fails before implementation, record the baseline failure.
* Do not treat pre-existing failures as Input Processor regressions unless caused by this work.

## Files Expected
* `app/graph/state.py`
* `app/input_processing/__init__.py`
* `app/input_processing/schemas.py`
* `app/input_processing/processors.py`
* `app/input_processing/image_processor.py`
* `app/input_processing/pdf_processor.py`
* `app/input_processing/ocr_provider.py`
* `app/input_processing/preview.py`
* `app/input_processing/errors.py`
* `guardrails/input_processor.py`
* `tests/input-processor/...`

## Test Fixtures To Prepare
* No real personal/government records.
* Empty placeholder README files are enough in this milestone.
* Actual synthetic PNG/JPG/PDF files are created in later milestones.

## Exit Criteria
* Local environment can install current dependencies.
* Branch and `.venv` are ready.
* State contract has `normalized_input` and no raw upload storage.
* Input Processor, guardrail, and test folders exist.
* Baseline `pytest` result is known.
