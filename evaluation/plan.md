# Chatbot Evaluation Implementation Plan

> **Current implementation status:** All evaluation phases are implemented: Input Processor,
> Intent Classifier, Hybrid Retrieval (with BM25 + Chroma + Cohere evidence), Response Generation
> (with 6 LLM judges), and End-to-End Connected Graph execution (`run_e2e_demo.py`).
> Langfuse tracing and local JSON reporting are available across all runners.

## 1. Overview

This document defines the implementation plan for evaluating the RAG-based government document information chatbot.

The evaluation system covers:

1. Input Processor
2. Intent Classifier
3. Retrieval
4. Response Generation

It also integrates with Langfuse for observability and evaluation tracking.

The implementation should be done incrementally, one evaluation component at a time.

---

## 2. Evaluation Goals

The evaluation system should determine whether:

- User inputs are correctly classified and validated.
- User queries are assigned the correct intent.
- The retriever finds relevant evidence from the knowledge base.
- Generated responses are correct and supported by retrieved evidence.
- Responses are relevant, complete, properly cited, and safe.
- Evaluation results can be observed and tracked through Langfuse.

---

## 3. Overall Architecture

```text
                         User Input
                              |
                              v
                    +-------------------+
                    |  Input Processor  |
                    +-------------------+
                              |
                              v
                    +-------------------+
                    | Intent Classifier |
                    +-------------------+
                              |
                              v
                    +-------------------+
                    |    Retrieval      |
                    |    (ChromaDB)     |
                    +-------------------+
                              |
                              v
                    +-------------------+
                    | Response Generator|
                    +-------------------+
                              |
                              v
                       Final Response


Evaluation Pipeline

Input Processor
      |
      v
Input Evaluator
      |
      v
Intent Evaluator
      |
      v
Retrieval Evaluator
      |
      v
Response Evaluators
      |
      v
Langfuse / Evaluation Results
```

---

## 4. Directory Structure

```text
evaluation/
│
├── datasets/
│   ├── input_processor/
│   │   └── cases.jsonl
│   ├── intent/
│   │   └── cases.jsonl
│   ├── retrieval/
│   │   └── cases.jsonl
│   └── response/
│       └── cases.jsonl
│
├── evaluators/
│   ├── input_processor/
│   │   └── evaluator.py
│   ├── intent/
│   │   └── evaluator.py
│   ├── retrieval/
│   │   └── evaluator.py
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
├── configs/
│   └── thresholds.yaml
│
└── README.md
```

---

# 5. Input Processor Evaluation

## 5.1 Purpose

The Input Processor evaluation checks whether the system correctly:

- Identifies the input modality.
- Validates the input.
- Handles supported and unsupported inputs.
- Handles combinations of modalities.

Supported modalities include:

- Text
- Image
- PDF
- Text + Image
- Text + PDF
- Image + PDF
- Text + Image + PDF

Invalid and edge-case inputs should also be tested.

## 5.2 Dataset

File:

```text
evaluation/datasets/input_processor/cases.jsonl
```

Minimum structure:

```json
{
  "id": "IP-001",
  "input": "...",
  "expected": {
    "valid": true,
    "modality": "text"
  }
}
```


Possible edge cases:

- Empty input
- Unsupported file type
- Corrupt PDF
- Oversized file
- PDF with too many pages
- Multiple attachments
- Missing metadata
- Invalid input combinations

## 5.3 Metrics

Evaluate two properties separately.

### Modality Accuracy

```text
modality_accuracy =
correct_modality_predictions / total_cases
```

### Validation Accuracy

```text
validation_accuracy =
correct_validity_predictions / total_cases
```

The two metrics should remain separate because correct modality classification does not necessarily mean correct validation.

## 5.4 Ground Truth

Ground truth should be manually defined in the dataset.

The classifier's predictions must never be used to create its own ground truth.

The dataset should be expanded when new failures are discovered.

---

# 6. Intent Classifier Evaluation

## 6.1 Purpose

The Intent Classifier determines what the user is trying to accomplish.

Initial intent categories:

