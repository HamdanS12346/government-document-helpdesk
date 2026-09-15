# Evaluation Changes

## Purpose

This document defines what needs to be changed, what needs to be added, and what should remain unchanged in the current evaluation implementation.

The evaluation will initially focus on four observations in the RAG pipeline:

1. **Input Processor – Modality Classification**
2. **Intent Classifier – Intent Classification**
3. **Retrieval Node – Retrieval Quality**
4. **Response Node – Response Quality**

The goal is to improve the existing evaluation implementation without unnecessarily changing parts that are already working correctly.

---

# 1. Input Processor – Modality Classification

## Objective

Check whether the input processor correctly identifies the type of input received.

The supported classifications are:

- `text`
- `image`
- `pdf`
- `mixed`

The evaluation should determine whether the predicted modality matches the expected modality.

---

## What should remain intact

The following parts of the current implementation should remain:

- The existing modality evaluation logic.
- The existing dataset structure under:

```text
evaluation/datasets/input_processor/
```

- The existing evaluator under:

```text
evaluation/evaluators/input_processor/
```

- The existing runner:

```text
evaluation/runners/run_input_processor.py
```

- The current approach of comparing the predicted modality with the expected modality.
- The existing modality accuracy metric.
- The existing per-case pass/fail evaluation.
- The existing Langfuse score publishing can remain temporarily while the evaluation architecture is being improved.

The basic evaluation flow is correct:

```text
Input
  ↓
Input Processor
  ↓
Predicted Modality
  ↓
Compare with Expected Modality
  ↓
Pass / Fail
```

---

## Changes required

### 1. Improve the modality dataset
The current dataset should be expanded to make sure all supported modality combinations are represented. The dataset should contain examples for:

- Text
- Image
- PDF
- Text + Image
- Text + PDF
- Image + PDF
- Text + Image + PDF

Also include edge cases such as:
- Empty input
- Unsupported file
- Multiple attachments
- Invalid attachment
- Missing attachment metadata

### 2. Add real-file test cases
The current synthetic fixtures should not be removed. They are useful because they make evaluation:
- Deterministic
- Reproducible
- Fast
- Suitable for regression testing

However, synthetic files alone do not guarantee that the real input-processing pipeline works correctly with real files. Therefore, add a small real-file fixture set.

**Suggested initial size:**
- 5–10 real images
- 5–10 real PDFs

These should be representative of the types of files the actual chatbot is expected to receive. The real-file tests should be added in addition to the existing synthetic tests.

<!--### 3. Separate modality classification from OCR evaluation
Modality classification should answer:
> *"Did the system correctly identify the input as text, image, PDF, or mixed?"*

OCR should answer a different question:
> *"Did the system correctly extract text from the image/PDF?"*

Therefore, OCR accuracy should not be mixed into the modality classification score. The Input Processor evaluation should remain focused on **Modality Classification** + **Input Validation**. A separate OCR evaluation can be added later if OCR is an important component of the pipeline.

---  -->

## Final metrics

The modality evaluation should continue to report:
- **Modality Accuracy**

Optionally, a confusion matrix can be added later:

```text
Expected → Predicted

text   → text
image  → image
pdf    → pdf
mixed  → mixed
```

This will help identify which modality classifications are failing.

---

# 2. Intent Classifier – Intent Classification

## Objective

Check whether the user's input is correctly classified into one of the supported intent categories:

- `document_info`
- `ambiguous`
- `general_chat`

The evaluation flow should compare:

```text
Predicted Intent
        ↓
Expected Intent
        ↓
Pass / Fail
```

---

## What should remain intact

The following should remain unchanged:

- The current intent dataset structure.
- The current three intent categories.
- The current ground-truth labels.
- One evaluation call per test case.
- The current comparison between predicted and expected intent.
- Accuracy calculation.
- Precision, Recall, and F1 calculation.
- Confusion matrix calculation.
- The existing intent evaluator.
- The existing intent runner.

The current one-call-per-case approach should be retained because it allows every test case to be evaluated independently.

---

## Changes required

### 1. Expand the intent dataset
The current dataset should continue to contain examples for `document_info`, `general_chat`, and `ambiguous`. 

The dataset should include:
- Direct questions
- Paraphrased questions
- Short questions
- Long questions
- Incomplete questions
- Questions containing synonyms
- Borderline cases
- Negative examples

**Examples:**
- `"What documents are required for a passport?"` $\rightarrow$ `document_info`
- `"Hello"` $\rightarrow$ `general_chat`
- `"Passport"` $\rightarrow$ `ambiguous`

The important point is that the dataset should test whether the classifier can distinguish between these categories rather than only testing obvious examples.

