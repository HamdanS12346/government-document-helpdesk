# Intent Classifier to Retriever Integration

## Purpose

This document captures the relevant integration details for connecting the
existing Input Processor and Intent Classifier graph slice to the Retriever.

The goal for this phase is not to finish the whole helpdesk workflow.

The current integrated slice lets a frontend chat request flow through:

```text
Frontend chat
  -> FastAPI /chat
  -> Input Processor
  -> normalized_input
  -> Intent Classifier
  -> intent_decision
  -> routing
  -> Retriever, only for document_info
  -> documents
  -> Context Builder
  -> retrieved_context
```

For now, `general_chat` and `ambiguous` are placeholder branches because the
Response Node and Clarification Node are not implemented yet.

The terminal debugging output for the connected path should show:

```text
Normalized input
Intent decision
Documents
Retrieved context
```

The API response can remain focused on the current input-processing payload
until the Response Node is available.

## Current Implemented State

The current graph slice is defined in `app/graph/graph.py`.

It builds a graph named by function, not by a class:

```python
build_input_intent_graph(classifier)
```

Current behavior:

```text
START
  -> intent_classifier
  -> END
```

Both graph bridges assume input processing has already completed.

The preserved input-intent bridge function:

```python
invoke_input_intent_graph(result, classifier, messages=None, conversation_summary=None)
```

does the following:

1. Converts a successful `InputProcessingResult` into graph state.
2. Requires `state["normalized_input"]`.
3. Optionally adds `messages`.
4. Optionally adds `conversation_summary`.
5. Invokes the graph.
6. Returns state containing `normalized_input` and `intent_decision`.

The active FastAPI route now does this after successful input processing:

```text
process_input(request)
  -> print normalized_input
  -> invoke_intent_retriever_graph(...)
  -> print intent_decision
  -> print documents, when present
  -> print retrieved_context, when present
```

The document-info branch now stops after `retrieved_context`; Response Node
generation is still later work.

## Existing State Contract

Shared graph state is defined in `app/graph/state.py`.

Relevant fields:

```python
class GraphState(TypedDict, total=False):
    normalized_input: NotRequired[NormalizedInput]
    intent_decision: NotRequired[IntentDecision]
    documents: NotRequired[list[Any]]
    retrieved_context: NotRequired[Any]
    messages: NotRequired[list[Any]]
    conversation_summary: NotRequired[str]
```

For this phase, only these fields are required:

```text
normalized_input
intent_decision
documents
retrieved_context
messages, optional and usually empty for now
conversation_summary, optional and usually absent for now
```

No state schema change is required to store retriever or context-builder output.

`documents` already exists as:

```python
documents: NotRequired[list[Any]]
```

The retrieval contract describes the intended concrete item type as:

```text
List[RetrievedDocument]
```

The Context Builder consumes `documents` and writes:

```python
{"retrieved_context": retrieved_context}
```

where `retrieved_context` follows the `RetrievedContext` response contract.

## Intent Decision Contract

The Intent Classifier writes:

```python
state["intent_decision"]
```

The model is:

```python
IntentDecision(
    query: str,
    intent_type: IntentType,
    confidence_score: float,
)
```

Supported intent values:

```text
document_info
general_chat
ambiguous
```

The important integration detail is that `intent_decision.query` is not the
retrieval query for this phase.

`intent_decision.query` is the classifier query.

It is intentionally built from:

```text
normalized_input.user_query
attachment previews
conversation context, when available
```

It does not include full extracted attachment text.

That is correct for classification because the classifier only needs enough
context to decide where the workflow should go.

## Normalized Input Contract

The Input Processor writes:

```python
state["normalized_input"]
```

The model is:

```python
NormalizedInput(
    user_query: str,
    image_content: list[ImageContent],
    pdf_content: list[PDFContent],
    combined_text: str,
)
```

`combined_text` is the key field for Retriever integration.

It contains the fuller normalized representation:

