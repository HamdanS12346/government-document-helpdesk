# Token Usage Tracking Logic in Evaluations

This document details the architecture, interception mechanics, aggregation formulas, and Langfuse telemetry used to measure and record token consumption across the connected graph evaluations.

---

## 1. Overview & Architecture

To evaluate the operational cost and context efficiency of the pipeline, token tracking operates across two distinct tiers:

1. **Pipeline Tier (Inside LangGraph)**: Measures tokens consumed by the actual RAG graph nodes during query normalization, intent detection, query rewriting, metadata extraction, and response generation.
2. **Evaluator Tier (Inside LLM Judges)**: Measures tokens consumed by the 6 LLM-as-a-judge evaluators (*Correctness, Faithfulness, Relevance, Completeness, Citation, Safety*).

```text
                        Incoming Evaluation Case (Query)
                                      │
                                      ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ TIER 1: Connected Graph Pipeline (evaluation/graph/adapter.py)            │
│                                                                           │
│  [Intent Stage]       OpenAIIntentClassifier.classify()                   │
│       │               Input: Query + Attachment previews                  │
│       │               Output: IntentDecision JSON                         │
│       ▼                                                                   │
│  [Retrieval Stage]    QueryRewriter + MetadataExtractor                   │
│       │               Input: Query + Conversation history                 │
│       │               Output: Rewritten search query + metadata filter    │
│       ▼                                                                   │
│  [Response Stage]     ResponseGenerator.generate()                        │
│                       Input: System prompt + Retrieved Context + Query    │
│                       Output: Grounded citizen-facing answer              │
└─────────────────────────────────────┬─────────────────────────────────────┘
                                      │
                                      ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ TIER 2: Evaluation Judges (evaluation/runners/run_e2e_demo.py)             │
│                                                                           │
│  6 LLM Judges: Correctness, Faithfulness, Relevance,                      │
│                Completeness, Citation, Safety                             │
│  Input:  Evaluation criteria + Context + Answer + Ground Truth Key Points  │
│  Output: Structured JSON scores & reasoning                               │
└─────────────────────────────────────┬─────────────────────────────────────┘
                                      │
                                      ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ TIER 3: Langfuse Reporting                                                │
│                                                                           │
│  - Trace Output Payload: Hierarchical token_usage dictionary              │
│  - Trace Numeric Scores: tokens_input, tokens_output, cost_usd, etc.       │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Token Interception Mechanics

Token counting is implemented using LangChain's callback mechanism (`get_openai_callback`), which intercepts requests and responses at the HTTP/SDK client level.

### How `get_openai_callback` Functions
1. **Context Registration**: When entering `with get_openai_callback() as cb:`, an `OpenAICallbackHandler` is registered on the active thread callback manager.
2. **Metadata Extraction**: When an OpenAI chat completion model (`ChatOpenAI`) completes an invocation, the raw API response headers and body containing `usage` are inspected:
   - `prompt_tokens` $\rightarrow$ Counted as **Input Tokens**.
   - `completion_tokens` $\rightarrow$ Counted as **Output Tokens**.
   - `total_tokens` $\rightarrow$ Sum of input and output.
   - `total_cost` $\rightarrow$ Estimated dollar cost computed against the standard model pricing table (e.g. `gpt-4o-mini`).

---

## 3. Tier 1: Stage-by-Stage Pipeline Interception

In [evaluation/graph/adapter.py](file:///c:/Users/ERICCARLOSFALEIRO/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/GitHub/government-document-helpdesk/evaluation/graph/adapter.py), node functions are wrapped with individual token trackers before being passed into `invoke_full_graph`:

```python
# Stage token container
stage_tokens = {
    "intent": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0.0},
    "retrieval": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0.0},
    "response": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0.0},
    "clarification": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0.0},
}
```

### Stage Interceptor Wrappers

1. **Intent Stage**:
   ```python
   class TrackedClassifier:
       def classify(self, q: str, **kwargs):
           with get_openai_callback() as cb:
               res = self.inner.classify(q, **kwargs)
           stage_tokens["intent"]["input_tokens"] += cb.prompt_tokens
           stage_tokens["intent"]["output_tokens"] += cb.completion_tokens
           stage_tokens["intent"]["total_tokens"] += cb.total_tokens
           stage_tokens["intent"]["cost_usd"] += cb.total_cost
           return res
   ```

2. **Retrieval Stage**:
   ```python
   def tracked_retriever(state: State) -> dict[str, Any]:
       with get_openai_callback() as cb:
           res = self.retriever(state)
       stage_tokens["retrieval"]["input_tokens"] += cb.prompt_tokens
       stage_tokens["retrieval"]["output_tokens"] += cb.completion_tokens
       stage_tokens["retrieval"]["total_tokens"] += cb.total_tokens
       stage_tokens["retrieval"]["cost_usd"] += cb.total_cost
       return res
   ```
   *Captures LLM calls made by `QueryRewriter` and `MetadataExtractor` during retrieval query optimization.*

3. **Response Stage**:
   ```python
   def tracked_responder(state: State) -> dict[str, Any]:
       with get_openai_callback() as cb:
           res = self.responder(state)
       stage_tokens["response"]["input_tokens"] += cb.prompt_tokens
       stage_tokens["response"]["output_tokens"] += cb.completion_tokens
       stage_tokens["response"]["total_tokens"] += cb.total_tokens
       stage_tokens["response"]["cost_usd"] += cb.total_cost
       return res
   ```
   *Measures the large context prompt (including all retrieved chunks) and the final synthesized citizen answer.*

4. **Overall Pipeline Wrap**:
   The entire `invoke_full_graph` execution is also wrapped with an overarching callback:
   ```python
   with get_openai_callback() as pipeline_cb:
       output_state = invoke_full_graph(...)

   token_metrics = {
       "input_tokens": pipeline_cb.prompt_tokens,
       "output_tokens": pipeline_cb.completion_tokens,
       "total_tokens": pipeline_cb.total_tokens,
       "cost_usd": pipeline_cb.total_cost,
       "stages": stage_tokens,
   }
   ```

---

## 4. Tier 2: Evaluator Token Interception

In [evaluation/runners/run_e2e_demo.py](file:///c:/Users/ERICCARLOSFALEIRO/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/GitHub/government-document-helpdesk/evaluation/runners/run_e2e_demo.py), the 6 LLM judge evaluations are wrapped together:

```python
with get_openai_callback() as eval_cb:
    eval_res = evaluate_response_case(
        case=eval_case_data,
        generated_response=graph_output.response or "",
    )

