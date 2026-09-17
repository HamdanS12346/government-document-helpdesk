# Intent Decision

## Overview

`IntentDecision` is the output of the Intent Classifier Node.

Its purpose is to represent the classifier's decision about what type of request the user has made.

The Intent Classifier receives a classification query constructed from:

* The user's original query
* A preview of each attached image, if present
* A preview of each attached PDF, if present
* A bounded preview of each attached spreadsheet workbook, if present

The classifier does not need to process the full attachment content at this stage. The previews provide enough context to help determine the user's intent.

---

## Schema

```text
IntentDecision
├── query: str
├── intent_type: str
└── confidence_score: float
```

### `query`

```text
query: str
```

The query used by the Intent Classifier for making the intent decision.

It contains:

1. The user's original query from `NormalizedInput.user_query`
2. The preview of each attached image
3. The preview of each attached PDF
4. The bounded preview of each attached spreadsheet workbook

If there are no attachments, the query is simply the user's original query.

Example:

```text
User Query:
Can I use this document as proof of address?

Attached Image:
address_certificate.jpg
Preview:
Certificate of Residence
Name: Rahul Sharma
Address: ...
```

---

### `intent_type`

```text
intent_type: str
```

The intent classification produced by the Intent Classifier.

Currently, the supported intent types are:

```text
document_info
general_chat
ambiguous
```

#### `document_info`

The user is asking about a government document, procedure, eligibility, requirements, application, fee, timeline, or other government-service-related information.

This routes the workflow toward Retrieval.

#### `general_chat`

The request does not require government-document knowledge retrieval.

This routes the workflow toward the Response Node.

#### `ambiguous`

The user's request does not provide enough information to confidently determine the intended task.

This routes the workflow toward the Clarification Node.

---

### `confidence_score`

```text
confidence_score: float
```

Represents the classifier's confidence in its intent decision.

The value should be between:

```text
0.0 - 1.0
```

where:

```text
0.0 → very low confidence
1.0 → very high confidence
```

The exact confidence thresholds used for routing or clarification are not defined here and can be decided separately.

---

# Examples

## 1. Document Information

User:

```text
"What documents are required for PAN application?"
```

Intent decision:

```text
IntentDecision(
    query="What documents are required for PAN application?",
    intent_type="document_info",
    confidence_score=0.98
)
```

---

## 2. General Chat

User:

```text
"Hello, how are you?"
```

Intent decision:

```text
IntentDecision(
    query="Hello, how are you?",
    intent_type="general_chat",
    confidence_score=0.99
)
```

---

## 3. Ambiguous Request

User:

```text
"Can you check this?"
```

Attachment:

```text
document.jpg
```

Intent decision:

```text
IntentDecision(
    query="""
    User Query:
    Can you check this?

    Attached Image:
    document.jpg

    Preview:
    Certificate of Residence
    Name: Rahul Sharma
    ...
    """,
    intent_type="ambiguous",
    confidence_score=0.65
)
```

The workflow can then route this to the Clarification Node.

---

## 4. Document Information with Attachments

User:

```text
"Can I use these documents for the application?"
```

Attachments:

```text
identity_proof.jpg
address_proof.jpg
application_guidelines.pdf
```

The classifier receives the user's query plus the previews of all three attachments.

The resulting decision could be:

```text
IntentDecision(
    query="...",
    intent_type="document_info",
    confidence_score=0.94
)
```

## 5. Document Information with Spreadsheet Attachment

User:

```text
"What does this uploaded fee schedule say?"
```

Attachment:

```text
fee_schedule.xlsx
```

The classifier receives the user's query plus the workbook name and bounded deterministic spreadsheet preview. It does not receive raw workbook bytes, parser objects, full structured workbook data, or `combined_text`.

The resulting decision could be:

```text
IntentDecision(
    query="...",
    intent_type="document_info",
    confidence_score=0.92
)
```

---

# Role in the Workflow

```text
NormalizedInput
      ↓
Intent Classifier
      ↓
IntentDecision
      ↓
   ┌──┴───────────────┐
   │                  │
   v                  v
document_info     general_chat
   │                  │
   v                  v
Retrieval          Response
```

For an ambiguous request:

```text
IntentDecision
      ↓
ambiguous
      ↓
Clarification Node
      ↓
Intent Classifier
```

## Design Principle

`IntentDecision` should remain a simple contract.

The Intent Classifier is responsible only for determining the intent and returning the agreed decision object. The internal classification method, model, prompting strategy, and other implementation details are not part of this schema.