```text
<USER_QUERY>
...

<IMAGE_CONTENT>
...

<PDF_CONTENT>
...
```

The Retriever should receive `normalized_input.combined_text` as the current
request text to optimize for retrieval.

This avoids accidentally retrieving from the classifier's preview-only query.

## Retriever Contract

The Retriever Node is currently implemented in `app/rag/node.py`.

Public graph adapter:

```python
retriever_node(state)
```

Default pipeline:

```python
get_default_retriever_pipeline()
```

Pipeline method:

```python
RetrieverPipeline.execute(state)
```

Current pipeline stages:

```text
1. Parse normalized_input
2. Query rewriting
3. Metadata extraction
4. Dense vector search through Chroma/vector adapter
5. BM25 lexical search
6. Reciprocal Rank Fusion
7. Cohere reranking, with fallback
8. Return {"documents": final_documents}
```

The node writes:

```python
{"documents": final_documents}
```

The intended document item shape is:

```python
RetrievedDocument(
    id: str,
    text_content: str,
    metadata: ChunkMetadata,
    score: Optional[float],
)
```

## Important Query Source Change

The current `RetrieverPipeline.execute` implementation reads:

```python
user_query = norm_input.user_query
```

It then separately builds attachment previews and passes those previews to the
query rewriter.

For this integration, the retriever should instead treat this as its source
query:

```python
retrieval_input = norm_input.combined_text
```

Then the rewriter should optimize that text with:

```text
combined_text
messages
conversation_summary
```

This is intentional because:

1. The classifier query is preview-oriented.
2. The retriever needs the fuller normalized user request.
3. Attached document/image extracted text may be relevant evidence for query
   optimization.
4. Downstream retrieval quality should not depend on the shortened classifier
   prompt.

Recommended implementation detail:

```python
retrieval_input = norm_input.combined_text.strip() or norm_input.user_query
```

Then pass `retrieval_input` to the query rewriter as the current query.

Because `combined_text` already includes attachment content, avoid duplicating
the same attachment content again unless the rewriter still needs separate
preview fields for compatibility.

If the existing `QueryRewriter.rewrite()` signature is kept unchanged, call it
like this:

```python
rewritten_query = self.query_rewriter.rewrite(
    user_query=retrieval_input,
    messages=messages,
    conversation_summary=summary,
    attachment_previews=[],
)
```

If separate attachment previews are still passed, tests should confirm that the
same attachment text is not injected twice.

## Conversation Context Status

Both the Intent Classifier and Retriever are designed to receive conversation
context:

```text
messages
conversation_summary
```

In the final workflow, these fields should come from the Memory and Response
parts of the system.

That is later work.

For this phase:

```text
messages can default to []
conversation_summary can default to None or be absent
```

The graph and nodes should keep accepting both fields so the future memory
integration does not require a redesign.

Do not block Retriever integration on memory.

Do not invent response-generated summaries in this phase.

## Routing Requirement

Routing happens immediately after the Intent Classifier writes
`state["intent_decision"]`.

The router should inspect:

```python
state["intent_decision"].intent_type
```

The route table for this phase:

| Intent | Route | Status |
| --- | --- | --- |
| `document_info` | Retriever Node -> Context Builder Node | Implemented |
| `general_chat` | Response placeholder | Placeholder |
| `ambiguous` | Clarification placeholder | Placeholder |

Expected behavior:

```text
document_info
  -> retriever
  -> context_builder
  -> END for now

general_chat
  -> general_chat_placeholder
  -> END for now

ambiguous
  -> clarification_placeholder
  -> END for now
```

The placeholders should be small graph nodes that return a minimal state update
or no update.

They should not call LLMs.

They should not pretend to generate a real assistant response.

They exist only so the graph shape is ready for future Response and
Clarification nodes.

## Proposed Graph Shape

For this phase, add a new graph builder rather than silently changing the
meaning of the existing one if tests or callers still depend on the old graph
name.

