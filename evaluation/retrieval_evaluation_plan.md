# Retrieval Evaluation Plan

## 1. Define the Objective

The purpose of the retrieval evaluation is to determine whether the retriever node is returning the correct and relevant chunks from ChromaDB for a given user query.

The evaluation should answer:
* Did the retriever find the relevant chunks?
* How many relevant chunks were retrieved?
* Were irrelevant chunks also retrieved?
* Was the most relevant chunk ranked highly?
* How well does the retriever perform across different types of questions?

---

## 2. Create the Retrieval Evaluation Dataset

Create:

```text
evaluation/
└── datasets/
    └── retrieval/
        └── cases.jsonl
```

Each test case should contain:

```json
{
  "id": "RET-001",
  "query": "What documents are required to apply for an Indian passport?",
  "expected_sources": [
    "indian-passport"
  ],
  "expected_chunks": [
    "actual_chunk_id_1",
    "actual_chunk_id_2"
  ]
}
```

The important part is that `query` is explicitly present.

### Dataset Requirements
The dataset should contain approximately **40–60 test cases** initially (around 50 cases is a good target).

The questions should cover:
* Purpose
* Eligibility
* Required Documents
* Procedure
* Fees
* Processing time where relevant
* Different ways of asking the same thing
* Broad questions
* Specific questions
* Questions involving similar documents
* Questions where irrelevant documents could easily be retrieved

---

## 3. Use ChromaDB Chunks as the Source for Ground Truth

The ChromaDB export containing the 1,947 chunks should be used to construct the expected results.

For every evaluation question:

```text
Question
   ↓
Inspect relevant ChromaDB chunks
   ↓
Identify genuinely relevant chunks
   ↓
Store their IDs as expected_chunks
```

> **Note:** The retriever's own results must **not** be used as the ground truth. The `expected_chunks` should represent the chunks that actually contain information needed to answer the query.

---

## 4. Organize the Dataset by Document

Initially, cover the important documents already present in the database.

| Document Category | Target Cases |
| :--- | :--- |
| Indian Passport | 5 cases |
| Visa for entering India | 5 cases |
| OCI Documents | 5 cases |
| Aadhaar Card | 5 cases |
| PAN Card | 5 cases |
| Income Tax Return | 5 cases |
| Disability / UDID | 5 cases |
| Voter ID / EPIC | 5 cases |
| Birth/Death Certificates | 5 cases |
| SC Caste Certificate | 5 cases |

**Total:** 10 documents $\times$ 5 questions = **50 cases**

---

## 5. Define Retrieval Metrics

The evaluator should calculate multiple retrieval metrics:

### Recall@K
Measures whether the relevant chunks were retrieved at all.

* **Example:**
  * Expected relevant chunks = 3
  * Retriever returned 5 chunks
  * 2 of the 3 relevant chunks were retrieved
  * **Recall@5 = 2/3**

This is particularly important for the RAG system because missing relevant information can lead to an incomplete answer.

### Precision@K
Measures how much of the retrieved content is actually relevant.

* **Example:**
  * 5 chunks retrieved
  * 3 are relevant
  * **Precision@5 = 3/5**

This helps identify whether the retriever is returning too much irrelevant information.

### MRR (Mean Reciprocal Rank)
Measures how highly the first relevant chunk appears.

* **Example:**
  * **Retrieved:**
    1. irrelevant
    2. irrelevant
    3. relevant
    4. irrelevant
    5. irrelevant
  * **Reciprocal Rank = 1/3**

This is useful because the ordering of retrieved chunks matters to the downstream LLM.

### nDCG@K
Measures the quality of the ranking, allowing different levels of relevance. This is useful if we later classify chunks as:
* Highly relevant
* Relevant
* Partially relevant
* Irrelevant

For the initial implementation, keep relevance binary:
* `1` = relevant
* `0` = not relevant

and introduce graded relevance later if needed.

---

## 6. Create the Retrieval Evaluator

Create:

```text
evaluation/
└── evaluators/
    └── retrieval/
        └── evaluator.py
```

The evaluator should:
1. Receive the query.
2. Receive the expected chunk IDs.
3. Receive the chunks returned by the actual retriever.
4. Compare the retrieved IDs against the expected IDs.
5. Calculate: **Recall@5**, **Precision@5**, **MRR**, **nDCG@5**.
6. Return the individual scores.

**Conceptual Flow:**

```text
Expected chunks
       +
Retrieved chunks
       ↓
   Evaluator
       ↓
 ┌───────────────┐
 │ Recall@5      │
 │ Precision@5   │
 │ MRR           │
 │ nDCG@5        │
 └───────────────┘
```

---

## 7. Create the Retrieval Runner

