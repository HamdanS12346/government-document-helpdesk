# Observability Plan

## Purpose

This document defines the plan for adding Langfuse observability to the Government Document Helpdesk workflow.

The immediate goal is to make one chat request traceable from the FastAPI `/chat` request boundary through the current LangGraph path:

```text
user query
  -> normalized input
  -> intent decision
  -> routed node
  -> retriever, for document_info
  -> context builder, for document_info
```

`general_chat`, `ambiguous` clarification handling, response generation, and memory are not fully implemented yet. They should still be represented in this plan so their future traces use the same structure instead of adding a separate observability style later.

## Current Architecture Snapshot

The current backend flow is:

```text
FastAPI /chat
  -> InputRequest
  -> Input Processor
  -> NormalizedInput
  -> LangGraph
  -> Intent Classifier
  -> IntentDecision
  -> route_after_intent
```

Current routing state:

```text
document_info
  -> retriever
  -> context_builder
  -> END

general_chat
  -> general_chat_placeholder
  -> END

ambiguous
  -> clarification_placeholder
  -> END
```

The current trace should show placeholder nodes when they are called, but the TODO section below should describe the final tracing requirements for the real Response Node and Clarification Node.

## Langfuse Setup

The local `.env` already contains:

```text
LANGFUSE_SECRET_KEY
LANGFUSE_PUBLIC_KEY
LANGFUSE_BASE_URL
```

Langfuse is not installed yet. Adding observability will require:

```text
requirements.txt
  -> add langfuse
```

Configuration should be loaded through the application config layer, not by reading `.env` directly inside every node.

Recommended settings:

```text
LANGFUSE_SECRET_KEY
LANGFUSE_PUBLIC_KEY
LANGFUSE_BASE_URL
LANGFUSE_ENABLED=true
LANGFUSE_CAPTURE_TEXT=false
```

`LANGFUSE_CAPTURE_TEXT` should default to `false` because user queries, extracted OCR text, PDF text, retrieved context, prompts, and model outputs can contain sensitive personal or government-document information.

## Trace Boundary

Create one Langfuse root trace for one `/chat` request.

Root trace name:

```text
chat_request
```

Root trace input should be minimized. Do not store raw uploads or full extracted document text.

Safe root metadata:

```text
{
  "route": "/chat",
  "environment": "development",
  "has_message": true,
  "attachment_count": 2,
  "attachment_media_types": ["image/png", "application/pdf"],
  "graph": "intent_retriever",
  "status": "success | clarification_required | general_chat_placeholder | retrieval_failed | system_error"
}
```

The root trace should contain child observations for each node or major internal step. Tracing failures must not fail the chat request.

For the current clarification milestone, the root `chat_request` output uses
the same public workflow status vocabulary returned by `/chat`. When the graph
produces a clarification question, the root output records:

```text
status = "clarification_required"
intent_type = "ambiguous"
clarification_round_count
assistant_message_length
```

The full clarification question is not captured by default. If
`LANGFUSE_CAPTURE_TEXT=true`, only a bounded redacted
`assistant_message_preview` may be included through the shared safe text preview
helper.

## Current Trace Shape

The target trace for a `document_info` request should look like this:

```text
chat_request
  -> input_processor
       input: raw request metadata only
       output: normalized input metadata

  -> intent_classifier
       input: normalized input metadata
       output: intent decision metadata

  -> route_after_intent
       input: intent_decision.intent_type
       output: selected node name

  -> retriever
       input: normalized_input metadata, intent_decision metadata
       output: final document metadata

       -> query_rewrite
            input: retrieval input metadata
            output: rewritten query metadata

       -> metadata_filter
            input: rewritten query metadata
            output: filter decision metadata

       -> dense_retrieval
            input: rewritten query, top_k, metadata filter
            output: dense result IDs and scores

       -> lexical_retrieval
            input: rewritten query, top_k, metadata filter
            output: lexical result IDs and scores

       -> reciprocal_rank_fusion
            input: dense result IDs, lexical result IDs
            output: fused result IDs and RRF scores

       -> reranking
            input: fused result IDs
            output: final ranked document IDs, scores, fallback status

  -> context_builder
       input: final document metadata
       output: retrieved_context metadata
```

For `general_chat` right now:

```text
chat_request
  -> input_processor
  -> intent_classifier
  -> route_after_intent
  -> general_chat_placeholder
```

For `ambiguous` right now:

```text
chat_request
  -> input_processor
  -> intent_classifier
  -> route_after_intent
  -> clarification_placeholder
```

## What Each Current Step Should Capture

### Input Processor

Capture node input and output at the contract boundary.

Input metadata:

```text
has_user_query
user_query_length
attachment_count
image_count
pdf_count
media_types
```

Output metadata:

```text
success
warning_count
normalized_user_query_length
combined_text_length
image_content_count
pdf_content_count
image_preview_lengths
pdf_preview_lengths
attachment_statuses
```