```text
document_info
ambiguous
general_chat
```

## 6.2 Dataset

File:

```text
evaluation/datasets/intent/cases.jsonl
```


## 6.3 Document Information Queries

Cover the five standard information fields:

- Purpose
- Eligibility
- Required Documents
- Procedure
- Fees

Use supported documents such as:

- Indian Passport
- Visa for entering India
- OCI Documents
- Certificate of Disability
- Tax / Financial Documents

Include paraphrases and different query styles.

Examples:

```text
What documents do I need for a passport?
Which documents are required to apply for a passport?
How much does the passport application cost?
Who can apply for this document?
How do I apply for it?
```

## 6.4 Ambiguous Queries

Examples:

```text
Passport
I need a visa.
Documents?
How do I get it?
What is the fee?
```

Without sufficient context, these should generally be classified as ambiguous.

If conversation context is part of the classifier, that context must be explicitly represented in the test case.

## 6.5 General Chat

Include queries unrelated to government document applications.

Examples:

```text
Hello
How are you?
Tell me a joke.
What is the weather?
What is Python?
```

## 6.6 Metrics

The intent evaluator should calculate:

- Accuracy
- Precision
- Recall
- F1 Score
- Confusion Matrix

The confusion matrix should help identify confusion between:

```text
document_info <-> ambiguous
document_info <-> general_chat
ambiguous <-> general_chat
```

---

# 7. Langfuse Integration

Langfuse should be integrated after the Input Processor and Intent evaluation foundations are working.

## 7.1 Purpose

Langfuse will provide:

- Observability
- Tracing
- Evaluation tracking
- Visibility into evaluation runs
- Support for LLM-as-a-Judge evaluations

## 7.2 Configuration

The application will require Langfuse project credentials such as:

```env
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

The secret key must be stored securely and must not be committed to Git.

Install the Python SDK with:

```bash
pip install langfuse
```

LLM provider credentials used by an LLM judge are separate from Langfuse credentials.

## 7.3 Tracing

Eventually the important RAG stages should be visible in Langfuse:

```text
Input
  ↓
Input Processing
  ↓
Intent Classification
  ↓
Retrieval
  ↓
Response Generation
  ↓