eval_tokens = {
    "input_tokens": eval_cb.prompt_tokens,
    "output_tokens": eval_cb.completion_tokens,
    "total_tokens": eval_cb.total_tokens,
    "cost_usd": eval_cb.total_cost,
}
```

---

## 5. Aggregation Formulas

For every test case turn, total token consumption and costs are calculated by aggregating both tiers:

$$\text{Total Input Tokens} = \text{Pipeline Input Tokens} + \text{Evaluator Input Tokens}$$

$$\text{Total Output Tokens} = \text{Pipeline Output Tokens} + \text{Evaluator Output Tokens}$$

$$\text{Total Tokens} = \text{Total Input Tokens} + \text{Total Output Tokens}$$

$$\text{Total Cost (USD)} = \text{Pipeline Cost} + \text{Evaluator Cost}$$

### Concrete Example from Record 16 (`RESP-016`)

| Category | Input Tokens | Output Tokens | Total Tokens | Cost (USD) |
| :--- | :---: | :---: | :---: | :---: |
| **Pipeline (Graph)** | 3,901 | 401 | 4,302 | $\approx \$0.00064$ |
| **Judges (6 Evaluators)** | 79,796 | 479 | 80,275 | $\approx \$0.01244$ |
| **Total Turn** | **83,697** | **880** | **84,577** | **$\approx \$0.01308$** |

*Notice: In evaluation mode, the 6 LLM judges account for the majority of input tokens because they evaluate extensive reference documentation, rubrics, and the generated answer six separate times.*

---

## 6. Langfuse Ingestion & Telemetry

The aggregated token metrics are recorded into Langfuse (`https://jp.cloud.langfuse.com`) in two ways:

### 1. Numeric Scores (Graphed & Filterable)
Recorded on each trace via `langfuse_client.create_score()`:

- `tokens_total`: Total tokens for the turn.
- `tokens_input`: Total input prompt tokens.
- `tokens_output`: Total output completion tokens.
- `tokens_pipeline_input`: Input tokens consumed by the graph alone.
- `tokens_pipeline_output`: Output tokens generated by the graph alone.
- `tokens_eval_input`: Input tokens consumed by the judge LLMs.
- `tokens_eval_output`: Output tokens generated by the judge LLMs.
- `cost_usd`: Total estimated financial cost for the turn.

### 2. Structured Trace Output Payload
Attached to the root observation payload (`eval_case:<ID>`):

```json
{
  "token_usage": {
    "input_tokens": 83697,
    "output_tokens": 880,
    "total_tokens": 84577,
    "cost_usd": 0.01308,
    "pipeline": {
      "input_tokens": 3901,
      "output_tokens": 401,
      "total_tokens": 4302,
      "cost_usd": 0.00064,
      "stages": {
        "intent": {"input_tokens": 285, "output_tokens": 15, "total_tokens": 300, "cost_usd": 0.00004},
        "retrieval": {"input_tokens": 512, "output_tokens": 42, "total_tokens": 554, "cost_usd": 0.00008},
        "response": {"input_tokens": 3104, "output_tokens": 344, "total_tokens": 3448, "cost_usd": 0.00052},
        "clarification": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0.0}
      }
    },
    "evaluators": {
      "input_tokens": 79796,
      "output_tokens": 479,
      "total_tokens": 80275,
      "cost_usd": 0.01244
    }
  }
}
```

---

## 7. Design Benefits

- **Zero Changes to Graph Routing**: Implemented entirely via evaluation wrappers without modifying `app/graph/routing.py`, `app/graph/graph.py`, or any core state schemas.
- **Stage Isolation**: Pinpoints which node consumes excessive token budgets (e.g. distinguishing between query rewriting prompt sizes vs. response context window load).
- **Cost Transparency**: Provides visibility into evaluation overhead (LLM judges) vs. real production request costs (graph pipeline).
