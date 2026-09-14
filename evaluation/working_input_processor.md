# Input Processor Evaluation Working Guide

This guide explains how the current Input Processor evaluation works, what it measures, where results are stored, and how to publish results to Langfuse.

## Scope

The current evaluation runs the real Input Processor only. Retrieval and response generation are not involved.

```text
Input Processor dataset
        |
        v
run_input_processor.py
        |
        v
process_input()
        |
        v
Input Processor evaluator
        |
        +--> terminal output
        +--> local JSON report
        +--> optional Langfuse scores
```

## Dataset

The current dataset is:

```text
evaluation/datasets/input_processor/cases.json
```

The loader also supports the planned JSON Lines name:

```text
evaluation/datasets/input_processor/cases.jsonl
```

Each case contains:

```json
{
  "id": "IP-001",
  "input": {
    "text": "What documents are required?",
    "attachments": []
  },
  "expected": {
    "valid": true,
    "modality": ["text"]
  }
}
```

Ground truth is manually defined. The evaluator never creates expected labels from the Input Processor prediction.

## Runner

The runner is:

```text
evaluation/runners/run_input_processor.py
```

Run it with:

```powershell
.\.venv\Scripts\python.exe evaluation\runners\run_input_processor.py
```

The runner:

1. Loads `cases.json` or `cases.jsonl`.
2. Verifies that case IDs exist and are unique.
3. Converts each case into an `InputRequest`.
4. Calls the real `process_input()` function.
5. Determines whether processing succeeded.
6. Determines the actual normalized modalities.
7. Compares actual output with the expected case labels.
8. Calculates aggregate metrics.
9. Prints a JSON report.

## Fixture Adapter

The current dataset describes attachment content using text such as:

```json
"content": "Government identity card image"
```

That value is not actual image or PDF bytes. The runner therefore uses deterministic fixture bytes and providers so the real Input Processor can be evaluated without Tesseract or an external PDF provider.

The adapter:

- Loads `evaluation/fixtures/input_processor/images/source1.jpg` and `source2.jpg`.
- Reuses those real image files across image cases; PNG declarations are encoded from a real source image so the declared signature remains valid.
- Loads `evaluation/fixtures/input_processor/pdfs/source1.pdf` and `source2.pdf`.
- Reuses real PDF files across PDF cases and creates bounded in-memory samples from their real pages to respect the existing five-page processor limit.
- Uses a deterministic OCR provider returning synthetic text.
- Uses a deterministic PDF extractor backed by the Input Processor's own PDF classification.
- Preserves dataset filenames and MIME declarations, including malformed metadata cases.
- Does not modify the Input Processor implementation.

This means the evaluation passes real fixture-derived files through the existing pipeline. It does not measure production OCR quality, and the current fixture directory does not contain dedicated corrupt, unreadable, oversized, or unsupported-format files for every invalid dataset case.

## Metrics and Separation of Concerns

The evaluator is:

```text
evaluation/evaluators/input_processor/evaluator.py
```

### Separation of Responsibilities
- **Evaluator (`evaluator.py`)**: A pure, stateless scoring module that takes actual predictions and compares them to expected labels. It has no file I/O or fixture dependencies.
- **Runner (`run_input_processor.py`)**: Responsible for dataset loading, loading real fixture bytes from `evaluation/fixtures/input_processor/`, wrapping requests into `Attachment` objects, executing `process_input()`, and passing results to the evaluator.

It reports two separate accuracy values:

```text
valid_accuracy = cases where actual success/failure matches expected validity / total cases
modality_accuracy = cases where actual modality list matches expected modality list / total cases
```

Current baseline scores on the 50 dataset cases:
- `valid_accuracy`: **78.0%** (39 / 50 cases match)
- `modality_accuracy`: **70.0%** (35 / 50 cases match)
- `passed_cases`: **35** (both validity and modality match)
- `failed_cases`: **15** (known dataset labeling differences, such as unsupported `.webp`/`.tif` in `IP-008`/`IP-040` and partial-success edge cases)

The report also includes:

- Total cases
- Passed cases
- Failed cases
- Expected validity per case
- Actual validity per case
- Expected modalities per case
- Actual modalities per case
- Whether validity matched
- Whether modality matched

Validity and modality are intentionally measured separately. A request can have the correct modality but incorrect validation behavior, or vice versa.

## Partial Success

The Input Processor supports partial success. For example:

```text
User text succeeds
One attachment fails
Another attachment succeeds
```