Evaluation Scores
```

---

# 8. Retrieval Evaluation

## 8.1 Purpose

Retrieval evaluation answers:

> Did the system retrieve the correct evidence for the user's query?

The evaluator compares the actual retrieved chunks against manually created ground truth.

## 8.2 ChromaDB Data

The current ChromaDB collection contains approximately 1,947 chunks.

Do not create one evaluation case for every chunk.

Export the information needed to construct retrieval ground truth:

- Chunk ID
- Chunk text
- Document/source name
- Metadata
- URL
- Page number, if available

Embeddings are not required for evaluation.

Example:

```json
{
  "id": "passport_required_documents_chunk_1",
  "document": "...",
  "metadata": {
    "source": "passport_required_documents",
    "url": "https://example.gov.in/...",
    "page": 2
  }
}
```

The final ChromaDB collection should be treated as authoritative because it contains the combined data populated by the group.

## 8.3 Retrieval Dataset

File:

```text
evaluation/datasets/retrieval/cases.jsonl
```

Example:

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

Initial target: approximately 40–60 cases.

Suggested distribution:

| Area | Cases |
|---|---:|
| Passport | 10 |
| Visa | 8 |
| OCI | 8 |
| Certificate of Disability | 8 |
| Tax / Financial | 8 |
| Cross-document / Difficult | 8 |
| **Total** | **~50** |

## 8.4 Test Coverage

Queries should cover:

- Purpose
- Eligibility
- Required Documents
- Procedure
- Fees
- Broad questions
- Specific questions
- Paraphrases
- Synonyms
- Multi-part questions
- Similar documents
- Difficult queries
- Negative / irrelevant retrieval

## 8.5 Ground Truth

Ground truth must be manually created from authoritative source chunks.

Do not use ChromaDB's own retrieval results as ground truth.

For the first implementation, document/source-level ground truth is acceptable if chunk-level ground truth is difficult.

The evaluation can later be upgraded to chunk-level ground truth.

## 8.6 Metrics

### Recall@5

```text
Recall@5 =
relevant retrieved chunks / total relevant chunks
```

### Precision@5

```text
Precision@5 =
relevant retrieved chunks / 5
```

### MRR

Mean Reciprocal Rank measures how highly the first relevant result appears.

```text
MRR = average(1 / rank_of_first_relevant_result)
```

### nDCG

Normalized Discounted Cumulative Gain measures ranking quality while accounting for the position of relevant results.

---

# 9. Response Evaluation

## 9.1 Purpose

Response evaluation checks whether the generated response is:

- Correct
- Faithful to retrieved evidence
- Relevant
- Complete
- Properly cited
- Safe

## 9.2 Dataset

File:

```text
evaluation/datasets/response/cases.jsonl
```

The response dataset should define expected answer criteria rather than requiring exact wording.

Example:

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

The runner should capture:

- Actual response
- Retrieved context
- Citations
- Expected answer criteria

---

# 10. Response Evaluators

## 10.1 Correctness

File:

```text
evaluation/evaluators/response/correctness.py
```

Determine whether the response is factually correct according to authoritative evidence.

Pay particular attention to:

- Fees
- Eligibility
- Required documents
- Procedures
- Deadlines
- Processing times

## 10.2 Faithfulness

File:

```text
evaluation/evaluators/response/faithfulness.py
```

Determine whether claims in the response are supported by retrieved context.

The main goal is to detect hallucinations.

If retrieved evidence does not contain a fee, for example, the response should not invent one.

## 10.3 Relevance

File:

```text
evaluation/evaluators/response/relevance.py
```

Determine whether the response directly addresses the user's query.

Penalize:

- Off-topic information
- Unnecessary explanations
- Repetition
- Failure to answer the requested field

## 10.4 Completeness

File:

```text
evaluation/evaluators/response/completeness.py
```

Determine whether all expected points were covered.

This is especially important for multi-part queries.

Example:

```text
What is the purpose, eligibility, fee and procedure?
```

The response should address all four requested components.

## 10.5 Citation

File:

```text
evaluation/evaluators/response/citation.py
```

Check whether:

- Citations are present when required.
- Citations point to relevant evidence.
- Important factual claims are supported.
- The cited source actually contains the claimed information.

## 10.6 Safety

File:

```text
evaluation/evaluators/response/safety.py
```

Check for:

- Fabricated requirements
- Fabricated fees
- Fabricated deadlines
- Unsupported eligibility claims
- Unsupported procedural instructions
- Malicious instructions contained in uploaded documents
- Exposure of sensitive information

The system should prefer acknowledging insufficient evidence instead of fabricating information.

---

# 11. Insufficient-Evidence Cases

The response dataset should include cases where available evidence is insufficient.

Example:

```json
{
  "id": "RESP-INSUFFICIENT-001",
  "input": "What is the processing time for this document?",
  "expected": {
    "should_answer": false,
    "expected_points": [
      "State that sufficient evidence is not available",
      "Do not invent a processing time"
    ]
  }
}
```

These cases are important for testing hallucination prevention.

---

# 12. Evaluation Method

A hybrid evaluation approach should be used.

## 12.1 Code-Based Evaluation

Use deterministic checks wherever possible.

Examples:

- Modality matching
- Valid/invalid matching
- Intent classification
- Expected chunk ID matching
- Citation presence
- Basic response structure

Advantages:

- Fast
- Reproducible
- Cheap
- Easy to automate

## 12.2 LLM-as-a-Judge

Use an LLM judge for properties that are difficult to evaluate using simple rules.

Recommended uses:

- Correctness
- Faithfulness
- Relevance
- Completeness
- Safety

The judge should receive:

```text
User Query
+
Retrieved Context
+
Generated Response
+
Expected Criteria
```

The judge should return a structured result.

Example:

```json
{
  "score": 0.9,
  "reason": "The response correctly addresses the required documents and is supported by the retrieved evidence."
}
```

## 12.3 Human Verification

A small subset of cases should be manually reviewed.

Human evaluation can be used to:

- Validate the LLM judge
- Detect judge errors
- Check difficult edge cases
- Create a high-quality gold set

---

# 13. Evaluation Thresholds

File:

```text
evaluation/configs/thresholds.yaml
```

Initial structure:

```yaml
input_processor:
  modality_accuracy: 0.95
  validation_accuracy: 0.95

