# Intent Classifier Evaluation Working Guide

This guide explains how the current Intent Classifier evaluation works, how metrics and reports are stored, how Langfuse publishing works, and what is required to run evaluation with OpenAI credentials.

## Scope

The current evaluation runs the Intent Classifier node with the existing intent dataset.

```text
Intent dataset
      |
      v
run_intent.py
      |
      v
NormalizedInput wrapper
      |
      v
classify_intent()
      |
      v
IntentClassifier provider
      |
      v
IntentDecision
      |
      +--> evaluator metrics
      +--> local JSON report
      +--> optional Langfuse scores
```

Retrieval and response generation are not part of this evaluation.

## Dataset

The current dataset is:

```text
evaluation/datasets/intent/cases.json
```

The loader also supports:

```text
evaluation/datasets/intent/cases.jsonl
```

Each case contains:

```json
{
  "id": "INT-001",
  "input": "What documents are required to apply for a passport?",
  "expected_intent": "document_info"
}
```

The allowed expected labels are:

```text
document_info
general_chat
ambiguous
```

These labels are manually defined ground truth. Predictions must never be used to create or update the expected labels automatically.

## Runner

The runner is:

```text
evaluation/runners/run_intent.py
```

There are two evaluation modes.

## Offline Mode

Run:

```powershell
.\.venv\Scripts\python.exe evaluation\runners\run_intent.py --offline
```

Offline mode uses `OfflineIntentClassifier`, a deterministic heuristic test double. It does not call OpenAI, require an OpenAI key, or incur model charges.

The offline mode is useful for:

- Verifying the evaluation pipeline.
- Checking dataset loading.
- Testing metric calculations.
- Running repeatable local regression checks.
- Testing Langfuse publishing without OpenAI calls.

Its score measures the heuristic baseline, not the quality of the OpenAI classifier.

## OpenAI Mode

Run:

```powershell
.\.venv\Scripts\python.exe evaluation\runners\run_intent.py
```

OpenAI mode:

1. Loads the intent dataset.
2. Creates `OpenAIIntentClassifier()`.
3. Builds a `NormalizedInput` for each text case.
4. Calls `classify_intent()`.
5. Builds the bounded classification query.
6. Sends the query to the OpenAI chat model through structured output.
7. Validates the result as `IntentDecision`.
8. Compares `intent_type` with `expected_intent`.
9. Calculates aggregate and per-class metrics.
10. Prints the report and optionally saves it.

Each case makes one classifier model request. Running the full dataset can create OpenAI usage and charges.

## Input to the Classifier

For each dataset case, the runner creates:

```python
NormalizedInput(
    user_query=case["input"],
    image_content=[],
    pdf_content=[],
    combined_text=f"<USER_QUERY>\n{case['input']}",
)
```

The node receives this in graph-like state:

```python
state = {
    "normalized_input": normalized_input,
    "messages": [],
    "conversation_summary": "",
}
```

The classifier query contains the user query and any configured conversation/attachment context. For these current text-only dataset cases, it is primarily the user query.

The final `IntentDecision.query` is overwritten by the exact query constructed by the node.

## Metrics

The evaluator is:

```text
evaluation/evaluators/intent/evaluator.py
```

It calculates:

- Overall accuracy
- Macro precision
- Macro recall
- Macro F1
- Per-class precision
- Per-class recall
- Per-class F1
- Per-class support
- Confusion matrix
- Per-case expected and actual intent

For each class:

```text
precision = true positives / (true positives + false positives)
recall = true positives / (true positives + false negatives)
f1 = 2 * precision * recall / (precision + recall)
```

The confusion matrix has expected intent as rows and predicted intent as columns:

```json
{
  "document_info": {
    "document_info": 18,
    "general_chat": 2,
    "ambiguous": 0
  },
  "general_chat": {
    "document_info": 0,
    "general_chat": 15,
    "ambiguous": 0
  },
  "ambiguous": {
    "document_info": 3,
    "general_chat": 2,
    "ambiguous": 10
  }
}
```

### Baseline Benchmark Results

1. **Offline Heuristic Baseline (`--offline`)**:
   - Accuracy: **76.0%** (38 / 50 cases)
   - Macro F1: **0.698**
   - Intended solely as a zero-cost deterministic baseline for pipeline testing.

2. **OpenAI `gpt-4o-mini` Evaluation**:
   - Accuracy: **86.0%** (43 / 50 cases)
   - Macro F1: **0.853**
   - Macro Precision: **0.882**, Macro Recall: **0.856**
   - Class breakdown:
     - `general_chat`: 100.0% recall, 78.9% precision (F1: 0.882)
     - `document_info`: 90.0% recall, 85.7% precision (F1: 0.878)
     - `ambiguous`: 66.7% recall, 100.0% precision (F1: 0.800)

## Local Report Storage

Save an offline report locally:

```powershell
New-Item -ItemType Directory -Force evaluation\reports
.\.venv\Scripts\python.exe evaluation\runners\run_intent.py `
  --offline `
  --output evaluation\reports\intent_offline.json
```

Save a real OpenAI evaluation report:

```powershell
.\.venv\Scripts\python.exe evaluation\runners\run_intent.py `
  --output evaluation\reports\intent_openai.json
