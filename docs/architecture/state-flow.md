# Workflow State Flow

## Overview

This document defines what each major node receives from and writes to the shared LangGraph `State`.

The internal implementation of each node is independent. The agreed state inputs and outputs act as the contract between nodes.

## State

```text
State
|-- normalized_input
|-- intent_decision
|-- documents
|-- retrieved_context
|-- messages
`-- conversation_summary
```

## 1. Input Processor Node

### Receives

Raw user input:

- User text/query
- Attached images
- Attached PDFs

### Writes

- `normalized_input`

The output follows the `NormalizedInput` schema.

### Flow

```text
Raw User Input
      |
      v
Input Processor
      |
      v
normalized_input
```

## 2. Intent Classifier Node

### Receives

- `normalized_input`
- `messages`
- `conversation_summary`

The Intent Classifier uses:

- `normalized_input.user_query`
- Preview of each attached image
- Preview of each attached PDF
- Relevant conversation context from `messages`
- `conversation_summary`

The conversation context helps the classifier understand the user's current request in relation to previous turns.

### Writes

- `intent_decision`

The output follows the `IntentDecision` schema.

### Flow

```text
normalized_input
        +
messages
        +
conversation_summary
        |
        v
Intent Classifier
        |
        v
intent_decision
```

## 3. Clarification Node

The Clarification Node is used when:

```text
intent_decision.intent_type == "ambiguous"
```

### Receives

- `normalized_input`
- `intent_decision`
- `messages`
- `conversation_summary`

The node uses the current request and conversation context to determine what clarification is needed.

It uses LangGraph interrupt to pause the workflow and wait for the user's clarification.

### Writes

The clarification interaction is added to:

- `messages`

After the user provides clarification, the workflow returns to the Intent Classifier.

### Flow

```text
intent_decision
        |
        v
   ambiguous
        |
        v
Clarification Node
        |
        v
    interrupt
        |
        v
User Clarification
        |
        v
Intent Classifier
```

## 4. Retriever Node

The Retriever is used when:

```text
intent_decision.intent_type == "document_info"
```

### Receives

- `normalized_input`
- `intent_decision`
- `messages`
- `conversation_summary`

The Retriever uses the relevant state information to understand the current request.

It may perform query optimization before retrieval, using the current user query and relevant conversation context to construct an effective retrieval query.

The Retriever can also use relevant normalized attachment content when the user's request depends on an attached document or image.

### Writes

- `documents`

`documents` is a list of retrieved documents, chunks, or evidence.

### Flow

```text
normalized_input
        +
intent_decision
        +
messages
        +
conversation_summary
        |
        v
Retriever
        |
        v
documents
```

## 5. Context Builder Node

### Receives

- `normalized_input`
- `intent_decision`
- `documents`
- `messages`
- `conversation_summary`

The Context Builder organizes the retrieved documents/evidence into the context required by the Response Node.

Its purpose is to create a clean, relevant, and bounded context while preserving the information required for source attribution.

### Writes

- `retrieved_context`

### Flow

```text
documents
    +
relevant state context
    |
    v
Context Builder
    |
    v
retrieved_context
```

## 6. Response Node

### Receives

- `normalized_input`
- `intent_decision`
- `retrieved_context`
- `messages`
- `conversation_summary`

For `document_info`:

- `retrieved_context` provides the retrieved evidence.
- `normalized_input` provides the user's multimodal input.
- `messages` and `conversation_summary` provide conversation context.

For `general_chat`:

- Retrieval may not have occurred.
- The response can be generated using the user's input and conversation context.

### Writes

The generated response is added to:

- `messages`

### Flow

```text
normalized_input
        +
intent_decision
        +
retrieved_context
        +
messages
        +
conversation_summary
        |
        v
Response Node
        |
        v
AI Message
        |
        v
messages
```

## High-Level Node Contracts

| Node | State Inputs | State Outputs |
| --- | --- | --- |
| Input Processor | Raw user input, attachments | `normalized_input` |
| Intent Classifier | `normalized_input`, `messages`, `conversation_summary` | `intent_decision` |
| Clarification Node | `normalized_input`, `intent_decision`, `messages`, `conversation_summary` | `messages` |
| Retriever | `normalized_input`, `intent_decision`, `messages`, `conversation_summary` | `documents` |
| Context Builder | `normalized_input`, `intent_decision`, `documents`, `messages`, `conversation_summary` | `retrieved_context` |
| Response Node | `normalized_input`, `intent_decision`, `retrieved_context`, `messages`, `conversation_summary` | `messages` |

## Routing

```text
Input Processor
      |
      v
normalized_input
      |
      v
Intent Classifier
      |
      v
intent_decision
      |
      +--------------------+--------------------+
      |                    |                    |
      v                    v                    v
document_info          ambiguous          general_chat
      |                    |                    |
      v                    v                    |
Retriever          Clarification Node           |
      |                    |                    |
      v                    v                    |
documents        User Clarification             |
      |                    |                    |
      v                    v                    |
Context Builder   Intent Classifier             |
      |                                         |
      +--------------------+--------------------+
                           |
                           v
                       Response
```

## Conversation Context

Conversation context is represented by:

- `messages`
- `conversation_summary`

Both can be provided to nodes where understanding the current request depends on previous conversation.

The `messages` state contains the available conversation message window, while `conversation_summary` provides a compact representation of earlier relevant conversation context.

## Design Principle

Nodes communicate through the shared `State`.

Each node has:

```text
Defined State Inputs
        |
        v
Internal Implementation
        |
        v
Defined State Outputs
```

The internal implementation of a node is not part of the contract between team members.

Only the agreed state fields and schemas need to be respected when integrating nodes.