Do not capture:

```text
raw uploaded files
raw OCR text
raw PDF text
full combined_text
full previews by default
government IDs
addresses
phone numbers
emails
dates of birth
```

### Intent Classifier

Capture the node input and output that explain the decision.

Input metadata:

```text
normalized_user_query_length
combined_text_length
image_content_count
pdf_content_count
messages_count
has_conversation_summary
conversation_summary_length
```

Output metadata:

```text
intent_type
confidence_score
classification_query_length
```

If text capture is explicitly enabled for local debugging, store redacted text only.

### Routing

Capture the route selected after intent classification.

Input metadata:

```text
intent_type
confidence_score
```

Output metadata:

```text
selected_node
selected_path
```

Expected current route mapping:

```text
document_info -> retriever
general_chat -> general_chat_placeholder
ambiguous -> clarification_placeholder
```

### Retriever Node

Capture the Retriever as one parent observation with child observations for its internal pipeline.

Retriever input metadata:

```text
has_normalized_input
normalized_user_query_length
combined_text_length
intent_type
messages_count
has_conversation_summary
conversation_summary_length
```

Retriever output metadata:

```text
final_document_count
final_document_ids
final_document_names
final_scores
fallback_applied
```

Do not capture full document text in Langfuse.

### Query Rewrite

Capture how the retrieval query was optimized.

Input metadata:

```text
retrieval_input_length
used_combined_text
messages_count
has_conversation_summary
attachment_preview_count
```

Output metadata:

```text
rewritten_query_length
query_changed
```

Optional local-only debug text, behind redaction and `LANGFUSE_CAPTURE_TEXT=true`:

```text
redacted_retrieval_input
redacted_rewritten_query
```

### Metadata Filter

Capture metadata extraction/filtering decisions.

Output metadata:

```text
is_confident
category
document_name
chroma_filter_applied
bm25_filter_applied
```

### Dense Retrieval

This is the first retrieved list.

Capture:

```text
method = "dense_vector"
top_k
filter_applied
result_count
result_ids
document_ids
document_names
scores
latency_ms
```

### Lexical Retrieval

This is the second retrieved list.

Capture:

```text
method = "bm25_lexical"
top_k
filter_applied
result_count
result_ids
document_ids
document_names
scores
latency_ms
```

### Reciprocal Rank Fusion

Capture RRF across dense and lexical lists.

Input metadata:

```text
dense_result_count
lexical_result_count
rrf_k
rrf_top_n
```

Output metadata:

```text
fused_result_count
fused_result_ids
fused_document_ids
fused_scores
```

### Reranking

Capture final reranking.

Input metadata:

```text
reranker_provider
input_document_count
top_n
```

Output metadata:

```text
final_document_count
final_document_ids
final_document_names
final_scores
fallback_applied
```

If Cohere is unavailable and RRF fallback is used, the trace should make that obvious.

### Context Builder

Capture input and output at the Context Builder node.

Input metadata:

```text
document_count
document_ids
document_names
scores
```

Output metadata:

```text
total_documents_retrieved
documents_used
source_count
source_chunk_ids
source_document_names
has_relevant_documents
truncated
fallback_applied
formatted_context_length
```

Do not capture full `formatted_context` by default.

## Privacy Rules

By default, Langfuse should receive metadata, not sensitive content.

Never capture by default:

```text
raw user-uploaded PDFs
raw user-uploaded images
raw OCR output
raw PDF extraction text
full normalized_input.combined_text
full retrieved document text
full retrieved_context.formatted_context
full prompts
full model responses
government identifiers
phone numbers
addresses
emails
dates of birth
```

Prefer:

```text
counts
lengths
booleans
route names
node names
status values
safe reason codes
document IDs
chunk IDs
source URLs only when already public/official
scores
latency
token usage
```

If payload capture is later needed for local debugging, add a redaction helper first and gate it behind explicit config.

## Implementation Plan

### Phase 1: Install And Configure Langfuse

Files likely affected:

```text
requirements.txt
app/config/
.env.example
README.md
```

Work:

```text
add langfuse dependency
add Langfuse settings
document LANGFUSE_* env vars in .env.example
document local setup in README.md
```

### Phase 2: Add Observability Helper Layer

Files likely affected:

```text
app/observability/
tests/
```

Work:

```text
create Langfuse client factory
create no-op fallback when disabled or misconfigured
create safe metadata helpers
create span/observation helpers
create redaction/minimization helpers
```

The rest of the app should depend on the helper layer, not direct Langfuse client construction everywhere.

### Phase 3: Add Root Trace At API Boundary

Files likely affected:

```text
app/api/routes.py
tests/api/
```

Work:

```text
start chat_request trace inside /chat
attach request metadata
pass trace context into input processing and graph invocation
set final trace status
record API-level exceptions safely
```

