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

- Uses generated valid PNG/JPEG bytes for valid image cases.
- Uses an existing valid PDF fixture for valid PDF cases.
- Uses invalid or over-limit fixtures for cases whose filenames indicate those failures.
- Uses a deterministic OCR provider returning synthetic text.
- Does not modify the Input Processor implementation.

This means the evaluation tests orchestration and validation behavior deterministically. It does not measure real OCR quality.

## Metrics

The evaluator is:

```text
evaluation/evaluators/input_processor/evaluator.py
```

It reports two separate accuracy values:

```text
valid_accuracy = cases where actual success/failure matches expected validity / total cases
modality_accuracy = cases where actual modality list matches expected modality list / total cases
```

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

Dataset cases that expect complete failure when valid user text exists should be reviewed against this contract.

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

Langfuse publishing is optional and is enabled explicitly with `--langfuse`:

```powershell
.\.venv\Scripts\python.exe evaluation\runners\run_input_processor.py --langfuse
```

To save a local copy and publish to Langfuse:

```powershell
.\.venv\Scripts\python.exe evaluation\runners\run_input_processor.py `
  --langfuse `
  --output evaluation\reports\input_processor.json
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
- Aggregate metrics and passed-case count as observation output.

Raw case input, upload bytes, extracted document text, and private document content are not sent to Langfuse.

The reporter calls `flush()` after publishing so queued Langfuse events are sent before the process exits.

## Langfuse Configuration

The `.env` file must contain:

```env
LANGFUSE_PUBLIC_KEY=your-public-key
LANGFUSE_SECRET_KEY=your-secret-key
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

The runner loads `.env` when `--langfuse` is used. Never commit `.env` or place credentials in source code.

Check configuration without printing secrets:

```powershell
.\.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; load_dotenv(); print({name: bool(os.getenv(name)) for name in ['LANGFUSE_PUBLIC_KEY', 'LANGFUSE_SECRET_KEY', 'LANGFUSE_BASE_URL']})"
```

All three values must be present before using `--langfuse`.

## Current Limitations

- The dataset contains descriptive attachment content rather than actual upload bytes.
- The fixture adapter provides deterministic modality/provider behavior.
- The evaluation does not measure production OCR accuracy.
- Dataset labels for unsupported extensions and partial-success cases need review.
- Langfuse publishing requires valid project credentials and network access.

## Useful Commands

Run without Langfuse:

```powershell
.\.venv\Scripts\python.exe evaluation\runners\run_input_processor.py
```

Run with Langfuse:

```powershell
.\.venv\Scripts\python.exe evaluation\runners\run_input_processor.py --langfuse
```

Run focused tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_evaluators.py tests\test_langfuse_reporting.py
```
