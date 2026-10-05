# Evaluation Guide

Comprehensive guide for evaluating the Government Document Helpdesk assistant across all pipeline stages: Input Processing, Intent Classification, Multi-Turn Conversational Memory, Clarification & Ambiguity, Hybrid Retrieval, Response Generation, Hallucination & Unsupported Information Detection, Out-of-Scope Detection & Handling, and End-to-End Connected Graph Execution.

---

## Overview of Evaluation Modules

| Evaluation Stage | Runner Script | Default Dataset | Evaluated Dimensions | Required Keys |
| :--- | :--- | :--- | :--- | :--- |
| **Input Processor** | `evaluation/runners/run_input_processor.py` | `evaluation/datasets/input_processor/cases.json` | Parsing success/failure, modality extraction | None (Deterministic fixtures) |
| **Intent Classifier** | `evaluation/runners/run_intent.py` | `evaluation/datasets/intent/cases.json` | Intent classification accuracy, macro/per-class Precision, Recall, F1 | None (offline), `OPENROUTER_API_KEY` (JEV), or `OPENAI_API_KEY` (OpenAI) |
| **Multi-Turn Memory** | `evaluation/runners/run_memory.py` | `evaluation/datasets/memory/cases.json` | Coreference resolution, intent preservation, topic switching, entity accuracy | None (offline) or `OPENAI_API_KEY` / `OPENROUTER_API_KEY` (online) |
| **Clarification & Ambiguity** | `evaluation/runners/run_clarification.py` | `evaluation/datasets/clarification/cases.json` | Ambiguity reason diagnosis, missing dimension extraction, question quality | None (offline) or `OPENAI_API_KEY` (online) |
| **Hybrid Retrieval** | `evaluation/runners/run_retrieval.py` | `evaluation/datasets/retrieval/cases.jsonl` | Recall@5, Precision@5, MRR, nDCG@5, Hybrid Evidence | `OPENAI_API_KEY`, optional `COHERE_API_KEY` |
| **Response Generation** | `evaluation/runners/run_response.py` | `evaluation/datasets/response/cases.jsonl` | 6 LLM judges (Correctness, Faithfulness, Relevance, Completeness, Citation, Safety) | `OPENAI_API_KEY` |
| **Hallucination Evaluation** | `evaluation/runners/run_hallucination.py` | `evaluation/datasets/hallucination/cases.jsonl` | Claim-level context support, hallucination rate, unsupported claim rate, missing info handling | `OPENAI_API_KEY` |
| **Out-of-Scope Detection** | `evaluation/runners/run_out_of_scope.py` | `evaluation/datasets/out_of_scope/cases.jsonl` | Scope classification, containment rate, false acceptance, false rejection, mixed queries | `OPENAI_API_KEY` |
| **End-to-End Graph** | `evaluation/runners/run_e2e_demo.py` | `evaluation/datasets/response/cases.jsonl` (single-turn) or `memory/cases.json` (`--memory`) | Full connected graph execution, dynamic grounding, IR metrics, memory persistence, LLM judges, token usage | `OPENAI_API_KEY` / `OPENROUTER_API_KEY`, optional `COHERE_API_KEY` |

> [!NOTE]
> All runners support Langfuse observability publishing by default when credentials (`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL`) are present. Pass `--no-langfuse` to run purely locally.

---

## Datasets Directory

The evaluation datasets reside under `evaluation/datasets/`:

```text
evaluation/datasets/
├── input_processor/
│   └── cases.json           # Valid/invalid document upload and text inputs
├── intent/
│   └── cases.json           # Queries labeled by intent (document_info, general_chat, ambiguous)
├── memory/
│   └── cases.json           # Multi-turn conversational flows (coreference, follow-ups, topic shifts)
├── clarification/
│   └── cases.json           # Ambiguous queries requiring targeted follow-ups across 6 reason codes
├── retrieval/
│   └── cases.jsonl          # Government queries paired with expected ground-truth chunk IDs
├── response/
│   └── cases.jsonl          # Queries with expected answers, citations, and ground-truth contexts
├── hallucination/
│   └── cases.jsonl          # 30 cases across 5 categories (fully supported, partially supported, unsupported, false premise, numerical)
└── out_of_scope/
    └── cases.jsonl          # 35 cases across 5 categories (in-scope, out-of-scope, borderline, mixed, adversarial)
```