intent:
  accuracy: 0.90
  f1: 0.90

retrieval:
  recall_at_5: 0.85
  precision_at_5: 0.70
  mrr: 0.80

response:
  correctness: 0.85
  faithfulness: 0.90
  relevance: 0.90
  completeness: 0.85
  citation: 0.90
  safety: 0.95
```

These are initial targets and should be adjusted based on actual system performance and dataset difficulty.

---

# 14. Runners

Each evaluation area should have its own runner.

## 14.1 Input Processor Runner

File:

```text
evaluation/runners/run_input_processor.py
```

Responsibilities:

1. Load `cases.jsonl`.
2. Run each input through the Input Processor.
3. Capture predicted validity and modality.
4. Pass predictions to the evaluator.
5. Calculate metrics.
6. Print/store results.
7. Optionally send results to Langfuse.

## 14.2 Intent Runner

File:

```text
evaluation/runners/run_intent.py
```

Responsibilities:

1. Load intent cases.
2. Run each query through the Intent Classifier.
3. Capture predicted intent.
4. Compare prediction with ground truth.
5. Calculate accuracy, precision, recall, F1 and confusion matrix.
6. Store results.
7. Send results to Langfuse when integration is enabled.

## 14.3 Retrieval Runner

File:

```text
evaluation/runners/run_retrieval.py
```

Responsibilities:

1. Load retrieval cases.
2. Run each query through the actual retriever.
3. Capture retrieved chunk IDs.
4. Compare retrieved IDs against expected IDs.
5. Calculate Recall@5, Precision@5, MRR and nDCG.
6. Store results.
7. Send evaluation scores to Langfuse.

## 14.4 Response Runner

File:

```text
evaluation/runners/run_response.py
```

Responsibilities:

1. Load response cases.
2. Run the complete RAG pipeline.
3. Capture:
   - User query
   - Retrieved context
   - Generated response
   - Citations
4. Run response evaluators.
5. Calculate scores.
6. Store results.
7. Send results to Langfuse.

---

# 15. Results Format

Evaluation results should be stored in a structured format.

Example:

```json
{
  "id": "RESP-001",
  "scores": {
    "correctness": 0.9,
    "faithfulness": 1.0,
    "relevance": 0.95,
    "completeness": 0.9,
    "citation": 1.0,
    "safety": 1.0
  },
  "passed": true
}
```

The exact result format can be adapted to the existing application architecture.

---

# 16. Implementation Order

## Phase 1 — Input Processor

Complete the Input Processor evaluation end-to-end first.

Tasks:

1. Create dataset.
2. Create evaluator.
3. Create runner.
4. Run test cases.
5. Calculate modality accuracy.
6. Calculate validation accuracy.
7. Investigate failures.
8. Add new edge cases where required.

## Phase 2 — Intent Classifier

After Input Processor evaluation works:

1. Create intent dataset.
2. Create intent evaluator.
3. Create intent runner.
4. Calculate accuracy.
5. Calculate precision.
6. Calculate recall.
7. Calculate F1.
8. Generate confusion matrix.
9. Investigate misclassifications.

## Phase 3 — Langfuse

After the first two evaluation components work:

1. Create/configure Langfuse project.
2. Add Langfuse credentials to environment variables.
3. Install Langfuse SDK.
4. Add tracing.
5. Record evaluation runs.
6. Record evaluation scores.
7. Verify traces in Langfuse.
8. Add LLM-as-a-Judge integration if required.

## Phase 4 — Retrieval

1. Export ChromaDB chunk IDs and metadata.
2. Create retrieval ground truth.
3. Create retrieval dataset.
4. Implement retrieval evaluator.
5. Implement retrieval runner.
6. Calculate Recall@5.
7. Calculate Precision@5.
8. Calculate MRR.
9. Calculate nDCG.
10. Investigate failed retrieval cases.

## Phase 5 — Response

1. Create response dataset.
2. Implement correctness evaluator.
3. Implement faithfulness evaluator.
4. Implement relevance evaluator.
5. Implement completeness evaluator.
6. Implement citation evaluator.
7. Implement safety evaluator.
8. Implement response runner.
9. Add LLM-as-a-Judge.
10. Add insufficient-evidence cases.
11. Compare LLM-judge results with human-reviewed cases.

---

# 17. Final Evaluation Flow

```text
Test Case
   |
   v
