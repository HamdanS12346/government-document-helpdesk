# Hallucination / Unsupported Information Evaluation — Implementation Plan

## 1. Objective

The **Hallucination / Unsupported Information Evaluation** will evaluate whether the government helpdesk chatbot makes factual claims that are not supported by the information retrieved from the knowledge base.

The evaluation should verify that the chatbot:

* Does not invent facts when information is unavailable.
* Does not fabricate fees, processing times, eligibility requirements, document requirements, or other government information.
* Correctly identifies when the retrieved context is insufficient to answer a question.
* Clearly communicates uncertainty when the required information is unavailable.
* Does not accept false or unsupported assumptions in the user's query as facts.
* Keeps factual claims grounded in the actual retrieved context.

### Primary evaluation question

> **Does the chatbot make factual claims that are unsupported by the context retrieved for the user's query?**

---

# 2. Difference from Existing Response Evaluation

This evaluation should complement, rather than duplicate, the existing **Response → Faithfulness** evaluation.

### Faithfulness

Checks:

> Is the generated response grounded in the retrieved context?

### Hallucination / Unsupported Information

Checks:

> Does the response contain unsupported factual claims, and does the chatbot appropriately handle information that is missing from the retrieved context?

The distinction should be maintained during implementation.

| Situation                                                       | Primary Evaluation                      |
| --------------------------------------------------------------- | --------------------------------------- |
| Response omits information that should have been provided       | Completeness                            |
| Response contains information unrelated to the query            | Relevance                               |
| Response makes a claim not supported by retrieved context       | Hallucination                           |
| Response correctly acknowledges that information is unavailable | Hallucination / Unsupported Information |
| Response contradicts retrieved information                      | Faithfulness / Hallucination            |

---

# 3. Evaluation Architecture

The evaluation should use the **actual connected chatbot graph** rather than isolated components.

```text
User Query
    |
    v
Connected RAG Graph
    |
    +----------------------+
    |                      |
    v                      v
Retrieved Context     Generated Response
    |                      |
    +----------+-----------+
               |
               v
   Hallucination Evaluator
               |
               v
      Claim-Level Analysis
               |
               +--------------------+
               |                    |
               v                    v
       Supported Claims      Unsupported Claims
               |                    |
               +---------+----------+
                         |
                         v
                Evaluation Score
```

---

# 4. Directory Structure

