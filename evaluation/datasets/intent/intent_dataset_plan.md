# Intent Classification Dataset Creation Plan

## 1. Objective

Create an evaluation dataset for the Intent Classification component of the chatbot.

The dataset will verify whether the system correctly classifies user input into one of three intents:

1. `document_info`
2. `general_chat`
3. `ambiguous`

The dataset will be used by the Intent evaluator to compare the application's predicted intent against manually defined ground truth.

## 2. Dataset Location

Create:

```text
evaluation/
└── datasets/
    └── intent/
        └── cases.jsonl
```

Use a single `cases.jsonl` file. Each test case is one JSON object on one line. Do not create a separate JSON file for each case.

## 3. Dataset Case Structure

Each case should contain:

- `id` — unique test-case identifier.
- `input` — the user's input.
- `expected_intent` — the manually defined correct intent.

Example:

```json
{"id":"INT-001","input":"What documents are required to apply for a passport?","expected_intent":"document_info"}
```

The exact field names should match the actual Intent Classification component once its schema is finalized.

## 4. Intent Categories

### 4.1 Document Information — `document_info`

Use this class when the user is clearly asking for information about a government document or its online application.

Cover the chatbot's supported information fields:

- Purpose
- Eligibility
- Required Documents
- Procedure
- Fees

Examples:

```text
What documents are required to apply for a passport?
How much does an OCI card cost?
Who is eligible for a disability certificate?
How do I apply for a passport?
What is the purpose of an OCI card?
```

Also include paraphrases such as:

- What paperwork do I need?
- How much does it cost?
- What are the charges?
- What is the application process?
- Am I eligible?
- Can I apply for this document?

The goal is to test semantic intent classification rather than simple keyword matching.

### 4.2 General Chat — `general_chat`

Use this class for inputs clearly unrelated to government document information.

Include:

- Greetings.
- Casual conversation.
- General knowledge.
- Technology questions.
- Mathematics.
- Writing requests.
- Other unrelated questions.

Examples:

```text
Hello, how are you?
What is the capital of France?
Can you explain artificial intelligence?
What is 25 multiplied by 4?
```

The purpose is to verify that unrelated questions are not incorrectly routed to the government-document RAG workflow.

### 4.3 Ambiguous — `ambiguous`

Use this class when there is not enough information to confidently determine the user's intended request.

Examples:

```text
Passport
I need a visa.
Documents?
How do I get it?
What is the fee?
```

These inputs may mention a government document but do not provide enough information to determine what the user wants.

This class is important because the classifier should not automatically classify every input containing a document name as `document_info`.

## 5. Recommended Dataset Distribution

Start with approximately 50 cases:

| Intent | Suggested Cases |
|---|---:|
| `document_info` | 20 |
| `general_chat` | 15 |
| `ambiguous` | 15 |
| **Total** | **50** |

Keeping the classes reasonably balanced helps prevent the evaluation from being dominated by one intent.

## 6. Document Information Test Matrix

For `document_info`, distribute questions across the actual documents supported by the chatbot.

For example:

| Information Type | Example |
|---|---|
| Purpose | What is the purpose of an Indian passport? |
| Eligibility | Who can apply for an OCI card? |
| Required Documents | What documents are needed for a disability certificate? |
| Procedure | How do I apply for a passport? |
| Fees | How much does a passport application cost? |

Use the document types actually supported by the chatbot, such as:

- Passport
- Visa
- OCI
- Certificate of Disability
- Tax/Financial documents

## 7. Paraphrase and Variation Strategy

Do not create every case using the same sentence pattern.

For example, all of the following can represent `document_info`:

```text
What is the passport fee?
How much does it cost to apply for a passport?
How much do I need to pay for a passport?
What are the charges for getting a passport?
```

This helps test whether the classifier understands meaning rather than exact phrases.

## 8. Borderline Cases

Include cases that test the boundary between the three classes.

Examples:

```text
What documents do I need to apply for an Indian passport?
```

→ `document_info`

```text
Passport
```

→ `ambiguous`

```text
What is the weather like today?
```

→ `general_chat`

```text
I need a passport.
```

→ `ambiguous`