Recommended function:

```python
build_intent_retriever_graph(
    classifier,
    retriever=retriever_node,
    context_builder=context_builder_node,
)
```

Recommended bridge:

```python
invoke_intent_retriever_graph(
    result,
    classifier,
    retriever=retriever_node,
    context_builder=context_builder_node,
    messages=None,
    conversation_summary=None,
)
```

The graph shape:

```text
START
  -> intent_classifier
  -> route_after_intent

route_after_intent:
  document_info -> retriever
  general_chat  -> general_chat_placeholder
  ambiguous     -> clarification_placeholder

retriever -> context_builder -> END
general_chat_placeholder -> END
clarification_placeholder -> END
```

The old `build_input_intent_graph()` can remain available if needed for the
current tests.

Once the new graph is stable, callers can migrate to the new bridge.

## Router Helper

`app/graph/routing.py` is currently empty.

This is the right place for routing logic.

Recommended helper:

```python
def route_after_intent(state: State) -> str:
    decision = state.get("intent_decision")
    if decision is None:
        raise ValueError("intent_decision is required for intent routing")

    intent_type = decision.intent_type

    if intent_type == IntentType.DOCUMENT_INFO:
        return "retriever"
    if intent_type == IntentType.GENERAL_CHAT:
        return "general_chat_placeholder"
    if intent_type == IntentType.AMBIGUOUS:
        return "clarification_placeholder"

    raise ValueError(f"unsupported intent_type: {intent_type}")
```

Use constants for node names in `app/graph/graph.py` to avoid string drift.

Recommended constants:

```python
INTENT_CLASSIFIER_NODE = "intent_classifier"
RETRIEVER_NODE = "retriever"
CONTEXT_BUILDER_NODE = "context_builder"
GENERAL_CHAT_PLACEHOLDER_NODE = "general_chat_placeholder"
CLARIFICATION_PLACEHOLDER_NODE = "clarification_placeholder"
```

## Placeholder Nodes

Placeholders should be explicit and boring.

Recommended shape:

```python
def general_chat_placeholder(state: State) -> dict[str, Any]:
    return {}


def clarification_placeholder(state: State) -> dict[str, Any]:
    return {}
```

If terminal debugging is useful, avoid putting print statements inside the
placeholder nodes.

Keep API/debug logging at the route boundary.

The future Response and Clarification nodes can replace these placeholders
without changing the route names.

## FastAPI Integration

The current `/chat` route imports:

```python
invoke_input_intent_graph
```

For this phase, switch the route to the new bridge:

```python
invoke_intent_retriever_graph
```

After invoking the graph, print:

```text
Normalized input:
<normalized_input json>

Intent decision:
<intent_decision json>

Documents:
<documents json or jsonable dump>

Retrieved context:
<retrieved_context json or jsonable dump>
```

Only print `Documents` and `Retrieved context` when those keys exist.

For `general_chat` and `ambiguous`, the graph should end without `documents` or
`retrieved_context`.

Expected terminal behavior:

```text
document_info request:
  prints normalized_input
  prints intent_decision
  prints documents
  prints retrieved_context

general_chat request:
  prints normalized_input
  prints intent_decision
  does not print documents, or prints an empty placeholder clearly

ambiguous request:
  prints normalized_input
  prints intent_decision
  does not print documents, or prints an empty placeholder clearly
```

The route should not expose raw retrieved documents to the frontend yet unless
that is intentionally added to the API contract.

For now, terminal visibility is enough.

## Testing Plan

Do not make live calls in automated tests.

That means tests should not depend on:

```text
OpenAI intent calls
OpenAI embedding calls
Cohere reranking calls
Chroma Cloud network calls
```

Use fake classifiers and fake retriever nodes.

Recommended graph tests:

1. `document_info` routes to Retriever and writes `documents`.
2. `document_info` routes from Retriever to Context Builder and writes
   `retrieved_context`.
