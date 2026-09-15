# Working Retrieval Evaluation

## Overview
The retrieval evaluation checks how well the **Retriever** node in the LangGraph pipeline returns relevant document chunks for a given user query. It exercises the full end‑to‑end pipeline:

1. **Query normalization** – `NormalizedInput` is built (empty attachments for the evaluation).
2. **Query rewriting** – optional `QueryRewriter`.
3. **Metadata filtering** – `MetadataExtractor` decides which docs to consider.
4. **Hybrid search** – BM25 lexical search + dense vector search.
5. **Reciprocal Rank Fusion (RRF)** – merges lexical and dense results.
6. **Reranking** – optional `CohereReranker` (final top‑k).
7. **Output** – a list of `RetrievedDocument` objects (id, source, text, score).

The evaluation script runs this pipeline on a curated set of cases and computes standard IR metrics.

---

## Dataset
The cases are stored in `evaluation/datasets/retrieval/cases.jsonl`. Each line is a JSON object with the shape:

```json
{
  "id": "RET-001",
  "query": "What is the policy on data retention?",
  "expected_chunks": ["doc-1", "doc-2"]
}
```

- `id` – unique identifier for the case.
- `query` – the user question fed to the retriever.
- `expected_chunks` – the IDs of document chunks that are considered correct.

Feel free to add or modify cases; the runner will automatically pick up any new lines.

---

## Runner script
The executable script is **`evaluation/runners/run_retrieval.py`**. Key usage:

```bash
# From the repository root (virtual‑env activated)
.venv\Scripts\python.exe -m evaluation.runners.run_retrieval \
    [--dataset PATH]          # optional – path to a custom cases file
    [--output PATH]           # optional – where to write the JSON report
    [--top-k N]               # number of top documents to return (default 5)
    [--no-langfuse]           # skip publishing to Langfuse
```

The script performs the following steps:

1. **Load cases** via `evaluation.case_loader.load_cases`.
2. **Validate case IDs** to avoid duplicates.
3. **Create a default retriever pipeline** (`app.rag.node.get_default_retriever_pipeline`).
4. **For each case**:
   - Build a minimal LangGraph state containing a `normalized_input` dict with the query (no attachments).
   - Execute the pipeline → get documents.
   - Extract the document IDs and evaluate against `expected_chunks`.
5. **Collect per‑case results** (`recall_at_5`, `precision_at_5`, `mrr`, `ndcg_at_5`).
6. **Aggregate metrics** (simple averages) via `summarize_retrieval_results`.
7. **Publish to Langfuse** (unless `--no-langfuse`). The `LangfuseReporter` stores the complete JSON report as an observation output.
8. **Write a local JSON report** to `evaluation/reports/retrieval/latest.json` (or the path supplied via `--output`).

---

## Metrics explained
| Metric | Meaning |
|--------|---------|
| `recall_at_5` | Fraction of expected chunks that appear in the top‑5 results. |
| `precision_at_5` | Proportion of the top‑5 results that are expected. |
| `mrr` (Mean Reciprocal Rank) | Reciprocal of the rank of the first relevant chunk (0 if none). |
| `ndcg_at_5` | Normalized Discounted Cumulative Gain@5 – accounts for rank ordering of relevant chunks. |

The aggregated report contains both the per‑case entries and an `average_*` summary.

---

## Running the evaluation (step‑by‑step)
1. **Activate the virtual environment** (if not already):
   ```bash
   .venv\Scripts\activate
   ```
2. **Ensure required API keys are present** in the environment:
   - `OPENAI_API_KEY` (for dense vector search & metadata extraction)
   - `COHERE_API_KEY` (if you want the reranker to run)
   - `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` (for publishing).
3. **Install any missing dependencies** (they were installed earlier, but you can run):
   ```bash
   .venv\Scripts\pip install -r requirements.txt
   ```
4. **Run the script**:
   ```bash
   .venv\Scripts\python.exe -m evaluation.runners.run_retrieval
   ```
   - The script will print the full JSON report to stdout and also write it to `evaluation/reports/retrieval/latest.json`.
5. **Inspect the report** – open the generated JSON file or view it in Langfuse UI.
6. **Optional tweaks**:
   - Change `--top-k` to evaluate different cut‑offs.
   - Provide a custom dataset file via `--dataset path/to/custom_cases.jsonl`.
   - Disable Langfuse publishing with `--no-langfuse` if you only need a local report.

---

## Frequently asked questions
> **Q:** *Why do I see “Missing credentials” errors?
> **A:** The retriever pipeline uses OpenAI‑hosted embeddings and the metadata extractor. Set `OPENAI_API_KEY` (or provide the key directly to the classes) before running.

> **Q:** *Can I evaluate without the reranker?*
> **A:** Yes – the pipeline falls back to the top‑k results from RRF if the reranker fails or its API key is not set.

> **Q:** *How do I add new cases?*
> **A:** Append a new JSON line to `evaluation/datasets/retrieval/cases.jsonl` following the same schema.

---

## Summary
- **Dataset:** `evaluation/datasets/retrieval/cases.jsonl`
- **Runner:** `evaluation/runners/run_retrieval.py`
- **Metrics:** recall@5, precision@5, MRR, nDCG@5 (averaged across cases)
- **Output:** JSON report locally & optional Langfuse observation
- **Prerequisites:** API keys (`OPENAI_API_KEY`, optional `COHERE_API_KEY`), Langfuse keys, virtual‑env activated.

Running the steps above will give you a complete picture of how well the Retriever node performs on the curated government‑document queries.

---

*For any further customization or to add additional metrics, edit `evaluation/evaluators/retrieval/evaluator.py` and the runner accordingly.*