### 2. Add context-aware cases later
The current evaluation is primarily based on individual user inputs. If the actual chatbot uses conversation history, the evaluation should eventually include context-aware cases.

**Example:**
- **User:** *"What documents do I need for a passport?"*
- **Assistant:** *[response]*
- **User:** *"What about the fees?"*

The second query cannot always be evaluated correctly without considering the previous conversation. Therefore, context-aware intent evaluation should be added once the actual pipeline's conversation-history behavior has been analyzed. 

> Do not redesign the current intent evaluator around conversation history before confirming that the production pipeline actually uses it.

### 3. Keep the offline evaluator
The current offline/heuristic evaluator can remain as a fast regression or smoke test. However, it should not be treated as the final measurement of the actual model's intent-classification quality.

There should eventually be a distinction between:

```text
Offline regression evaluation
        ↓
Fast deterministic testing

Actual model evaluation
        ↓
Measures real classifier performance
```

---

## Final metrics

Continue measuring:
- Accuracy
- Precision
- Recall
- F1
- Confusion Matrix

Accuracy can be used as the primary metric initially. However, macro-F1 should also be monitored so that performance on one intent category does not hide poor performance on another category.

---

# 3. Retrieval Node

## Objective

Check whether the retrieval node retrieves the correct and relevant information from the knowledge base.

The evaluation question is:
> *"Did the system retrieve the correct evidence for the user's query?"*

This evaluation should focus on retrieval quality rather than the quality of the final generated response.

---

## What should remain intact

The following should remain:

- The existing ChromaDB collection.
- The existing retrieval implementation.
- The existing document/chunking process.
- The existing knowledge base.
- The actual retrieved chunks used by the application.
- The retrieval pipeline itself.

The evaluation should test the existing retrieval system rather than modify the retrieval system simply to make the evaluation easier.

---

## Changes required

### 1. Create a retrieval evaluation dataset
Create:
```text
evaluation/datasets/retrieval/cases.jsonl
```

Each case should contain:

```json
{
  "id": "RET-001",
  "query": "What documents are required to apply for an Indian passport?",
  "expected_sources": [
    "passport_required_documents"
  ],
  "expected_chunks": [
    "passport_required_documents_chunk_1",
    "passport_required_documents_chunk_3"
  ]
}
```

The exact fields can be adjusted based on the metadata available in the final ChromaDB collection.

### 2. Use ChromaDB IDs as ground truth identifiers
The final ChromaDB collection contains approximately 1,947 chunks. Do not create a test case for every chunk. Instead, create a representative retrieval dataset of approximately **40–60 test cases**.

The dataset should cover the important government-document categories and the five standard information fields:
1. Purpose
2. Eligibility
3. Required Documents
4. Procedure
5. Fees

### 3. Do not use the retriever's own output as ground truth
The expected retrieved chunks must be defined independently.

- **Incorrect approach:**
  ```text
  Query → Retriever → Retrieved chunks → Treat retrieved chunks as correct
  ```
  *(Cannot reliably measure retrieval quality because the system is judging itself.)*

- **Correct approach:**
  ```text
  Query → Human-defined ground truth → Expected relevant chunks
  Query → Retriever → Actual retrieved chunks
  Compare the two → Retrieval score
  ```

### 4. Start with document-level ground truth if necessary
If assigning exact chunk IDs is too time-consuming initially, document/source-level ground truth can be used.

- **Query:** *"What documents are required for a passport?"*
- **Expected source:** `Passport Required Documents`

Later, this can be refined into chunk-level ground truth. For the initial implementation, document-level evaluation is acceptable if it allows the evaluation to be completed reliably.

### 5. Include difficult retrieval cases
The retrieval dataset should not only contain simple questions. Include:
- Paraphrased questions
- Broad questions
- Specific questions
- Synonyms
- Multi-part questions
- Similar-document questions
- Questions involving similar terminology
- Irrelevant/negative queries

This will provide a more realistic measurement of retrieval quality.

---

## Final metrics

The retrieval evaluation should eventually measure:
- Recall@K
- Precision@K
- MRR
- nDCG

A practical starting point is **Recall@5**, **Precision@5**, and **MRR**. nDCG can be added when graded relevance becomes useful.

---

# 4. Response Node

## Objective

Check whether the final chatbot response is:
- Correct
- Faithful to the retrieved information
- Relevant to the user's question
- Complete
- Properly cited
- Safe

The response evaluation should not only check whether the answer "sounds good"—it should check whether the answer is actually supported by the retrieved evidence.

---

## 4.1 Correctness

### Evaluation question
Is the answer factually correct according to the expected answer and authoritative information?

