# Overall Architecture

## Overview

The Government Document Helpdesk is a multimodal chatbot orchestrated using LangGraph.

The system accepts user queries through text, images, PDFs, or a combination of these inputs.

The architecture is designed around independent nodes with clear contracts. Each node operates on shared LangGraph `State` and is responsible for producing defined outputs.

The internal implementation of each node is independent from the other nodes as long as the agreed state and schema contracts are followed.

---

# High-Level Architecture

```text
User Input
(Text / Image / PDF / Mixed)
        |
        v
Input Processor
        |
        v
Normalized Input
        |
        v
Intent Classifier
        |
        v
Intent Decision
        |
   +----+----------------------+
   |                           |
   v                           v
document_info              ambiguous
   |                           |
   v                           v
Retriever                Clarification
   |                           |
   v                           |
Documents                      |
   |                           |
   v                           |
Context Builder                |
   |                           |
   v                           |
Retrieved Context              |
   |                           |
   +-------------+-------------+
                 |
                 v
             Response
                 |
                 v
            AI Message
```

`general_chat` requests from the Intent Classifier can proceed directly to the Response Node without retrieval.

---

# LangGraph State

The workflow uses a shared state containing the main information required across nodes.

The current state fields are `normalized_input`, `intent_decision`, `documents`, `retrieved_context`, `messages`, `conversation_summary`, and `clarification_round_count`.

```text
State
├── normalized_input
├── intent_decision
├── documents
├── retrieved_context
├── messages
└── conversation_summary
```

## State Responsibilities

### `normalized_input`

Contains the normalized representation of the user's multimodal input.

It includes:

- User query
- Processed image content
- Processed PDF content
- Combined textual representation

Detailed structure:

```text
normalized_input
    → NormalizedInput
```

See `normalized-input.md` for the detailed schema.

---

### `intent_decision`

Contains the result of intent classification.

```text
intent_decision
    → IntentDecision
```

The decision identifies whether the request is:

```text
document_info
general_chat
ambiguous
```

It also contains the classification confidence and the query used for classification.

See `intentdecision.md` for the detailed schema.

---

### `documents`

Contains the documents/chunks/evidence returned by the Retriever.

```text
documents
    → list of retrieved documents/nodes
```

The detailed retrieval representation will be defined separately.

---

### `retrieved_context`

Contains the context prepared from retrieved documents for the Response Node.

```text
retrieved_context
    → prepared response context
```

This is the information that will be provided to the LLM for grounded response generation.

---

### `messages`

Contains the conversation messages, including human and AI messages.

It represents the available conversation message window used by nodes that require recent conversational context.

---

### `conversation_summary`

Contains a compact summary of relevant previous conversation context.

It complements the `messages` window when the complete conversation history should not be passed to a node.

---

### `clarification_round_count`

Tracks consecutive clarification turns for the active request.

This prevents unbounded clarification loops and prepares the graph state for later durable memory/checkpoint persistence.

---

# Conversation Context

Conversation context is represented through:

```text
messages
conversation_summary
```

Both can be provided to nodes where understanding the current request depends on previous conversation.

For example:

```text
Intent Classifier
    ← normalized_input
    ← messages
    ← conversation_summary
```

The conversation context allows the system to understand requests that depend on previous turns.

Example:

```text
User: What documents do I need for PAN?
Assistant: ...
User: What about the second one?
```

The second request cannot always be understood from `user_query` alone, so conversation context is available to the relevant nodes.

---

# Node Responsibilities

## Input Processor

Responsible for converting raw multimodal user input into:

```text
normalized_input
```

It handles the modality-specific processing required to create the normalized representation.

---

## Intent Classifier

Responsible for determining the type of user request.

Receives:

```text
normalized_input
messages
conversation_summary
```

Produces:

```text
intent_decision
```

---

## Clarification Node

Used when:

```text
intent_decision.intent_type == "ambiguous"
```

Receives:

```text
intent_decision.intent_type
intent_decision.query
messages
conversation_summary
clarification_round_count
```

Produces:

```text
messages
clarification_round_count
```

It uses the classifier-facing query and conversation context to ask the user for clarification.

It does not inspect `normalized_input` directly. Attachment context reaches clarification through `intent_decision.query`, because the Intent Classifier already incorporates relevant image/PDF previews into that query.

For the current backend milestone, the clarification path writes the clarification `AIMessage` to graph state and returns a completed graph result. Durable conversation persistence across HTTP requests is left to the memory/checkpoint branch.

The workflow then returns to the Intent Classifier.

---

## Retriever

Used for:

```text
intent_type == "document_info"
```

It uses the current request and relevant conversation context to perform retrieval.

Query optimization can occur within this stage.

Produces:

```text
documents
```

---

## Context Builder

Takes the retrieved documents/evidence and constructs the context required by the Response Node.

Produces:

```text
retrieved_context
```

The context is organized and bounded while preserving the information needed for source attribution and traceability.

---

## Response Node

Responsible for generating the final response using the LLM.

It can use:

```text
normalized_input
intent_decision
retrieved_context
messages
conversation_summary
```

The generated response is added to:

```text
messages
```

---

# State Flow

```text
Raw User Input
      |
      v
Input Processor
      |
      | writes
      v
normalized_input
      |
      v
Intent Classifier
      |
      | writes
      v
intent_decision
      |
      +----------------------+
      |                      |
      | document_info        | ambiguous
      v                      v
Retriever              Clarification
      |                      |
      | writes               |
      v                      |
documents                    |
      |                      |
      v                      |
Context Builder              |
      |                      |
      | writes               |
      v                      |
retrieved_context            |
      |                      |
      +----------+-----------+
                 |
                 v
             Response
                 |
                 | writes
                 v
              messages
```

For `general_chat`:

```text
Intent Classifier
      |
      | general_chat
      v
Response
```

---

# Node Contract Principle

Each node is treated as an independent component.

```text
State Input
     ↓
   Node
     ↓
State Output
```

Team members can implement nodes independently as long as they follow the agreed contracts.

For example:

```text
Input Processor
    IN  → raw user input
    OUT → normalized_input

Intent Classifier
    IN  → normalized_input + conversation context
    OUT → intent_decision

Retriever
    IN  → normalized_input + intent decision + conversation context
    OUT → documents

Context Builder
    IN  → documents + relevant state
    OUT → retrieved_context

Response
    IN  → relevant state + conversation context
    OUT → messages
```

The internal implementation of each node is not part of the integration contract.

---

# Architecture Documents

The architecture is separated into multiple documents so that the overall architecture remains simple while individual contracts can be defined independently.

```text
architecture.md
    |
    +── state.md
    |
    +── normalized-input.md
    |
    +── intentdecision.md
    |
    +── flow.md
    |
    +── retrieval schema/contract
    |
    +── response/context schema/contract
    |
    └── other component-specific documents
```

`architecture.md` defines the overall system structure.

The individual schema documents define the detailed contracts used between nodes.

---

# Design Principle

The system follows a **contract-first, modular node architecture**.

The main principle is:

> **What happens inside a node is an implementation concern. What matters for integration is the agreed input and output contract.**

This allows multiple team members to work on different nodes in parallel without requiring knowledge of each other's internal implementation.