---

## 1. Input Processor Evaluation

Evaluates text normalization, file validation, and modality detection using deterministic fixtures.

### Commands

```powershell
# Run evaluation (publishes to Langfuse if configured)
.\.venv\Scripts\python.exe evaluation\runners\run_input_processor.py

# Run local only without publishing
.\.venv\Scripts\python.exe evaluation\runners\run_input_processor.py --no-langfuse

# Save JSON report to custom path
.\.venv\Scripts\python.exe evaluation\runners\run_input_processor.py --output evaluation\reports\input_processor.json
```

- **Required Keys**: None. Uses real sample fixtures from `evaluation/fixtures/input_processor/` without calling external OCR or PDF services.
- **Cost**: $0.00 (local processing).
- **Metrics**:
  - `valid_accuracy`: Whether processor validation outcome matches the expected ground truth.
  - `modality_accuracy`: Whether detected modalities (`text`, `pdf`, `image`) match the declared input types.
- **Limitations**: Attachment files are reused test fixtures matching the expected MIME types, not dynamic OCR outputs.

---

## 2. Intent Classifier Evaluation

Evaluates routing accuracy across `document_info`, `general_chat`, and `ambiguous`.

### Commands

```powershell
# Offline heuristic baseline (no API call, $0 cost)
.\.venv\Scripts\python.exe evaluation\runners\run_intent.py --offline

# Auto-selection (uses JEV if OPENROUTER_API_KEY is configured, else OpenAI)
.\.venv\Scripts\python.exe evaluation\runners\run_intent.py

# Explicitly evaluate JevIntentClassifier via OpenRouter
.\.venv\Scripts\python.exe evaluation\runners\run_intent.py --classifier jev

# Explicitly evaluate OpenAIIntentClassifier
.\.venv\Scripts\python.exe evaluation\runners\run_intent.py --classifier openai

# Local only (skip Langfuse)
.\.venv\Scripts\python.exe evaluation\runners\run_intent.py --no-langfuse

# Save JSON report
.\.venv\Scripts\python.exe evaluation\runners\run_intent.py --output evaluation\reports\intent_results.json
```

- **Required Keys**:
  - Offline: None ($0.00).
  - Online (JEV): `OPENROUTER_API_KEY` (calls JEV Decisions API on OpenRouter, with graceful fallback to OpenAI).
  - Online (OpenAI): `OPENAI_API_KEY` (invokes `gpt-4o-mini`).
- **Cost**:
  - Offline: $0.00.
  - Online: ~$0.0001 per test case (~$0.005 for full 50-case dataset).
- **Metrics**:
  - `accuracy`: Overall classification accuracy.
  - Macro and per-intent `precision`, `recall`, `f1`, and `support`.
  - Confusion matrix and per-case prediction details.
- **Limitations**: Evaluates standalone classification outside conversation memory context.

---

## 3. Multi-Turn Conversational Memory Evaluation

Evaluates dialogue memory context, pronoun/anaphora resolution, elliptical follow-ups, and clean topic switching across sequential turns.

### Commands

```powershell
# Run deterministic offline evaluation (0 API calls, $0 cost)
.\.venv\Scripts\python.exe evaluation\runners\run_memory.py --offline --no-langfuse

# Run real LLM evaluation with OpenAI
.\.venv\Scripts\python.exe evaluation\runners\run_memory.py

# Run subset of cases (e.g. first 5)
.\.venv\Scripts\python.exe evaluation\runners\run_memory.py --offline --limit 5

# Save custom JSON report
.\.venv\Scripts\python.exe evaluation\runners\run_memory.py --offline --output evaluation\reports\memory\latest.json
```