These cases are particularly valuable because they test whether the classifier makes the correct decision when the input is not obviously classifiable.

## 9. Contextual / Incomplete Queries

Include cases such as:

```text
What is the fee?
Which documents?
How do I get it?
Can I apply?
```

Unless the Intent Classifier explicitly receives conversation history, these should generally be labeled `ambiguous`.

If the application uses conversation context, create separate test cases that explicitly define the available context and expected intent.

## 10. Negative Examples

Include unrelated inputs that contain words associated with government documents.

For example, create cases where words such as `passport`, `visa`, or `document` appear but the user's actual intent is not government-document information.

This helps reduce keyword-based false positives.

## 11. Ground Truth Rules

Ground truth should be defined manually.

For every case:

1. Read the input independently.
2. Determine the user's primary intent.
3. Assign exactly one of:
   - `document_info`
   - `general_chat`
   - `ambiguous`
4. Do not use the classifier's prediction when defining the expected intent.
5. Review borderline cases separately.

The evaluation compares:

```text
Expected Intent
      ↓
    versus
      ↓
Actual Predicted Intent
```

## 12. Case Creation Process

### Step 1 — Confirm Intent Definitions

Write precise rules for:

```text
document_info
general_chat
ambiguous
```

The definitions should be clear enough for consistent manual labeling.

### Step 2 — List Supported Documents

Use the actual document categories currently supported by the chatbot.

### Step 3 — Create the Test Matrix

Create cases across:

- Intent classes.
- Document types.
- Information types.
- Different phrasings.
- Different levels of specificity.

### Step 4 — Add Borderline Cases

Deliberately create cases where the classifier could confuse:

- `document_info` vs `ambiguous`
- `general_chat` vs `ambiguous`
- `document_info` vs `general_chat`

### Step 5 — Manually Review Labels

Verify every `expected_intent` before running the evaluation.

### Step 6 — Save as JSONL

Store all cases in:

```text
evaluation/datasets/intent/cases.jsonl
```

## 13. Quality Checks

Before using the dataset, verify:

- Every case has a unique ID.
- Every case contains an input.
- Every case has exactly one expected intent.
- Only the three allowed intent labels are used.
- The three classes have reasonable representation.
- `document_info` covers the supported government documents.
- Different phrasings are represented.
- Borderline and ambiguous cases are represented.
- Unrelated general-chat cases are represented.
- Ground truth was defined independently of the classifier's prediction.
- No case depends on hidden context unless that context is explicitly part of the test case.

## 14. Evaluation Metrics

The dataset should support:

### Accuracy

Percentage of inputs classified correctly.

```text
Correct Predictions / Total Cases
```

### Precision

Measure precision separately for:

- `document_info`
- `general_chat`
- `ambiguous`

### Recall

Measure recall separately for:

- `document_info`
- `general_chat`
- `ambiguous`

### F1 Score

Use F1 to combine precision and recall for each intent.

### Confusion Matrix

Use a confusion matrix to identify errors such as:

```text
document_info → ambiguous
ambiguous → document_info
general_chat → document_info
```

This is especially useful for determining whether the classifier is too aggressive about routing inputs to the RAG system.

## 15. Expansion Strategy

Start with approximately 50 cases rather than creating a very large dataset immediately.

After running the evaluation:

1. Identify incorrectly classified cases.
2. Determine which intent boundary caused the failure.
3. Add cases representing that failure pattern.
4. Keep the original case as a regression test.
5. Re-run the evaluation.

For example, if the classifier frequently misclassifies:

```text
I need a passport.
```

as `document_info`, add more similar incomplete requests to test that boundary.

The dataset should evolve based on actual failures while preserving the original evaluation cases.

## 16. Final Deliverable

The initial deliverable is:

```text
evaluation/
└── datasets/
    └── intent/
        └── cases.jsonl
```

The file should initially contain approximately 50 manually reviewed cases covering:

- `document_info`
- `general_chat`
- `ambiguous`
- Government-document variations.
- Paraphrases.
- Borderline cases.
- Incomplete inputs.
- Negative/unrelated examples.

The dataset should remain independent of the Intent Classification implementation so it can be reused whenever the classifier, prompt, or model is changed.