### What should be evaluated
Check whether the response correctly provides information such as Purpose, Eligibility, Required Documents, Procedure, and Fees.

The evaluation should not require an exact wording match. Instead, use expected answer points.

**Example:**
```json
{
  "expected_points": [
    "Lists the required documents for the passport application"
  ]
}
```
The response passes if it communicates the required information correctly, even if the wording is different.

---

## 4.2 Faithfulness

### Evaluation question
Are the claims in the response supported by the retrieved context?

This is especially important for the RAG chatbot. The system should not invent:
- Fees
- Eligibility requirements
- Documents
- Deadlines
- Processing times
- Procedures
- Government rules

when those facts are not supported by the retrieved evidence.

### What should remain intact
Keep faithfulness as a separate evaluation from correctness. A response can be:
- *Correct but unsupported* OR
- *Supported but factually incorrect*

Therefore, these should not be combined into a single metric.

---

## 4.3 Relevance

### Evaluation question
Does the response directly answer the user's question?

The response should avoid:
- Unnecessary information
- Irrelevant government documents
- Excessive explanation
- Information unrelated to the user's intent

For example, if the user asks about passport fees, the response should primarily address passport fees rather than explaining the entire passport application process.

---

## 4.4 Completeness

### Evaluation question
Did the response cover all the important parts of the user's request?

This is particularly important for multi-part questions.

**Example:**
> *"What is the eligibility, required documents and fee for a passport?"*

The response should address:
1. Eligibility
2. Required Documents
3. Fees

A response that only answers the fee should receive a low completeness score even if the fee itself is correct.

---

## 4.5 Citation Evaluation

### Evaluation question
Does the response provide appropriate citations for the information it gives?

The evaluation should check:
- Are citations present?
- Are citations relevant?
- Do they support the claims being made?

Citation presence alone is not enough. A citation should actually support the information presented in the response.

---

## 4.6 Safety / Guardrail Evaluation

### Evaluation question
Does the chatbot avoid unsafe, unsupported, or inappropriate responses?

For this project, important cases include:
- Fabricated government requirements
- Fabricated fees
- Fabricated deadlines
- Unsupported eligibility claims
- Instructions based on malicious uploaded content
- Sensitive information exposure

The evaluation should include cases where the correct behavior is to refuse to make an unsupported claim or state that sufficient evidence is unavailable.

---

# 5. Response Evaluation Dataset

Create:
```text
evaluation/datasets/response/cases.jsonl
```

Each case should contain the expected outcome rather than an exact expected response.

**Example:**
```json
{
  "id": "RESP-001",
  "input": "What documents are required to apply for an Indian passport?",
  "expected": {
    "should_answer": true,
    "expected_points": [
      "List the required documents for the passport application"
    ],
    "expected_sources": [
      "passport_required_documents"
    ]
  }
}
```

The dataset should contain a mixture of:
- Normal questions
- Multi-part questions
- Insufficient-evidence questions
- Potentially unsafe questions
- Citation-required questions
- Questions with similar documents

---

# 6. What Should NOT Be Changed Right Now

The following should remain intact unless problems are discovered during evaluation:

### Input Processor
- Existing input processing pipeline
- Existing modality classification logic
- Existing validation logic
- Existing dataset structure
- Existing evaluator structure
- Existing runner structure

*(Only improve the test coverage and separate concerns where necessary.)*

### Intent Classifier
- Three intent categories
- Existing dataset format
- Existing evaluator
- Existing runner
- One-call-per-case evaluation
- Existing Accuracy / Precision / Recall / F1 metrics

*(Add context-aware testing later when the actual pipeline behavior is understood.)*

### Retrieval
- Existing ChromaDB
- Existing chunks
- Existing retrieval implementation
- Existing embeddings
- Existing retrieval configuration

*(The evaluation should measure the retriever rather than modify it.)*

### Response
- Keep the response-generation pipeline intact.
- Add evaluations around the output: Correctness, Faithfulness, Relevance, Completeness, Citation, Safety.

*(Do not modify the response generator simply to improve evaluation scores.)*

---

# 7. Langfuse Storage

## Current approach
The current implementation publishes evaluation results to Langfuse using scores such as:
- `accuracy`
- `validity_accuracy`
- `modality_accuracy`
- `case_passed`

This approach is valid and does not need to be immediately removed. However, it should eventually be reorganized to better match Langfuse's evaluation model.

## Recommended approach
Use three layers:

```text
Git / JSONL datasets
        ↓
Ground truth
        ↓
Langfuse Dataset
        ↓
Langfuse Experiment
        ↓
Per-case scores
        ↓
Aggregate experiment scores
```

The source-controlled JSON/JSONL datasets should remain the primary definition of the evaluation cases. Langfuse can be used to visualize, compare, and track evaluation runs.