- **Required Keys**:
  - Offline: None ($0.00). Uses deterministic offline coreference and contextual heuristic resolution.
  - Online: `OPENAI_API_KEY` or `OPENROUTER_API_KEY` (invokes `QueryRewriter` and `JevIntentClassifier` or `OpenAIIntentClassifier`).
- **Cost**:
  - Offline: $0.00.
  - Online: ~$0.0003 per turn.
- **Metrics**:
  - `intent_preservation_accuracy`: Accuracy of intent classification across conversational context (e.g., preventing elliptical follow-ups like "What is the fee?" from dropping to ambiguous).
  - `entity_resolution_accuracy`: Proportion of dialogue entities correctly resolved into standalone search queries.
  - `topic_switch_accuracy`: Precision in dropping stale dialogue context when switching topics (e.g., passport to PAN card).
  - `case_pass_rate` & `turn_pass_rate`: Percentage of cases and turns meeting all evaluation thresholds.
  - `overall_score`: Weighted composite score across pass rate, entity resolution, and intent preservation.
- **Evaluated Categories**:
  - `coreference_resolution`: Pronoun resolution ("it", "this", "that").
  - `ellipsis_resolution`: Follow-ups with missing subjects.
  - `refinement`: Narrowing queries with conditions (e.g., Tatkaal, minor child).
  - `topic_switch`: Abrupt domain shifts between document types.
  - `clarification_followup`: Answering system clarification prompts.
  - `multi_turn_chain`: 3+ turn contextual dialogues.

---

## 4. Clarification & Ambiguity Loop Evaluation

Evaluates the Clarification Node when citizen requests are ambiguous, testing diagnostic accuracy of missing information slots, targeted questioning quality, and multi-round repetition suppression.

### Commands

```powershell
# Run deterministic offline baseline (0 API calls, $0 cost)
.\.venv\Scripts\python.exe evaluation\runners\run_clarification.py --offline --no-langfuse

# Run real model evaluation with OpenAI
.\.venv\Scripts\python.exe evaluation\runners\run_clarification.py

# Run subset of cases (e.g. first 5)
.\.venv\Scripts\python.exe evaluation\runners\run_clarification.py --offline --limit 5

# Save custom JSON report
.\.venv\Scripts\python.exe evaluation\runners\run_clarification.py --offline --output evaluation\reports\clarification\latest.json
```

- **Required Keys**:
  - Offline: None ($0.00). Uses deterministic rule-based clarification diagnostics.
  - Online: `OPENAI_API_KEY` (invokes `gpt-4o-mini` with structured output).
- **Cost**:
  - Offline: $0.00.
  - Online: ~$0.0002 per test case (~$0.004 for full 20-case dataset).
- **Metrics**:
  - `reason_code_accuracy`: Proportion of cases where the primary ambiguity reason code correctly matches ground truth.
  - `average_dimension_f1`: Precision/Recall/F1 of identified missing information dimensions.
  - `average_question_score`: Quality score evaluating interrogative sentence structure and presence of targeted clarification cues.
  - `average_composite_score`: Weighted overall score (45% reason code, 25% dimension F1, 30% question score).
  - `pass_rate`: Percentage of cases passing composite threshold (>= 0.65) with matching reason code.
- **Evaluated Ambiguity Reason Codes**:
  - `missing_document_type`: Inquiries about fees, procedures, or validity without naming the document.
  - `missing_service_or_task`: Document stated, but desired task or question is absent.
  - `missing_location`: Regional/state revenue certificates (income, residence, domicile) lacking state context.
  - `missing_applicant_context`: Eligibility or fee inquiries missing category (minor, adult, Tatkaal, concession).
  - `missing_attachment_reference`: Queries referencing unattached or missing uploads.
  - `unclear_request`: Opaque or ultra-short queries requiring general elaboration.

---

## 5. Hybrid Retrieval Evaluation

Evaluates the multi-stage retriever (query rewriting, metadata filtering, BM25 lexical search, Chroma dense vector search, Reciprocal Rank Fusion, and Cohere reranking) against ground-truth document chunks.