3. `general_chat` routes to the general chat placeholder and does not write
   `documents` or `retrieved_context`.
4. `ambiguous` routes to the clarification placeholder and does not write
   `documents` or `retrieved_context`.
5. Missing `normalized_input` still fails before classification.
6. Missing `intent_decision` in routing raises a clear error.
7. Existing conversation fields are preserved in graph state.
8. Retriever receives the same `normalized_input` object that came from input
   processing.
9. Context Builder receives the same state, including `documents`, from the
   Retriever branch.
10. Retriever uses `normalized_input.combined_text`, not
   `intent_decision.query`, as its retrieval input.

The eighth test may be easiest at the RetrieverPipeline level with a fake query
rewriter.

The fake query rewriter can record the `user_query` argument and assert that it
equals:

```python
normalized_input.combined_text
```

not:

```python
intent_decision.query
```

Recommended API tests:

1. Patch input processing to return a successful `InputProcessingResult`.
2. Patch the graph bridge to return `normalized_input`, `intent_decision`,
   fake `documents`, and fake `retrieved_context`.
3. Assert `/chat` still returns the current public response shape.
4. Assert graph bridge errors return the existing classification error payload.

Keep real Chroma/manual verification separate from unit tests.

## Manual Verification

When live services are intentionally configured, a manual frontend run should
look like this:

```text
Frontend sends message/files
FastAPI receives multipart request
Input Processor creates normalized_input
Intent Classifier creates intent_decision
Router sends document_info to Retriever
Retriever queries Chroma/vector + BM25 path
Retriever writes documents
Context Builder writes retrieved_context
FastAPI terminal prints normalized_input, intent_decision, documents, retrieved_context
```

Manual document-info query example:

```text
What documents are required for PAN application?
```

Expected route:

```text
document_info -> retriever -> context_builder -> END
```

Manual general-chat query example:

```text
Hello, how are you?
```

Expected route:

```text
general_chat -> general_chat_placeholder -> END
```

Manual ambiguous query example:

```text
Can you check this?
```

Expected route:

```text
ambiguous -> clarification_placeholder -> END
```

## Implementation Sequence

Recommended order:

1. Add node-name constants in `app/graph/graph.py`.
2. Add `route_after_intent()` in `app/graph/routing.py`.
3. Add placeholder node functions.
4. Add `build_intent_retriever_graph()`.
5. Add `invoke_intent_retriever_graph()`.
6. Keep `build_input_intent_graph()` unless all callers are migrated.
7. Update the RetrieverPipeline to rewrite from `combined_text`.
8. Update `/chat` to invoke the new graph bridge.
9. Print `documents` in the terminal when present.
10. Wire `retriever -> context_builder -> END`.
11. Print `retrieved_context` in the terminal when present.
12. Add routing tests with fake classifier, fake retriever, and fake context
    builder.
13. Add retriever query-source test with a fake query rewriter.
14. Run focused tests first, then run `pytest`.

## Boundary Rules

Do not change `IntentDecision` fields for this integration.

Do not change `NormalizedInput` fields for this integration.

Do not change `GraphState` unless a concrete new state field is required.

Do not put retrieval business logic in routing helpers.

Do not put response generation in the Retriever.

Do not implement clarification behavior in this phase.

Do not make tests depend on live external providers.

Keep the graph responsible for orchestration only.

Keep node-specific behavior inside the owning package:

```text
app/intent/
app/rag/
app/response/
app/memory/
```

## Later Work

After the Response Node exists:

```text
general_chat -> response
document_info -> retriever -> context_builder -> response
```

After the Clarification Node exists:

```text
ambiguous -> clarification -> interrupt -> user clarification -> intent classifier
```

After Memory exists:

```text
messages
conversation_summary
```

should be populated from real conversation state rather than passed as empty
or omitted values.

At that point, the Retriever can use real multi-turn context for query
optimization, and the Intent Classifier can use the same conversation window
for better routing decisions.
