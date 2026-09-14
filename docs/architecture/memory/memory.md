# Memory Integration Notes

This document is a forward-integration guide for adding conversation memory to
the Government Document Helpdesk graph. Clarification can now be displayed
through `/chat`, but durable conversation memory and clarified query
reconstruction are still future work. This file should stay focused on the state
contract and integration expectations.

## State Fields

Conversation context is carried through shared graph state with these fields:

```python
messages: list[Any]
conversation_summary: str
clarification_round_count: int
```

`messages` should contain the current conversation window, including human
messages and AI responses. `conversation_summary` should contain a compact
summary of older conversation that no longer fits in the active window.
`clarification_round_count` should contain the number of consecutive
clarification turns for the active request.

Raw frontend multipart data, uploaded file objects, temporary paths, and
provider-specific memory internals should not be stored in graph state.

## Node Expectations

| Node | Memory Input | Memory Output |
| --- | --- | --- |
| Intent Classifier | Reads `messages` and `conversation_summary` to classify follow-up requests. | None. |
| Clarification Node | Reads `messages`, `conversation_summary`, and `clarification_round_count` to ask the right clarification question. | Adds clarification interaction to `messages` and increments `clarification_round_count`. |
| Retriever | Reads conversation context to rewrite follow-up retrieval queries. | None. |
| Response Node | Reads conversation context plus `retrieved_context` to answer coherently. | Adds the final AI response to `messages`. |
| Memory Node | Reads updated `messages`; summarizes older turns when needed; tracks active clarification context. | Writes updated `messages`, `conversation_summary`, `clarification_round_count`, and active clarification context. |

The Input Processor should remain the first boundary for each new frontend
request. Memory should be injected after input processing, before nodes that
need conversation context.

## Intended Flow

```text
Frontend request
  -> Input Processor
  -> load memory into messages + conversation_summary + clarification_round_count
  -> Intent Classifier
  -> route by intent
      -> document_info: Retriever -> Context Builder -> Response
      -> general_chat: Response
      -> ambiguous: Clarification
  -> append human/AI turn to messages
  -> summarize older messages when needed
  -> persist memory
```

The current `/chat` response includes `conversation_id`, but it is `null` until
the memory branch chooses and wires the production session store.

## Clarification Memory Handoff

When `/chat` returns `status: "clarification_required"`, the graph has already
added the clarification question as an assistant message. The memory branch must
persist enough state for the next user turn to continue the same active request.

Persist:

- `conversation_id`
- `messages`, including the original user request, assistant clarification
  question, and later user clarification answer
- `conversation_summary`
- `clarification_round_count`
- active clarification context needed for deterministic query reconstruction
- approved derived attachment context, if the privacy decision permits it

Do not persist:

- raw uploaded files
- raw multipart file objects
- temporary upload paths
- frontend-only transcript state as authoritative backend memory
- unnecessary sensitive identifiers or unbounded extracted attachment text

The next `/chat` request should follow this sequence:

```text
/chat request
  -> identify conversation_id
  -> memory_read
  -> messages + conversation_summary + clarification_round_count
  -> input processing for current turn
  -> graph invoke
  -> memory_write
  -> /chat response
```

The graph bridge already accepts:

```python
invoke_intent_retriever_graph(
    result,
    classifier,
    messages=loaded_messages,
    conversation_summary=loaded_summary,
    clarification_round_count=loaded_round_count,
)
```

The API boundary should load those values from memory and pass them through its
chat graph invocation handoff before classification.

## Clarified Query Reconstruction

The Clarification Node does not mutate `normalized_input`. It only asks the
question and writes an assistant message plus the updated clarification round
count.

Full clarified retrieval requires a memory-owned reconstruction step before the
second classification/retrieval pass.

Required effective query:

```text
effective query =
original request
+
assistant clarification question
+
user clarification answer
+
relevant multimodal content from the current request context
```

Recommended future helper:

```text
app/memory/clarification_context.py
  -> load active clarification context
  -> merge original request and clarification answer
  -> expose messages/summary/counter to graph
```

Reconstruction must be deterministic and idempotent. Re-running the same user
turn should not repeatedly append the same clarification answer. If memory is
not ready, a follow-up clarification answer may only be classified using its own
text and whatever non-durable context is available; that limitation should be
explicit in PR notes.

## Integration Rules

- Keep the state contract stable: use `messages`, `conversation_summary`, and
  `clarification_round_count`.
- Store both user messages and assistant responses in conversation history.
- Store clarification questions as ordinary assistant messages.
- Reset `clarification_round_count` when the active request resolves to a
  non-ambiguous route.
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

4. Clarification continuation:

```text
Turn 1: How do I apply for this?
Assistant: Which document do you mean, and which state are you applying in?
Turn 2: Birth certificate in Goa.
```

Expected: Memory loads the original request, assistant clarification, user
answer, and round counter before classification. The effective query preserves
the original request and the clarification answer.

5. Response continuity:

```text
Turn 1: I am applying for a passport.
Turn 2: Do I need address proof?
```

Expected: Response uses the passport context from memory and appends the AI
answer back into `messages`.

6. Summary handoff:

After enough turns to exceed the active message window, older details should move
into `conversation_summary`, while recent turns remain in `messages`.
