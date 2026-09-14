# Current Evaluation Guide

Evaluation is currently implemented for:

- Input Processor
- Intent Classifier

Retrieval and response evaluation are intentionally not included yet.

Langfuse publishing runs by default for the two implemented evaluations. Use
`--no-langfuse` for a deliberate local-only run.

## Datasets

The runners support both the planned JSON Lines format and the current datasets:

```text
evaluation/datasets/input_processor/cases.json
evaluation/datasets/intent/cases.json
```

Ground truth remains independent of system predictions.

## Input Processor

Run:

```powershell
.\.venv\Scripts\python.exe evaluation\runners\run_input_processor.py
```

The runner publishes the same run to Langfuse automatically:

```powershell
.\.venv\Scripts\python.exe evaluation\runners\run_input_processor.py --langfuse
```

Optional JSON report:

```powershell
.\.venv\Scripts\python.exe evaluation\runners\run_input_processor.py `
  --output evaluation\reports\input_processor.json
```

The runner uses the real Input Processor and deterministic evaluation fixtures/providers. It does not call Tesseract or an external PDF provider.

Metrics:

- `valid_accuracy`: whether the processor's success/failure matches the label.
- `modality_accuracy`: whether the normalized output's modality list matches the label.
- Per-case results and mismatches.

The fixture adapter loads real image/PDF files from `evaluation/fixtures/input_processor/` because the current dataset's attachment `content` fields are descriptions, not upload bytes. The same source fixtures are reused across cases while preserving each dataset filename and declared MIME type. This does not modify the Input Processor.

Evaluation validity requires `process_input()` success and every attachment status to be successful. The Input Processor itself intentionally supports partial success, so a request with valid user text and a failed attachment can still have `success=True`; the evaluator still marks that case invalid because one supplied attachment failed.

## Intent Classifier

### Offline, no API call

```powershell
.\.venv\Scripts\python.exe evaluation\runners\run_intent.py --offline
```

This uses a deterministic heuristic baseline. Its score measures the baseline, not OpenAI model quality. Langfuse publishing is automatic when credentials are configured.

Publish the offline baseline scores to Langfuse:

```powershell
.\.venv\Scripts\python.exe evaluation\runners\run_intent.py --offline --langfuse
```

### Real OpenAI evaluation

```powershell
.\.venv\Scripts\python.exe evaluation\runners\run_intent.py
```

This invokes the real `OpenAIIntentClassifier` once per case and requires a valid `OPENAI_API_KEY`. It may incur API usage.

The real-model evaluation is also published automatically when credentials are configured:

```powershell
.\.venv\Scripts\python.exe evaluation\runners\run_intent.py --langfuse
```

Metrics:

- Accuracy
- Macro precision
- Macro recall
- Macro F1
- Per-intent precision, recall, F1, and support
- Confusion matrix
- Per-case predictions

## Langfuse Publishing

Set these variables in `.env` before running a runner:

```text
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

The reporter creates one evaluator observation per run and publishes:

- Aggregate scalar metrics such as accuracy and F1.
- One `case_passed` score per case.
- The run name and case count.

Raw case inputs, uploaded bytes, and generated document content are not sent to Langfuse. Publishing fails clearly when credentials are missing. Use `--no-langfuse` when evaluation must remain local.

## Output Reports

Reports are JSON and should normally be written outside source control, for example:

```powershell
New-Item -ItemType Directory -Force evaluation\reports
.\.venv\Scripts\python.exe evaluation\runners\run_intent.py --offline `
  --output evaluation\reports\intent-offline.json
```

Do not commit API keys, raw uploads, or generated private evaluation data.

## Current Dataset Follow-Up

The first run should be reviewed before setting pass thresholds. In particular:

- `IP-008` and `IP-040` are labeled valid but use unsupported `.webp` and `.tif` extensions.
- Several invalid cases include user text. Under the current partial-success contract, the request may remain successful even when an attachment fails.
- `IP-038` combines a valid image with a broken PDF and should be reviewed against partial-success behavior.

These are evaluation-label decisions, not changes to the Input Processor.