### Commands

```powershell
# Run full retrieval dataset (50 cases)
.\.venv\Scripts\python.exe -m evaluation.runners.run_retrieval

# Run limited subset (e.g. 10 cases)
.\.venv\Scripts\python.exe -m evaluation.runners.run_retrieval --limit 10

# Run specific record slice
.\.venv\Scripts\python.exe -m evaluation.runners.run_retrieval --start 1 --end 10

# Evaluate with custom top-k and write report locally
.\.venv\Scripts\python.exe -m evaluation.runners.run_retrieval --top-k 5 --no-langfuse --output evaluation\reports\retrieval\latest.json
```

### Required Keys & Configuration

- `OPENAI_API_KEY`: **Required**. Used for dense query embeddings (`text-embedding-3-small`) and LLM metadata filter extraction.
- `COHERE_API_KEY`: **Optional** (recommended). Enables Cohere reranking (`rerank-v3.5`). If omitted, the pipeline falls back gracefully to Reciprocal Rank Fusion (RRF) scores without failing.
- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`: Optional for publishing.

### Costs & Resource Usage

- Dense embeddings: ~$0.02 per 1,000 queries.
- BM25: In-memory lexical search (free).
- Cohere reranker: ~$1.00 per 1,000 queries (if key provided).
- Total cost for 50 cases: ~$0.05.

### Metrics & Evidence

- **Information Retrieval (IR) Metrics**:
  - `recall_at_5`: Fraction of expected chunks found in top-5 results.
  - `precision_at_5`: Proportion of top-5 results that are relevant.
  - `mrr` (Mean Reciprocal Rank): Reciprocal rank of the first relevant chunk.
  - `ndcg_at_5`: Normalized Discounted Cumulative Gain accounting for rank positions.
- **Evaluation Evidence Block (`corpus_evidence`)**:
  - `chroma_document_count`: Total indexed documents in vector store (e.g., 1948).
  - `bm25_document_count`: Total indexed documents in lexical index (e.g., 1948).
  - `average_dense_result_count`: Mean candidate chunks returned by Chroma search.
  - `average_lexical_result_count`: Mean candidate chunks returned by BM25 search.
  - `hybrid_retrieval_verified`: Confirms both dense and lexical candidates were retrieved and evaluated.

### Limitations

- Fails fast (`RuntimeError`) if the Chroma vector store or BM25 index contains 0 documents.
- Evaluates exact chunk ID matches (`expected_chunks`); re-chunking or re-indexing the corpus requires updating dataset IDs.

---

## 6. Response Node Evaluation

Evaluates response generation and citation precision using LLM-as-a-judge across 6 distinct criteria.

### Commands

```powershell
# Run full response dataset with all 6 LLM judges
.\.venv\Scripts\python.exe -m evaluation.runners.run_response

# Limit to first 10 cases
.\.venv\Scripts\python.exe -m evaluation.runners.run_response --limit 10

# Evaluate a specific subset of criteria
.\.venv\Scripts\python.exe -m evaluation.runners.run_response --limit 5 --criteria correctness,faithfulness

# Run local only and output report
.\.venv\Scripts\python.exe -m evaluation.runners.run_response --no-langfuse --output evaluation\reports\response\latest.json
```

### Required Keys

- `OPENAI_API_KEY`: **Required**. Used for both response generation (`gpt-4o-mini`) and executing the 6 LLM judges.
- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`: Optional for publishing.

### Costs

- Generation & Judges: ~$0.001 - $0.005 per case evaluated across all 6 criteria.
- Full 50-case evaluation: ~$0.15 - $0.25.

### Metrics

Each criterion is scored from 0.0 to 1.0:

1. `correctness`: Factual alignment with expected answer.
2. `faithfulness`: Strict grounding in context without hallucination.
3. `relevance`: Directness and helpfulness for the citizen query.
4. `completeness`: Thorough coverage of necessary steps, rules, or fees.
5. `citation`: Precision and validity of citation links.
6. `safety`: Absence of harmful, deceptive, or unsafe guidance.
- `composite_score`: Weighted average across criteria.
- `passed`: Whether composite score meets threshold (default >= 0.70).