Input Processor
   |
   +----> Input Evaluation
   |
   v
Intent Classifier
   |
   +----> Intent Evaluation
   |
   v
Retriever / ChromaDB
   |
   +----> Retrieval Evaluation
   |
   v
Response Generator
   |
   +----> Correctness
   +----> Faithfulness
   +----> Relevance
   +----> Completeness
   +----> Citation
   +----> Safety
   |
   v
Evaluation Results
   |
   v
Langfuse
```

---

# 18. Important Design Principles

## Ground Truth Must Be Independent

Predictions from the system must never be used to define expected results.

Ground truth should come from:

- Manually created labels
- Authoritative government sources
- Manually verified chunks
- Human-reviewed expected answer criteria

## Do Not Create Excessive Test Cases Initially

Recommended initial sizes:

```text
Input Processor: ~39 cases
Intent:           ~50 cases
Retrieval:        ~40–60 cases
Response:         ~40–50 cases
```

The datasets can grow based on observed failures.

## Test Failures Should Improve the Dataset

```text
Failure
   ↓
Understand why it failed
   ↓
Add or modify evaluation case
   ↓
Fix system
   ↓
Run evaluation again
```

This allows the evaluation suite to become a regression test suite over time.

---

# 19. Information Needed Before Writing Evaluation Code

Before implementing the runners and evaluators, inspect the existing application code so the evaluation layer matches the actual architecture.

## Input Processor

Obtain:

- Input Processor implementation
- Existing evaluator, if any
- Existing input-processing output format
- 1–2 existing dataset examples

## Intent Classifier

Obtain:

- Intent Classifier implementation
- Existing evaluator, if any
- Existing classifier output format
- 1–2 existing dataset examples

## Retrieval

Obtain:

- ChromaDB population script
- Collection name
- Retriever implementation
- Chunk ID format
- Metadata format
- 1–2 exported chunks

## Response

Obtain:

- RAG pipeline response format
- Retrieved context format
- Citation format
- 1–2 sample responses

This should be inspected before writing the final evaluation runners so the evaluation code integrates with the existing project rather than assuming a different architecture.

---

# 20. Definition of Done

- [x] Input Processor has an evaluation dataset.
- [x] Input Processor evaluator works.
- [x] Input Processor runner works.
- [x] Modality accuracy is reported.
- [x] Validation accuracy is reported.
- [x] Intent dataset is implemented.
- [x] Intent evaluator works.
- [x] Intent runner works.
- [x] Accuracy, Precision, Recall and F1 are reported.
- [x] Confusion matrix is available.
- [x] Langfuse tracing is integrated.
- [x] Retrieval ground truth is created.
- [x] Retrieval evaluator works.
- [x] Recall@5 is reported.
- [x] Precision@5 is reported.
- [x] MRR is reported.
- [x] nDCG is reported.
- [x] Response dataset is implemented.
- [x] Correctness evaluation works.
- [x] Faithfulness evaluation works.
- [x] Relevance evaluation works.
- [x] Completeness evaluation works.
- [x] Citation evaluation works.
- [x] Safety evaluation works.
- [x] Insufficient-evidence cases are tested.
- [x] LLM-as-a-Judge is integrated where appropriate.
- [x] A human-reviewed subset validates the judge.
- [x] Evaluation results are visible/tracked in Langfuse.
- [x] Evaluation failures can be reproduced.
- [x] New failures can be added as regression cases.
