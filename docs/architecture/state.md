# State

## Overview

The LangGraph state is the shared state passed through the workflow. It stores information produced by different nodes so that each node can work independently through agreed input/output contracts.

The state should remain simple and contain only information needed by the workflow.

## High-Level State

```text
State
├── normalized_input
├── intent_decision
├── documents
├── retrieved_context
├── messages
└── conversation_summary
```

### 1. Normalized Input

`normalized_input` stores the normalized representation of the user's multimodal input, including the user's query and processed information from attached images/PDFs.

The detailed schema will be defined separately in the Input Processor schema.

### 2. Intent Decision

`intent_decision` stores the classification produced by the Intent Classifier, including the detected intent, confidence, and classification query.

The detailed schema will be defined separately in the Intent Decision schema.

### 3. Documents

`documents` stores the documents/nodes returned by the retrieval stage.

It is a list because retrieval can return multiple relevant documents or chunks.

The detailed structure will be defined separately as part of the retrieval contract.

### 4. Retrieved Context

`retrieved_context` stores the context prepared from retrieved documents for the Response Node.

At a high level, this is the context provided to the LLM for answer generation.

### 5. Messages

`messages` stores conversation messages, including human and AI messages.

This supports conversation flow and LangGraph message-state handling.

### 6. Conversation Summary

`conversation_summary` stores a compact summary of relevant previous conversation context.

It is represented as a string and can be used when the full message history should not be passed directly to downstream processing.

## State Flow

The state is progressively populated as the graph executes:

```text
User Input
    ↓
normalized_input
    ↓
intent_decision
    ↓
documents
    ↓
retrieved_context
    ↓
Response
```

`messages` and `conversation_summary` provide conversation context alongside this flow.

## Design Principle

The state acts as the shared contract between LangGraph nodes.

Each node should read the state fields it needs and write its defined outputs back into the state. The internal implementation of a node remains independent from other nodes as long as it follows the agreed state and schema contracts.

Detailed field-level schemas should be maintained in separate schema documents rather than making this overview document overly detailed.