### Limitations

- Evaluates the generator against static ground-truth context provided in the dataset. To evaluate responses grounded on live retrieved documents, use the End-to-End Evaluation.

---

## 7. End-to-End Connected Graph Evaluation

Executes cases through the complete connected LangGraph pipeline (`process_input` -> `intent_classifier` -> `retriever` -> `context_builder` -> `response`), evaluating dynamic grounding, full IR quality, response judges, and token consumption in a single workflow.

### Commands

```powershell
# Run single-turn demo on records 1 to 3
.\.venv\Scripts\python.exe -m evaluation.runners.run_e2e_demo --start 1 --end 3

# Run on 10 records with custom report output
.\.venv\Scripts\python.exe -m evaluation.runners.run_e2e_demo --start 1 --end 10 --output evaluation\reports\e2e\latest.json

# Run multi-turn conversational memory cases through the connected graph
.\.venv\Scripts\python.exe -m evaluation.runners.run_e2e_demo --memory --start 1 --end 3
```

### Metrics & Outputs

- **Corpus Evidence Summary**: Verifies Chroma document count (1948), BM25 document count (1948), and average candidate counts.
- **Dynamic Retrieval Metrics**: Evaluates Recall@5, Precision@5, MRR, and nDCG@5 against ground-truth chunks using live retrieved chunks.
- **Response Quality**: Evaluates live generated answers against expected answers across all 6 LLM judge criteria.
- **Token & Cost Observability**: Tracks input, output, total tokens, and estimated cost across both pipeline nodes and evaluation judges.
- **Langfuse Integration**: Creates hierarchical traces with intermediate node outputs and registers numeric metric scores.

---

## 8. Hallucination & Unsupported Information Evaluation

Evaluates whether the connected chatbot graph makes factual claims that are not supported by the retrieved context, properly acknowledges missing or unavailable information, refuses to fabricate details (fees, timeframes, eligibility), and challenges false assumptions in user queries.

### Difference from Response Faithfulness

| Dimension | Primary Objective | Key Distinction |
| :--- | :--- | :--- |
| **Response → Faithfulness** | Is the overall answer grounded in retrieved chunks? | Evaluates general holistic grounding and tone. |
| **Hallucination Evaluation** | Does the answer invent unsupported facts, and does it handle missing information appropriately? | Performs **claim-level decomposition**, checks individual assertions against context, verifies honest refusal/uncertainty, and flags false premise acceptance. |

### Commands

```powershell
# Run the complete 30-case hallucination evaluation
.\.venv\Scripts\python.exe -m evaluation.runners.run_hallucination

# Run local only without publishing to Langfuse
.\.venv\Scripts\python.exe -m evaluation.runners.run_hallucination --no-langfuse

# Run on a subset (e.g., first 5 cases)
.\.venv\Scripts\python.exe -m evaluation.runners.run_hallucination --limit 5

# Run a specific slice (records 11 to 20)
.\.venv\Scripts\python.exe -m evaluation.runners.run_hallucination --start 11 --end 20

# Save JSON report to custom destination
.\.venv\Scripts\python.exe -m evaluation.runners.run_hallucination --output evaluation\reports\hallucination_report.json

# Run hallucination evaluator unit tests
.\.venv\Scripts\python.exe -m pytest tests/test_hallucination_evaluator.py
```

### Evaluated Test Categories (30 Cases)

| Test Category | Number | Purpose |
| :--- | :---: | :--- |
| **Fully Supported** | 10 | Verify that supported answers are not incorrectly flagged as hallucinations (low false positive rate). |
| **Partially Supported** | 5 | Verify chatbot answers supported parts while refusing to guess missing details. |
| **Completely Unsupported** | 5 | Verify chatbot acknowledges unavailable information and refuses to fabricate facts. |
| **False Premise** | 5 | Verify chatbot challenges or refuses to accept unsupported user assumptions as fact. |
| **Numerical & Eligibility** | 5 | High-risk numerical grounding (fees, age limits, validity periods, appointment reschedules). |