### Phase 4: Instrument Current Nodes

Files likely affected:

```text
app/input_processing/
app/intent/
app/graph/graph.py
app/graph/routing.py
app/rag/node.py
app/rag/hybrid_fusion.py
app/rag/context_builder/node.py
app/rag/context_builder/builder.py
tests/input-processor/
tests/intent-classifier/
tests/rag/
tests/context-builder/
```

Work:

```text
trace input_processor inputs and outputs
trace intent_classifier inputs and outputs
trace route_after_intent selected node
trace retriever parent span
trace query rewrite
trace metadata filter
trace dense retrieval list
trace lexical retrieval list
trace RRF
trace reranking
trace final documents
trace context builder input and output
```

### Phase 5: Add Tests

Testing should verify:

```text
observability disabled does not change behavior
Langfuse failures do not fail chat requests
safe metadata excludes raw file bytes
safe metadata excludes full extracted text
document_info path emits expected observation names
general_chat placeholder emits selected route
ambiguous placeholder emits selected route
retriever emits dense and lexical result counts separately
context builder emits safe output metadata
```

## TODO: Response Node Observability

When the Response Node is implemented, add it to the same root trace.

Expected trace shape:

```text
chat_request
  -> response_node
       input: normalized input metadata, intent decision, retrieved context metadata, memory metadata
       output: response metadata

       -> response_prompt_build
       -> response_model_call
       -> citation_validation
       -> response_formatting
```

Response Node input metadata:

```text
intent_type
normalized_user_query_length
has_retrieved_context
retrieved_context_length
source_count
documents_used
messages_count
has_conversation_summary
```

Response Node output metadata:

```text
response_status
answer_length
citation_count
source_count_used
model_provider
model_name
input_tokens
output_tokens
total_tokens
latency_ms
fallback_applied
```

For `document_info`, the trace should show whether the answer was grounded in `retrieved_context.sources`.

For `general_chat`, the trace should show that retrieval was skipped and the Response Node generated from the user query plus conversation context.

Do not capture full prompts or full final answers by default.

## Clarification Node Observability

The Clarification Node traces the current milestone behavior: the graph writes a clarification `AIMessage` and returns a completed graph result. Durable interrupt/resume and cross-request memory linkage remain part of the later memory/checkpoint work.

Expected trace shape:

```text
chat_request
  -> clarification
       input: intent decision metadata and conversation metadata
       output: clarification question metadata
       status: clarification_required
```

Clarification input metadata:

```text
intent_type
confidence_score
classification_query_length
messages_count
has_conversation_summary
conversation_summary_length
clarification_round_count
max_clarification_rounds
```

Clarification output metadata:

```text
clarification_required
reason_code
missing_dimension_count
missing_dimensions
question_length
next_node_after_user_reply = "intent_classifier"
```

Do not capture full messages, full summaries, full classification queries, or full clarification questions by default. If `LANGFUSE_CAPTURE_TEXT=true`, only capture bounded redacted previews through the shared safe text preview helper.

When the user replies in a later request, the memory/checkpoint branch should link or reload the conversation state so the next trace makes it clear that classification runs again after clarification.

The root `chat_request` trace should mirror this outcome with
`status: "clarification_required"` and safe metadata only. It must not store the
full clarification question unless text capture is explicitly enabled, and even
then only as a redacted bounded preview.

## TODO: Memory Observability

Memory is not complete yet. When implemented, trace memory reads and writes without storing private conversation content.

Expected observations:

```text
memory_read
memory_write
conversation_summary_update
message_window_build
```

Memory metadata:

```text
session_id_hash
messages_available
messages_used
message_window_size
has_conversation_summary
conversation_summary_length
summary_updated
summary_input_message_count
summary_output_length
```

Do not store full message history or raw summaries in Langfuse by default.

## TODO: Guardrails And Evaluation Observability

When guardrails are added, trace:

```text
guardrail_check_name
guardrail_category
result = pass | warn | block
safe_reason_code
action_taken
latency_ms
```

When evaluation is added, attach:

```text
evaluation_case_id
metric_name
score
pass_fail
expected_route
actual_route
retrieval_expected_doc_ids
retrieval_actual_doc_ids
```

Evaluation payloads must follow the same privacy rules as production traces.

## Expected End State

When observability is fully implemented, opening a Langfuse trace for a document-info request should let a developer see:

```text
what the user sent, as safe metadata
how it was normalized
which intent was chosen
which route was selected
which node ran
how the retrieval query was optimized
which dense results were returned
which lexical results were returned
how RRF fused them
how reranking changed the final order
which documents were passed forward
how context was built
which response node path ran
which citations/sources were used
what failed, if anything
how long each step took
```

The trace should describe node inputs and outputs clearly while keeping sensitive document content out of Langfuse unless explicit, redacted, local debugging capture is enabled.