```

Reports are stored under:

```text
evaluation/reports/
```

The directory is ignored by Git because reports are generated artifacts. Reports remain available locally but are not committed.

## Langfuse Storage

The offline evaluation publishes automatically when Langfuse credentials are configured:

```powershell
.\.venv\Scripts\python.exe evaluation\runners\run_intent.py --offline --langfuse
```

The real OpenAI evaluation also publishes automatically when credentials are configured:

```powershell
.\.venv\Scripts\python.exe evaluation\runners\run_intent.py
```

Use `--no-langfuse` for an intentional local-only run:

```powershell
.\.venv\Scripts\python.exe evaluation\runners\run_intent.py --no-langfuse
```

### Publishing Existing Saved Reports

You can also publish saved report files from `evaluation/reports/` directly to Langfuse without re-running the evaluation:

```powershell
# Publish all report files in evaluation/reports/
.\.venv\Scripts\python.exe evaluation\langfuse_reporting.py

# Or publish a specific report file:
.\.venv\Scripts\python.exe evaluation\langfuse_reporting.py evaluation\reports\intent_openai.json
```

The run name is:

```text
intent_offline
```

for offline mode, or:

```text
intent
```

for real OpenAI mode. Langfuse receives an evaluator observation named:

```text
evaluation:intent_offline
evaluation:intent
```

The reporter stores:

- Aggregate scalar metrics such as accuracy and macro F1.
- One `case_passed` score per dataset case.
- The case ID as the score comment.
- Evaluation name and total case count as observation input.
- The entire evaluation report content (all metrics, confusion matrix, per-class metrics, and per-case predictions) as observation output.

`flush()` is called after publishing so queued events are sent before the runner exits.

## OpenAI Credentials

Real OpenAI evaluation requires a valid key in `.env`:

```env
OPENAI_API_KEY=your-openai-key
```

The project already uses `python-dotenv` and the `OpenAIIntentClassifier` uses `ChatOpenAI` from `langchain-openai`.

Required packages:

```text
openai
langchain-openai
python-dotenv
```

They are declared in `requirements.txt`. Install the project dependencies in the active virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Check whether the key is loaded without printing its value:

```powershell
.\.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; load_dotenv(); print('OPENAI_API_KEY configured:', bool(os.getenv('OPENAI_API_KEY')))"
```

Expected result:

```text
OPENAI_API_KEY configured: True
```

The key must:

- Be valid and active.
- Have access to the configured model, currently `gpt-4o-mini`.
- Have available quota or billing.
- Not be surrounded by accidental whitespace.
- Never be committed, logged, placed in a report, or sent to Langfuse.

## Running Real OpenAI Evaluation Safely

Before running all 50 cases, use a small dataset copy:

```powershell
.\.venv\Scripts\python.exe evaluation\runners\run_intent.py `
  --dataset evaluation/datasets/intent/smoke_cases.json `
  --output evaluation/reports/intent_smoke.json
```

The smoke dataset should contain only a few manually selected cases. Once the smoke run succeeds, run the complete dataset:

```powershell
.\.venv\Scripts\python.exe evaluation\runners\run_intent.py `
  --output evaluation/reports/intent_openai.json
```

To publish the complete OpenAI evaluation to Langfuse:

```powershell
.\.venv\Scripts\python.exe evaluation\runners\run_intent.py `
  --langfuse `
  --output evaluation/reports/intent_openai.json
```

## Failure Conditions

The real OpenAI run can fail because of:

- Missing `OPENAI_API_KEY`.
- Invalid or expired credentials.
- No billing or quota.
- Model access restrictions.
- Network errors.
- Rate limits.
- Structured output parsing errors.
- Provider output outside the supported intent contract.

A failed provider call currently stops the runner rather than silently converting the case into a prediction. This prevents an API failure from being counted as a classification result.

## Offline Versus OpenAI Results

Do not compare the offline heuristic score with the OpenAI score as if they were the same model. Label reports clearly:

```text
intent_offline.json
intent_openai.json
```

The offline run validates the evaluation machinery. The OpenAI run measures the configured model and prompt at the time of execution.

## Current Limitations

- Current intent cases are text-only.
- Conversation history and attachment previews are not represented in the current dataset runner.
- The OpenAI runner makes one model call per case.
- OpenAI evaluation can cost money and may be affected by service variability.
- Langfuse publishing requires valid credentials and network access.
- Results are not automatically used as ground truth.

## Useful Commands

Offline evaluation:

```powershell
.\.venv\Scripts\python.exe evaluation\runners\run_intent.py --offline
```

Offline evaluation with Langfuse:

```powershell
.\.venv\Scripts\python.exe evaluation\runners\run_intent.py --offline --langfuse
```

Real OpenAI evaluation (publishes to Langfuse by default when credentials exist):

```powershell
.\.venv\Scripts\python.exe evaluation\runners\run_intent.py
```

Real OpenAI evaluation purely local (without Langfuse):

```powershell
.\.venv\Scripts\python.exe evaluation\runners\run_intent.py --no-langfuse
```

Publish saved report to Langfuse:

```powershell
.\.venv\Scripts\python.exe evaluation\langfuse_reporting.py evaluation\reports\intent_openai.json
```

Focused tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_intent_classifier.py tests\test_evaluators.py tests\test_langfuse_reporting.py
```