### Per-case evaluation
Each evaluation case should eventually produce scores such as:
- `case_passed`
- `accuracy`
- `faithfulness`
- `relevance`
- `completeness`
- `citation`
- `safety`

depending on which evaluator applies to that case. This makes it possible to identify exactly which test cases failed.

### Aggregate evaluation
The evaluation run should also produce aggregate metrics such as:
- Modality Accuracy
- Intent Accuracy
- Intent F1
- Recall@5
- MRR
- Response Correctness
- Faithfulness
- Relevance
- Completeness
- Citation Score
- Safety Score

The aggregate scores are useful for comparing different versions of the pipeline.

---

# 8. Recommended Evaluation Structure

The current structure can remain, but it should eventually evolve toward:

```text
evaluation/
│
├── datasets/
│   ├── input_processor/
│   │   └── cases.jsonl
│   │
│   ├── intent/
│   │   └── cases.jsonl
│   │
│   ├── retrieval/
│   │   └── cases.jsonl
│   │
│   └── response/
│       └── cases.jsonl
│
├── evaluators/
│   ├── input_processor/
│   │   └── evaluator.py
│   │
│   ├── intent/
│   │   └── evaluator.py
│   │
│   ├── retrieval/
│   │   └── evaluator.py
│   │
│   └── response/
│       ├── correctness.py
│       ├── faithfulness.py
│       ├── relevance.py
│       ├── completeness.py
│       ├── citation.py
│       └── safety.py
│
├── runners/
│   ├── run_input_processor.py
│   ├── run_intent.py
│   ├── run_retrieval.py
│   └── run_response.py
│
├── common/
│   ├── dataset_loader.py
│   ├── metrics.py
│   ├── result_schema.py
│   └── langfuse.py
│
├── configs/
│   └── thresholds.yaml
│
└── README.md
```

The `common/` directory is an improvement to make the framework easier to extend. It should contain reusable functionality rather than evaluation-specific logic.

---

# 9. Implementation Order

The changes should be implemented in the following order:

1. **Step 1 – Preserve the current working evaluations:** Do not rewrite everything. First make sure the current Input Processor and Intent evaluations still run successfully.
2. **Step 2 – Improve Input Processor test coverage:** Add real image fixtures, real PDF fixtures, more modality combinations, and edge cases. Keep synthetic fixtures.
3. **Step 3 – Improve Intent test coverage:** Add more paraphrases, borderline cases, incomplete queries, and negative examples. Keep the existing evaluator and metrics.
4. **Step 4 – Build Retrieval Evaluation:** Create dataset, evaluator, and runner files using independently defined ground truth (starting with 40–60 cases).
5. **Step 5 – Build Response Evaluation:** Create response datasets and implement evaluators for Correctness, Faithfulness, Relevance, Completeness, Citation, and Safety.
6. **Step 6 – Improve Langfuse integration:** Move toward Langfuse Datasets + Experiments for offline evaluation once local evaluations are running. Do not make Langfuse the only ground truth store.
7. **Step 7 – Add common evaluation utilities:** Identify duplicated code and abstract reusable utilities into `evaluation/common/` (e.g., metric calculations, dataset loading).

---

# 10. Future Evaluations

The four evaluations above are the initial scope. Potential future evaluation points include:

```text
OCR / Document Extraction
        ↓
Input Normalization
        ↓
Query Rewriting
        ↓
Intent Classification
        ↓
Retrieval
        ↓
Reranking
        ↓
Context Construction
        ↓
Response Generation
        ↓
Citation
        ↓
Guardrails
```

These should **NOT** all be implemented immediately. First analyze the actual pipeline and identify which nodes perform meaningful transformations or decisions.

Each new evaluation should answer:

```text
What does this node do?
        ↓
What can go wrong?
        ↓
What is the expected behavior?
        ↓
What should be measured?
        ↓
What is the ground truth?
        ↓
Which metric should be used?
```

---

# 11. Final Principle

The evaluation framework should be built incrementally. The current four observations are the initial evaluation scope:

1. **Input Processor – Modality Classification**
2. **Input Processor – Intent Classification**
3. **Retrieval Node – Retrieval Quality**
4. **Response Node – Response Quality**

The existing working logic should be preserved wherever possible. Changes should primarily focus on:
- Better test coverage
- Better ground truth
- Better separation of evaluation concerns
- Better metrics
- Better tracking of individual failures
- Better Langfuse organization

The evaluation system should measure the actual pipeline rather than changing the pipeline to satisfy the evaluator. Future evaluations should be added only after the corresponding pipeline component has been analyzed and its failure modes are understood.