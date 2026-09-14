# Memory Integration Notes

This document is a forward-integration guide for adding conversation memory to
the Government Document Helpdesk graph. The full Memory, Clarification, and
Response implementations are still future work, so this file should stay focused
on the state contract and integration expectations.

## State Fields

Conversation context is carried through shared graph state with two fields:

```python
messages: list[Any]
conversation_summary: str
```

`messages` should contain the current conversation window, including human
messages and AI responses. `conversation_summary` should contain a compact
summary of older conversation that no longer fits in the active window.

Raw frontend multipart data, uploaded file objects, temporary paths, and
provider-specific memory internals should not be stored in graph state.

## Node Expectations

| Node | Memory Input | Memory Output |
| --- | --- | --- |
| Intent Classifier | Reads `messages` and `conversation_summary` to classify follow-up requests. | None. |
| Clarification Node | Reads conversation context to ask the right clarification question. | Adds clarification interaction to `messages`. |
| Retriever | Reads conversation context to rewrite follow-up retrieval queries. | None. |
| Response Node | Reads conversation context plus `retrieved_context` to answer coherently. | Adds the final AI response to `messages`. |
| Memory Node | Reads updated `messages`; summarizes older turns when needed. | Writes updated `messages` and `conversation_summary`. |

The Input Processor should remain the first boundary for each new frontend
request. Memory should be injected after input processing, before nodes that
need conversation context.

## Intended Flow

```text
Frontend request
  -> Input Processor
  -> load memory into messages + conversation_summary
  -> Intent Classifier
  -> route by intent
      -> document_info: Retriever -> Context Builder -> Response
      -> general_chat: Response
      -> ambiguous: Clarification
  -> append human/AI turn to messages
  -> summarize older messages when needed
  -> persist memory
```

Until Response and Clarification are implemented, memory integration should keep
accepting `messages` and `conversation_summary` without requiring those nodes to
exist.

## Integration Rules

- Keep the state contract stable: use `messages` and `conversation_summary`.
- Store both user messages and assistant responses in conversation history.
- Keep memory persistence outside node business logic unless a dedicated Memory
  node owns it.
- Do not make Intent Classifier, Retriever, Clarification, or Response directly
  responsible for saving memory.
- Keep summaries factual and compact; do not invent user details.
- Do not store secrets, raw private files, or unnecessary extracted attachment
  text in long-term memory.

## Manual Verification

Use these checks when memory is wired into the live graph:

1. Follow-up intent classification:

```text
Turn 1: What documents are required for PAN application?
Turn 2: What about address proof?
```

Expected: Turn 2 has enough conversation context to classify as
`document_info`.

2. Follow-up retrieval:

```text
Turn 1: Tell me about Aadhaar address update.
Turn 2: Which documents are accepted?
```

Expected: Retriever uses memory context to retrieve Aadhaar address-update
documents, not generic document lists.

3. Ambiguous reference:

```text
Turn 1: Upload or discuss a specific document.
Turn 2: What is this about?
```

Expected: With a known prior document/context, classify and answer using that
context. Without prior context or attachment, classify as `ambiguous`.

4. Response continuity:

```text
Turn 1: I am applying for a passport.
Turn 2: Do I need address proof?
```

Expected: Response uses the passport context from memory and appends the AI
answer back into `messages`.

5. Summary handoff:

After enough turns to exceed the active message window, older details should move
into `conversation_summary`, while recent turns remain in `messages`.
