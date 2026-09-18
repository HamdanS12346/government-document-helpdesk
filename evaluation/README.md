# Evaluation Guide

Comprehensive guide for evaluating the Government Document Helpdesk assistant across all pipeline stages: Input Processing, Intent Classification, Hybrid Retrieval, Response Generation, and End-to-End Connected Graph Execution.

---

## Overview of Evaluation Modules

| Evaluation Stage | Runner Script | Default Dataset | Evaluated Dimensions | Required Keys |
| :--- | :--- | :--- | :--- | :--- |
| **Input Processor** | `evaluation/runners/run_input_processor.py` | `evaluation/datasets/input_processor/cases.json` | Parsing success/failure, modality extraction | None (Deterministic fixtures) |
| **Intent Classifier** | `evaluation/runners/run_intent.py` | `evaluation/datasets/intent/cases.json` | Intent classification accuracy, macro/per-class Precision, Recall, F1 | None (offline) or `OPENAI_API_KEY` (online) |
| **Hybrid Retrieval** | `evaluation/runners/run_retrieval.py` | `evaluation/datasets/retrieval/cases.jsonl` | Recall@5, Precision@5, MRR, nDCG@5, Hybrid Evidence | `OPENAI_API_KEY`, optional `COHERE_API_KEY` |
| **Response Generation** | `evaluation/runners/run_response.py` | `evaluation/datasets/response/cases.jsonl` | 6 LLM judges (Correctness, Faithfulness, Relevance, Completeness, Citation, Safety) | `OPENAI_API_KEY` |
| **End-to-End Graph** | `evaluation/runners/run_e2e_demo.py` | `evaluation/datasets/response/cases.jsonl` | Full graph execution, dynamic grounding, IR metrics, LLM judges, token usage | `OPENAI_API_KEY`, optional `COHERE_API_KEY` |

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
├── retrieval/
│   └── cases.jsonl          # Government queries paired with expected ground-truth chunk IDs
└── response/
    └── cases.jsonl          # Queries with expected answers, citations, and ground-truth contexts
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

# Real model evaluation with OpenAI
.\.venv\Scripts\python.exe evaluation\runners\run_intent.py

# Local only (skip Langfuse)
.\.venv\Scripts\python.exe evaluation\runners\run_intent.py --no-langfuse

# Save JSON report
.\.venv\Scripts\python.exe evaluation\runners\run_intent.py --output evaluation\reports\intent_openai.json
```

- **Required Keys**:
  - Offline: None.
  - Online: `OPENAI_API_KEY` (invokes `gpt-4o-mini`).
- **Cost**:
  - Offline: $0.00.
  - Online: ~$0.0001 per test case (~$0.005 for full 50-case dataset).
- **Metrics**:
  - `accuracy`: Overall classification accuracy.
  - Macro and per-intent `precision`, `recall`, `f1`, and `support`.
  - Confusion matrix and per-case prediction details.
- **Limitations**: Evaluates standalone classification outside conversation memory context.

---

## 3. Hybrid Retrieval Evaluation

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

## 4. Response Node Evaluation

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

## 5. End-to-End Connected Graph Evaluation

Executes cases through the complete connected LangGraph pipeline (`process_input` -> `intent_classifier` -> `retriever` -> `context_builder` -> `response`), evaluating dynamic grounding, full IR quality, response judges, and token consumption in a single workflow.

### Commands

```powershell
# Run demo on records 1 to 3
.\.venv\Scripts\python.exe -m evaluation.runners.run_e2e_demo --start 1 --end 3

# Run on 10 records with custom report output
.\.venv\Scripts\python.exe -m evaluation.runners.run_e2e_demo --start 1 --end 10 --output evaluation\reports\e2e\latest.json
```

### Metrics & Outputs

- **Corpus Evidence Summary**: Verifies Chroma document count (1948), BM25 document count (1948), and average candidate counts.
- **Dynamic Retrieval Metrics**: Evaluates Recall@5, Precision@5, MRR, and nDCG@5 against ground-truth chunks using live retrieved chunks.
- **Response Quality**: Evaluates live generated answers against expected answers across all 6 LLM judge criteria.
- **Token & Cost Observability**: Tracks input, output, total tokens, and estimated cost across both pipeline nodes and evaluation judges.
- **Langfuse Integration**: Creates hierarchical traces with intermediate node outputs and registers numeric metric scores.

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
   ```
2. **Retrieval Verification (Low Cost)**:
   ```powershell
   .\.venv\Scripts\python.exe -m evaluation.runners.run_retrieval --limit 5 --no-langfuse
   ```
3. **Response Verification (Controlled Budget)**:
   ```powershell
   .\.venv\Scripts\python.exe -m evaluation.runners.run_response --limit 3 --no-langfuse
   ```
4. **End-to-End System Verification**:
   ```powershell
   .\.venv\Scripts\python.exe -m evaluation.runners.run_e2e_demo --start 1 --end 3
   ```