### Claim-Level Structured Output

```json
{
  "score": 0.33,
  "hallucination_detected": true,
  "claims": [
    {
      "claim": "An Indian passport facilitates international travel.",
      "supported": true,
      "evidence": "Passports Act 1967 requires travel documents for departing India."
    },
    {
      "claim": "The application fee is ₹1,500.",
      "supported": false,
      "evidence": null
    },
    {
      "claim": "Processing takes 15 days.",
      "supported": false,
      "evidence": null
    }
  ],
  "unsupported_claims": 2,
  "unsupported_information_handling": 0.5,
  "reason": "The response contains two factual claims that are not supported by the retrieved context."
}
```

### Metrics & Outputs

- **Average Hallucination Score**: Ratio of supported factual claims to total factual claims across all cases (or 1.0 for valid refusal/uncertainty statements).
- **Hallucination Rate**: Percentage of test cases containing 1 or more unsupported claims.
- **Unsupported Claim Rate**: Total unsupported claims divided by total factual claims across all cases.
- **Unsupported Information Handling**: Rate of appropriately acknowledging missing information and challenging false premises without guessing.
- **Claim-Level Analysis**: Extracts discrete claims, evaluates grounding strictly against retrieved context, and records supporting evidence.

---

## 9. Out-of-Scope Detection & Handling Evaluation

Evaluates whether the connected chatbot graph correctly identifies queries within versus outside its supported government-document domain, avoids answering unrelated requests (coding, weather, stocks, shopping, general knowledge), politely refuses or redirects users to government document assistance, handles borderline queries, and answers mixed queries by resolving only the in-scope portion.

### Difference from Intent Classification

| Stage | Primary Question | Key Difference |
| :--- | :--- | :--- |
| **Intent Classifier** | Did the system map the query to the correct intent class (`document_info`, `general_chat`, `ambiguous`)? | Tests isolated node classification accuracy. |
| **Out-of-Scope Evaluation** | Does the **end-to-end chatbot** recognize domain boundaries, avoid answering forbidden topics, politely redirect, and handle mixed/adversarial inputs safely? | Tests connected graph behavior, refusal quality, and containment of unsupported requests. |

### Commands

```powershell
# Run the complete 35-case out-of-scope evaluation
.\.venv\Scripts\python.exe -m evaluation.runners.run_out_of_scope

# Run local only without publishing to Langfuse
.\.venv\Scripts\python.exe -m evaluation.runners.run_out_of_scope --no-langfuse

# Run on a subset (e.g., first 5 cases)
.\.venv\Scripts\python.exe -m evaluation.runners.run_out_of_scope --limit 5

# Run a specific slice (records 11 to 20)
.\.venv\Scripts\python.exe -m evaluation.runners.run_out_of_scope --start 11 --end 20

# Save JSON report to custom destination
.\.venv\Scripts\python.exe -m evaluation.runners.run_out_of_scope --output evaluation\reports\out_of_scope_results.json

# Run unit tests for out-of-scope evaluator
.\.venv\Scripts\python.exe -m pytest tests/test_out_of_scope_evaluator.py
```

### Evaluated Test Categories (35 Cases)

| Test Category | Number | Purpose |
| :--- | :---: | :--- |
| **Clearly In-Scope** | 10 | Verify normal government document queries are answered helpfully (ensures low false rejection rate). |
| **Clearly Out-of-Scope** | 10 | General knowledge, weather, coding, stocks, medical, entertainment queries (verifies polite refusal/redirection). |
| **Borderline / Ambiguous** | 5 | Queries tangentially mentioning travel/documents but involving foreign rules or commercial services. |
| **Mixed In-Scope + Out-of-Scope** | 5 | Combines an in-scope question with an unrelated request (verifies answering in-scope only). |
| **Adversarial / Scope-Bypass** | 5 | Jailbreak attempts, persona shifts, and instruction overrides attempting to force out-of-scope generation. |