Add the following components to the existing evaluation structure:

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
│   ├── response/
│   │   └── cases.jsonl
│   └── hallucination/
│       └── cases.jsonl
│
├── evaluators/
│   ├── input_processor/
│   ├── intent/
│   ├── retrieval/
│   ├── response/
│   └── hallucination/
│       └── evaluator.py
│
├── runners/
│   ├── run_input_processor.py
│   ├── run_intent.py
│   ├── run_retrieval.py
│   ├── run_response.py
│   └── run_hallucination.py
│
├── configs/
│   └── thresholds.yaml
│
├── reports/
│
└── README.md
```

The existing `llm_judge.py` implementation can be reused as the underlying LLM-as-a-judge mechanism if it supports structured evaluation output.

---

# 5. Define Evaluation Test Categories

The hallucination dataset should contain multiple types of cases rather than only normal questions.

Start with approximately **30 test cases**.

Recommended distribution:

| Test Category                  | Number | Purpose                                                                            |
| ------------------------------ | -----: | ---------------------------------------------------------------------------------- |
| Fully supported                |     10 | Verify that supported answers are not incorrectly classified as hallucinations     |
| Partially supported            |      5 | Test whether the chatbot avoids guessing missing information                       |
| Completely unsupported         |      5 | Test whether the chatbot refuses or acknowledges unavailable information           |
| False premise                  |      5 | Test whether the chatbot challenges unsupported assumptions                        |
| Numerical / eligibility claims |      5 | Test high-risk hallucination areas such as fees, processing times, and eligibility |
| **Total**                      | **30** |                                                                                    |

The dataset can be expanded later based on observed failures.

---

# 6. Test Category 1 — Fully Supported Information

These cases contain enough information in the retrieved context to answer the question.

### Example

Retrieved context:

```text
An Indian passport serves as an identity document
and facilitates international travel.
```

User:

```text
What is the purpose of an Indian passport?
```

Expected behavior:

```text
The chatbot should answer using the available information.
No hallucination should be detected.
```

Purpose:

* Establish a baseline.
* Ensure valid answers are not incorrectly classified as hallucinations.
* Test evaluator false-positive behavior.

---

# 7. Test Category 2 — Partially Supported Information

These cases contain some information required to answer the query but not all of it.

### Example

Retrieved context:

```text
An Indian passport is required for international travel.
```

User:

```text
What is the passport fee and processing time?
```

Expected behavior:

* The chatbot should not invent a fee.
* The chatbot should not invent a processing time.
* The chatbot may state that the available information does not specify these details.
* The chatbot may direct the user to the appropriate official source if supported by the system.

Purpose:

* Test whether the chatbot knows when information is missing.
* Detect partial hallucinations.

---

# 8. Test Category 3 — Completely Unsupported Information

These cases ask for information that is not present in the retrieved context.

### Example

Retrieved context:

```text
Information about passport eligibility.
```

User:

```text
How long does passport processing take?
```

If processing time is not included in the context, the chatbot should not provide a specific processing time.

Expected behavior:

```text
The available information does not specify the processing time.
```

Purpose:

* Test refusal/uncertainty behavior.
* Detect fabricated information.

---

# 9. Test Category 4 — False Premise

These cases contain an assumption that may not be supported by the knowledge base.

### Example

User:

```text
What is the 50% discount available to senior citizens
when applying for an Indian passport?
```

If the retrieved context contains no evidence of such a discount, the chatbot should not accept the premise as fact.

Expected behavior:

```text
The chatbot should indicate that the available information
does not confirm such a discount.
```

Purpose:

* Test whether the model blindly accepts user-provided claims.
* Detect fabricated policies, schemes, discounts, or benefits.

---

# 10. Test Category 5 — Numerical and Eligibility Claims

These should receive special attention because numerical information is particularly important in a government-document chatbot.

Create cases involving:

* Application fees
* Processing times
* Age requirements
* Validity periods
* Number of required documents
* Penalties
* Eligibility requirements
* Application charges

### Example

User:

```text
How much does the application cost?
```

If the retrieved context does not contain a fee, the chatbot should not invent one.

Expected behavior:

```text
The chatbot should state that the fee is not specified
in the available information.
```

---

# 11. Dataset Structure

Create:

```text
evaluation/datasets/hallucination/cases.jsonl
```

Each case should contain the information required to evaluate the chatbot's behavior.

Example:

```json
{
  "id": "HAL-001",
  "query": "What is the purpose of an Indian passport?",
  "expected_behavior": "supported",
  "expected_key_points": [
    "Passport serves as an identity document",
    "Passport facilitates international travel"
  ],
  "hallucination_expected": false,
  "metadata": {
    "document": "Indian Passport",
    "category": "Travel & Immigration",
    "test_type": "fully_supported"
  }
}
```

Example unsupported case:

```json
{
  "id": "HAL-002",
  "query": "What is the passport processing time?",
  "expected_behavior": "should_not_guess",
  "expected_key_points": [],
  "hallucination_expected": false,
  "metadata": {
    "document": "Indian Passport",
    "category": "Travel & Immigration",
    "test_type": "unsupported_information"
  }
}
```

> `hallucination_expected` should represent the expected behavior of the chatbot, not whether the test case is designed to potentially trigger a hallucination.

---

# 12. Execute the Actual Connected Graph

The hallucination runner should execute the same connected graph used by the chatbot.

Do not create a separate retrieval implementation for this evaluation.

Conceptually:

```python
result = run_graph(query)
```

The graph should provide:

```python
{
    "query": query,
    "retrieved_context": [...],
    "response": "...",
    "citations": [...]
}
```

The evaluation should use:

* Actual user query
* Actual retrieved context
* Actual generated response

This ensures that the evaluation measures hallucinations produced by the real system.

---

# 13. Implement `run_hallucination.py`

Create:

```text
evaluation/runners/run_hallucination.py
```

The runner should:

1. Load `cases.jsonl`.
2. Iterate through each test case.
3. Send the query to the connected graph.
4. Capture the actual retrieved context.
5. Capture the generated response.
6. Pass the query, context, and response to the hallucination evaluator.
7. Store the evaluation result.
8. Calculate aggregate metrics.
9. Optionally send evaluation scores to Langfuse.

Conceptually:

```python
for case in dataset:

    result = run_graph(case["query"])

    evaluation = evaluate_hallucination(
        query=case["query"],
        retrieved_context=result["retrieved_context"],
        response=result["response"],
        expected_behavior=case["expected_behavior"]
    )

    save_result(evaluation)