The overall result can still be successful, with only the successful content included in `NormalizedInput` and a failure status for the failed attachment.

Evaluation validity requires `process_input()` success and every attachment status to be successful. The evaluator therefore marks a case invalid when any supplied attachment fails, even if the Input Processor returns a partial-success result because valid user text or another attachment remains.

## Local Report Storage

To save a local JSON report:

```powershell
New-Item -ItemType Directory -Force evaluation\reports
.\.venv\Scripts\python.exe evaluation\runners\run_input_processor.py `
  --output evaluation\reports\input_processor.json
```

The report is stored at:

```text
evaluation/reports/input_processor.json
```

The `evaluation/reports/` directory is ignored by Git because reports are generated artifacts. The files remain visible locally but are not committed.

## Langfuse Storage

Langfuse publishing happens automatically when the runner is executed and credentials are configured:

```powershell
.\.venv\Scripts\python.exe evaluation\runners\run_input_processor.py --langfuse
```

To save a local copy while publishing to Langfuse:

```powershell
.\.venv\Scripts\python.exe evaluation\runners\run_input_processor.py `
  --output evaluation\reports\input_processor.json
```

Use `--no-langfuse` for a local-only run:

```powershell
.\.venv\Scripts\python.exe evaluation\runners\run_input_processor.py --no-langfuse
```

The reporter creates one Langfuse evaluator observation named:

```text
evaluation:input_processor
```

It stores:

- Aggregate scalar metrics such as `valid_accuracy` and `modality_accuracy`.
- A `case_passed` score for every case.
- The case ID as the score comment.
- The evaluation name and total case count as observation input.
- The entire evaluation report content (all metrics, case evaluations, and modality match details) as observation output.

The reporter calls `flush()` after publishing so queued Langfuse events are sent before the process exits.

### Publishing Existing Saved Reports

You can also publish saved report files from `evaluation/reports/` directly to Langfuse without re-running the evaluation:

```powershell
# Publish all report files in evaluation/reports/
.\.venv\Scripts\python.exe evaluation\langfuse_reporting.py

# Or publish a specific report file:
.\.venv\Scripts\python.exe evaluation\langfuse_reporting.py evaluation\reports\input_processor.json
```

## Langfuse Configuration

The `.env` file must contain:

```env
LANGFUSE_PUBLIC_KEY=your-public-key
LANGFUSE_SECRET_KEY=your-secret-key
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

The runner loads `.env` before publishing. Never commit `.env` or place credentials in source code. Use `--no-langfuse` to skip publishing.

Check configuration without printing secrets:

```powershell
.\.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; load_dotenv(); print({name: bool(os.getenv(name)) for name in ['LANGFUSE_PUBLIC_KEY', 'LANGFUSE_SECRET_KEY', 'LANGFUSE_BASE_URL']})"
```

All three values must be present before using Langfuse publishing.

## Current Limitations

- **Descriptive dataset attachments bridged by fixtures**: In `cases.json`, attachment `content` fields are text descriptions (e.g. `"content": "Government identity card image"`) rather than actual binary uploads. The runner bridges this by injecting real bytes from `evaluation/fixtures/`, but it reuses the same 2 sample images and 2 sample PDFs across all cases rather than testing case-specific, unique, or realistic corrupted/oversized documents.
- **Deterministic OCR/PDF extraction**: The fixture adapter uses deterministic mock providers, meaning evaluation measures input routing and modality classification, not production OCR extraction accuracy.
- **Dataset labeling nuances**: Labels for unsupported extensions (`.webp` in `IP-008`, `.tif` in `IP-040`) and partial-success edge cases should be reviewed before enforcing strict pass thresholds.
- **Network / Credentials**: Langfuse publishing requires valid credentials and active network access.

## Useful Commands

Run with automatic Langfuse publishing (default when credentials exist):

```powershell
.\.venv\Scripts\python.exe evaluation\runners\run_input_processor.py
```

Run purely locally without Langfuse:

```powershell
.\.venv\Scripts\python.exe evaluation\runners\run_input_processor.py --no-langfuse
```

Save report locally while publishing:

```powershell
.\.venv\Scripts\python.exe evaluation\runners\run_input_processor.py `
  --output evaluation\reports\input_processor.json
```

Publish saved report to Langfuse:

```powershell
.\.venv\Scripts\python.exe evaluation\langfuse_reporting.py evaluation\reports\input_processor.json
```

Run focused tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_evaluators.py tests\test_langfuse_reporting.py
```