Create:

```text
evaluation/
└── runners/
    └── run_retrieval.py
```

The runner should be responsible for executing the evaluation.

```text
cases.jsonl
     ↓
Load evaluation case
     ↓
Send query to actual retriever
     ↓
Get retrieved chunks
     ↓
Run retrieval evaluator
     ↓
Calculate metrics
     ↓
Publish results to Langfuse
     ↓
Generate local evaluation report
```

> **Important:** The runner must call the actual retrieval implementation used by the application. Do not create a separate retrieval implementation specifically for evaluation.

---

## 8. Keep Ground Truth Independent

This is very important.

* **Incorrect Approach:**
  ```text
  Query → Retriever → Top 5 chunks → Declare those chunks as correct
  ```

* **Correct Approach:**
  ```text
  Query → Human-validated ground truth → Expected chunks

  # Separately:
  Query → Actual retriever → Retrieved chunks

  # Evaluation:
  Expected chunks VS Retrieved chunks → Evaluation metrics
  ```

This makes the evaluation meaningful.

---

## 9. Integrate Langfuse

After the retrieval runner finishes, the entire evaluation result must be published to Langfuse. This should not be limited to just one final aggregate score.

We should publish:

### Per-case results
For every case:
```text
RET-001: Recall@5, Precision@5, MRR, nDCG@5
RET-002: Recall@5, Precision@5, MRR, nDCG@5
...
```

### Overall results
At the end of the run:
* `retrieval_recall@5`
* `retrieval_precision@5`
* `retrieval_mrr`
* `retrieval_ndcg@5`
* `total_cases`
* `passed_cases`

This gives us visibility into both **Individual case performance** and **Overall retrieval performance**.

---

## 10. Use Langfuse Dataset + Experiment Structure

Ideally, the retrieval evaluation should eventually follow:

```text
Langfuse Dataset
        ↓
Evaluation Experiment
        ↓
Actual Retriever
        ↓
Retrieved Chunks
        ↓
Item Evaluators
        ↓
Recall@5 / Precision@5 / MRR / nDCG@5
        ↓
Run-level Evaluators
        ↓
Overall metrics
```

The source-controlled `evaluation/datasets/retrieval/cases.jsonl` should remain our ground-truth source of truth. Langfuse can contain a mirrored dataset for experiment tracking.

---

## 11. Store Useful Metadata

Every retrieval evaluation run should record information such as:

```text
evaluation_name = retrieval
dataset_version = v1
retriever_version = ...
embedding_model = ...
top_k = 5
git_commit = ...
evaluator_version = ...
```

This will allow us to later compare **Retriever v1 vs Retriever v2** or **Embedding model A vs Embedding model B** using the same evaluation dataset.

---

## 12. Generate a Local Report as Well

Even though Langfuse is the main observability/evaluation platform, the runner should also generate a local report such as:

```text
evaluation/
└── reports/
    └── retrieval/
        └── latest.json
```

This makes debugging easier. Example payload:

```json
{
  "case_id": "RET-001",
  "query": "What documents are required to apply for an Indian passport?",
  "expected_chunks": ["chunk-1", "chunk-2"],
  "retrieved_chunks": ["chunk-1", "chunk-7", "chunk-9"],
  "recall_at_5": 0.5,
  "precision_at_5": 0.2,
  "mrr": 1.0,
  "ndcg_at_5": 0.613
}
```

---

## Final Folder Structure

```text
evaluation/
│
├── datasets/
│   └── retrieval/
│       └── cases.jsonl
│
├── evaluators/
│   └── retrieval/
│       └── evaluator.py
│
├── runners/
│   └── run_retrieval.py
│
├── reports/
│   └── retrieval/
│       └── latest.json
│
├── configs/
│   └── thresholds.yaml
│
└── README.md
```

---

## Overall Implementation Order

```text
1. Finalize retrieval questions
          ↓
2. Inspect ChromaDB chunks
          ↓
3. Assign human-validated expected_chunks
          ↓
4. Create cases.jsonl
          ↓
5. Implement retrieval evaluator
          ↓
6. Implement run_retrieval.py
          ↓
7. Run against the actual retriever
          ↓
8. Calculate Recall@5 / Precision@5 / MRR / nDCG@5
          ↓
9. Publish ALL per-case results to Langfuse
          ↓
10. Publish aggregate results to Langfuse
          ↓
11. Generate local report
          ↓
12. Review failures and improve dataset/retriever
```

> **Key Principle:** `cases.jsonl` defines the ground truth, `run_retrieval.py` executes the real retriever, `evaluator.py` scores it, and the complete evaluation run—including per-case and aggregate results—is published to Langfuse.