```

---

# 14. Implement `evaluators/hallucination/evaluator.py`

Create:

```text
evaluation/evaluators/hallucination/evaluator.py
```

The evaluator should perform **claim-level analysis** rather than simply asking whether the entire response is hallucinated.

Inputs:

```text
Query
Retrieved Context
Generated Response
Expected Behavior
```

The evaluator should:

1. Identify factual claims in the response.
2. Compare each claim against the retrieved context.
3. Determine whether each claim is supported.
4. Identify unsupported claims.
5. Determine whether the chatbot appropriately handled missing information.
6. Calculate an overall score.
7. Return structured output.

---

# 15. Claim-Level Evaluation

For example, suppose the chatbot produces:

```text
A passport is required for international travel.
The application fee is ₹1,500 and processing takes 15 days.
```

The evaluator should identify:

```text
Claim 1:
Passport is required for international travel.

Claim 2:
Application fee is ₹1,500.

Claim 3:
Processing takes 15 days.
```

Then evaluate:

| Claim                                         | Supported? |
| --------------------------------------------- | ---------- |
| Passport is required for international travel | Yes        |
| Application fee is ₹1,500                     | No         |
| Processing takes 15 days                      | No         |

Result:

```text
Total claims: 3
Supported claims: 1
Unsupported claims: 2
```

---

# 16. LLM Judge Prompt

The evaluator can use the existing `llm_judge.py` infrastructure.

The judge should receive:

```text
USER QUERY:

{query}

RETRIEVED CONTEXT:

{retrieved_context}

CHATBOT RESPONSE:

{response}

EXPECTED BEHAVIOR:

{expected_behavior}
```

The judge should be instructed to:

* Identify factual claims.
* Determine whether each claim is supported by the retrieved context.
* Avoid using outside knowledge when deciding whether a claim is grounded.
* Identify unsupported claims.
* Distinguish between an unsupported claim and an appropriate statement of uncertainty.
* Determine whether the chatbot correctly avoided guessing when information was unavailable.

---

# 17. Structured Evaluation Output

The evaluator should return structured JSON.

Example:

```json
{
  "score": 0.33,
  "hallucination_detected": true,
  "claims": [
    {
      "claim": "Passport is required for international travel.",
      "supported": true,
      "evidence": "Retrieved chunk 1"
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
  "reason": "The response contains two factual claims that are not supported by the retrieved context."
}
```

---

# 18. Scoring

Use the existing **0–1 evaluation scale**.

A simple hallucination score can be calculated as:

```text
Hallucination Score =
Number of supported factual claims
-----------------------------------
Total factual claims
```

Examples:

### All claims supported

```text
3 supported / 3 claims = 1.0
```

### One unsupported claim

```text
2 supported / 3 claims = 0.67
```

### All claims unsupported

```text
0 supported / 3 claims = 0.0
```

---

# 19. Correct Handling of Missing Information

A response should **not be penalized** simply because it does not provide information that was unavailable.

Example:

```text
User:
What is the passport processing time?

Retrieved context:
Processing time is not specified.

Chatbot:
The available information does not specify the processing time.
```

This should receive a high score.

The evaluation should reward the chatbot for:

* Acknowledging missing information.
* Avoiding unsupported claims.
* Avoiding fabricated numbers.
* Clearly communicating uncertainty.

---

# 20. Add an Unsupported Information Handling Score

In addition to the main hallucination score, consider tracking:

```text
unsupported_information_handling
```

Example:

| Behavior                                   | Hallucination Score | Handling Score |
| ------------------------------------------ | ------------------: | -------------: |
| All claims supported                       |                 1.0 |            1.0 |
| Unsupported claim invented                 |                 0.0 |            0.0 |
| Missing information correctly acknowledged |                 1.0 |            1.0 |
| Partially guesses missing information      |                 0.5 |            0.5 |
| Clearly refuses to guess                   |                 1.0 |            1.0 |

This distinguishes **not knowing something** from **making something up**.

---

# 21. Evaluation Metrics

Calculate the following metrics after running the dataset.

### 1. Average Hallucination Score

```text
Average hallucination score across all test cases
```

### 2. Hallucination Rate

```text
Cases containing one or more unsupported claims
------------------------------------------------
Total test cases
```

### 3. Unsupported Claim Rate

```text
Total unsupported claims
------------------------
Total factual claims
```

### 4. Unsupported Information Handling Rate

Percentage of cases where the chatbot correctly acknowledged that information was unavailable instead of guessing.

### 5. False Positive Rate

Cases where the evaluator incorrectly identifies a supported claim as unsupported.

This is important for validating the evaluator itself.

---

# 22. Example Evaluation Report

The runner should produce something similar to:

```text
Hallucination Evaluation
========================

Total Cases: 30

Average Hallucination Score: 0.91

Hallucination Rate: 10.0%

Unsupported Claim Rate: 7.2%

Unsupported Information Handling: 93.3%

Cases with Hallucinations: 3

Cases Correctly Handling Missing Information: 14
```

Also record the individual failures:

```text
HAL-012
---------
Query:
What is the passport processing time?

Unsupported Claim:
"Passport processing takes 15 working days."

Reason:
Processing time was not present in the retrieved context.
```

---

# 23. Testing the Evaluator

Before trusting the evaluator, manually validate a subset of results.

Use approximately:

```text
10 test cases
```

Manually classify each response:

```text
Human judgment
      vs.
LLM evaluator judgment
```

Compare:

* Supported vs unsupported classification
* Unsupported claim identification
* Score
* Reason

Investigate disagreements.

This step is important because the hallucination evaluator itself can produce false positives or false negatives.

---

# 24. Tune the Evaluator

After the first evaluation run, review incorrect classifications.

Common problems may include:

### Problem 1 — Judge uses outside knowledge

The evaluator decides a claim is true because it knows the fact, even though the retrieved context doesn't contain it.

**Fix:**

Explicitly instruct the judge to evaluate support **only against the provided retrieved context**.

### Problem 2 — Paraphrases incorrectly classified as hallucinations

The response uses different wording from the retrieved chunk.

**Fix:**

Allow semantic equivalence and paraphrasing.

### Problem 3 — Common-sense statements incorrectly classified

The model may treat generic statements as factual claims requiring evidence.

**Fix:**

Define what constitutes a material factual claim for the evaluation.

### Problem 4 — Appropriate uncertainty marked as incomplete

A chatbot may correctly say that information is unavailable.

**Fix:**

Explicitly reward appropriate uncertainty/refusal behavior.

---

# 25. Langfuse Integration

After the local evaluation is working correctly, integrate the results with Langfuse.

For each evaluation trace, record:

```text
hallucination_score
unsupported_claims
unsupported_information_handling
```

Conceptually:

```text
Trace
│
├── Input Processor
├── Intent
├── Retrieval
├── Response
│
└── Evaluation
    ├── hallucination_score = 0.90
    ├── unsupported_claims = 1
    └── unsupported_information_handling = 1.0
```

The evaluation should use the shared Langfuse project once the project migration/consolidation is complete.

---

# 26. Recommended Implementation Order

Implement the evaluation in the following order:

```text
Step 1
Define hallucination criteria
        ↓
Step 2
Create 30-case hallucination dataset
        ↓
Step 3
Connect runner to actual chatbot graph
        ↓
Step 4
Capture actual retrieved context
        ↓
Step 5
Capture actual generated response
        ↓
Step 6
Implement claim-level evaluator
        ↓
Step 7
Reuse existing LLM judge infrastructure
        ↓
Step 8
Return structured evaluation results
        ↓
Step 9
Calculate hallucination metrics
        ↓
Step 10
Manually validate evaluator results
        ↓
Step 11
Tune evaluator based on errors
        ↓
Step 12
Run complete 30-case evaluation
        ↓
Step 13
Integrate results with Langfuse
        ↓
Step 14
Expand dataset using real failure cases
```

---

# 27. Final Deliverables

At the end of the implementation, the following should exist:

```text
evaluation/
│
├── datasets/
│   └── hallucination/
│       └── cases.jsonl
│
├── evaluators/
│   └── hallucination/
│       └── evaluator.py
│
├── runners/
│   └── run_hallucination.py
│
└── reports/
    └── hallucination_report.json
```

The evaluation should provide:

* Per-case hallucination score
* Claim-level support analysis
* Unsupported claim count
* Unsupported claim explanations
* Unsupported-information handling score
* Aggregate hallucination rate
* Unsupported claim rate
* Failure cases
* Results suitable for Langfuse

---

# 28. Success Criteria

The evaluation implementation can be considered complete when:

* [ ] A dedicated hallucination dataset exists.
* [ ] Dataset contains supported and unsupported-information scenarios.
* [ ] At least 30 test cases are available.
* [ ] The actual connected chatbot graph is used.
* [ ] Actual retrieved context is captured.
* [ ] Actual generated responses are evaluated.
* [ ] Evaluation is performed at claim level.
* [ ] Unsupported claims are identified.
* [ ] Appropriate uncertainty/refusal is rewarded.
* [ ] Hallucination score is calculated consistently.
* [ ] Evaluation results are manually validated.
* [ ] False positives and false negatives are reviewed.
* [ ] Evaluator has been tuned based on validation results.
* [ ] Results are integrated with Langfuse.
* [ ] The evaluation can be rerun automatically using `run_hallucination.py`.
* [ ] Real failure cases can be added back into the dataset for regression testing.