### Structured Evaluation Output

```json
{
  "score": 1.0,
  "scope_classification": {
    "expected": "out_of_scope",
    "actual": "out_of_scope",
    "correct": true
  },
  "behavior": {
    "expected": "refuse_or_redirect",
    "actual": "refuse_or_redirect",
    "correct": true
  },
  "response_appropriate": true,
  "reason": "The chatbot correctly recognized the query as outside its government document domain and politely redirected the user."
}
```

### Metrics & Outputs

- **Scope Classification Accuracy**: Percentage of cases where the chatbot correctly recognized the query scope (`in_scope`, `out_of_scope`, `borderline`, `mixed`).
- **Response Behavior Accuracy**: Percentage of cases where the chatbot executed the expected action (`answer`, `refuse_or_redirect`, `answer_in_scope_only`, `clarify`).
- **Out-of-Scope Containment Rate**: Percentage of out-of-scope queries successfully prevented from generating unsupported responses.
- **False Acceptance Rate**: Out-of-scope queries incorrectly answered (targeted to be as close to 0% as possible).
- **False Rejection Rate**: In-scope queries incorrectly refused (targeted to be as close to 0% as possible).
- **Subcategory Accuracies**: Individual accuracy breakdowns for borderline, mixed, and adversarial queries.

---

## Langfuse Publishing

Set these variables in `.env`:

```env
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com  # or https://jp.cloud.langfuse.com
```

To publish previously generated reports without re-running evaluations:

```powershell
# Publish all saved reports in evaluation/reports/
.\.venv\Scripts\python.exe evaluation\langfuse_reporting.py

# Publish a specific report file:
.\.venv\Scripts\python.exe evaluation\langfuse_reporting.py evaluation\reports\retrieval\latest.json
```

---

## Summary & Best Practices

1. **Quick Smoke Test (No Cost)**:
   ```powershell
   .\.venv\Scripts\python.exe evaluation\runners\run_input_processor.py --no-langfuse
   .\.venv\Scripts\python.exe evaluation\runners\run_intent.py --offline --no-langfuse
   .\.venv\Scripts\python.exe evaluation\runners\run_memory.py --offline --no-langfuse
   .\.venv\Scripts\python.exe evaluation\runners\run_clarification.py --offline --no-langfuse
   ```
2. **Retrieval Verification (Low Cost)**:
   ```powershell
   .\.venv\Scripts\python.exe -m evaluation.runners.run_retrieval --limit 5 --no-langfuse
   ```
3. **Response Verification (Controlled Budget)**:
   ```powershell
   .\.venv\Scripts\python.exe -m evaluation.runners.run_response --limit 3 --no-langfuse
   ```
4. **Hallucination Verification (Claim-Level Grounding)**:
   ```powershell
   # Smoke test (5 cases, no Langfuse publish):
   .\.venv\Scripts\python.exe -m evaluation.runners.run_hallucination --limit 5 --no-langfuse

   # Complete run across all 30 benchmark cases:
   .\.venv\Scripts\python.exe -m evaluation.runners.run_hallucination
   ```
5. **Out-of-Scope Containment Verification**:
   ```powershell
   # Smoke test (5 cases, no Langfuse publish):
   .\.venv\Scripts\python.exe -m evaluation.runners.run_out_of_scope --limit 5 --no-langfuse

   # Complete run across all 35 benchmark cases:
   .\.venv\Scripts\python.exe -m evaluation.runners.run_out_of_scope
   ```
6. **End-to-End System Verification**:
   ```powershell
   # Single-turn grounded QA:
   .\.venv\Scripts\python.exe -m evaluation.runners.run_e2e_demo --start 1 --end 3

   # Multi-turn conversational memory:
   .\.venv\Scripts\python.exe -m evaluation.runners.run_e2e_demo --memory --start 1 --end 3
   ```
