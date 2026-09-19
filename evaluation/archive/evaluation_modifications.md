# Connected Graph Evaluation Architecture

Now that the entire RAG graph is connected, I would make a few changes to the evaluation architecture, but I would not throw away the datasets or the evaluation criteria we already created.

The biggest change is that the evaluations should now test the actual connected graph, rather than treating each component as completely isolated.

---

## 1. Overall Evaluation Architecture

### Previously
We were thinking:

```text
Input Processor Evaluation
        ↓
Intent Evaluation
        ↓
Retrieval Evaluation
        ↓
Response Evaluation
```

### Now
Now that the graph is connected, the actual evaluation flow should be:

```text
                    Test Case
                       │
                       ▼
                ┌─────────────┐
                │ Input Query │
                └──────┬──────┘
                       ↓
                ┌─────────────┐
                │Input Process│
                └──────┬──────┘
                       │
              Input Evaluation
                       │
                       ↓
                ┌─────────────┐
                │ Intent Node │
                └──────┬──────┘
                       │
               Intent Evaluation
                       │
                       ↓
                ┌─────────────┐
                │  Retriever  │
                └──────┬──────┘
                       │
             Retrieval Evaluation
                       │
                       ↓
                ┌─────────────┐
                │Response Node│
                └──────┬──────┘
                       │
              Response Evaluation
                       │
       ┌───────────────┼────────────────┐
       ↓               ↓                ↓
  Correctness     Faithfulness      Relevance
       ↓               ↓                ↓
  Completeness       Citation         Safety
```

**The key difference:** The evaluation runner should execute the real graph and capture the output of each stage.

---

## 2. Datasets Do Not Need to Be Discarded

You already have:

```text
evaluation/
├── datasets/
│   ├── input_processor/
│   │   └── cases.jsonl
│   ├── intent/
│   │   └── cases.jsonl
│   ├── retrieval/
│   │   └── cases.jsonl
│   └── response/
│       └── cases.jsonl
```

Keep these. They represent the expected/ground-truth behavior against which the actual graph will be evaluated. The response dataset you reviewed especially should remain.

---

## 3. The Biggest Change: Runners

This is where I would make the main architectural change.

Previously, the runners could have independently called different components:
- `run_input_processor.py`
- `run_intent.py`
- `run_retrieval.py`
- `run_response.py`

Now they should be able to interact with the connected graph:

```text
evaluation/runners/
├── run_input_processor.py
├── run_intent.py
├── run_retrieval.py
└── run_response.py
```

The runners should capture the outputs produced by the real graph.

---

## 4. Input Processor Evaluation

### Before
We might test:
```text
Input → Input Processor → Expected Output
```

### Now
Run the actual graph's input-processing stage:
```text
Test Query
    ↓
Actual Input Processor
    ↓
Actual Processed Input
    ↓
Input Evaluator
```

Then compare:
$$\text{Actual Processed Input} \quad \text{vs} \quad \text{Expected Processed Input}$$

### Change Needed
Probably very little to the evaluator itself. The main change is how the runner obtains the actual processed input.

---

## 5. Intent Evaluation

Same idea. The actual graph does:
```text
Input Processor
       ↓
Intent Node
       ↓
Detected Intent
```

The evaluator then checks:
$$\text{Actual Intent} \quad \text{vs} \quad \text{Expected Intent}$$

### Execution Flow:
```text
run_intent.py
      ↓
Execute actual graph/node
      ↓
Capture intent
      ↓
intent/evaluator.py
      ↓
Score
```

Again, the evaluation criteria don't fundamentally change.

---

## 6. Retrieval Evaluation

This one becomes more important. Your actual graph will now perform:
```text
Query → Intent → Retriever → ChromaDB → Retrieved chunks
```

We evaluate those actual chunks. For example:
- **Expected chunks:** `chunk-A`, `chunk-B`
- **Actual retrieved:** `chunk-A`, `chunk-C`, `chunk-D`

The retrieval evaluator can determine:
- Was the correct information retrieved?
- Were relevant chunks retrieved?
- Were important chunks missed?
- How much irrelevant material was retrieved?

### Important Change
Your retrieval evaluator should not simply compare the generated answer. It needs access to:
- Actual retrieved chunk IDs
- Actual retrieved text
- Expected chunk IDs/sources

This is where your existing retrieval dataset becomes useful.

---

## 7. Response Evaluation Changes the Most

This is the biggest change from our previous design.

### Previously
```text
Dataset context → Generate/evaluate response
```

### Now
```text
Evaluation case → Actual connected graph → Actual retrieval → Actual response → Six LLM judges
```

The response evaluator should receive:
- Query
- Actual Retrieved Context
- Actual Generated Response
- Expected Answer
- Expected Citations

> [!IMPORTANT]
> **Do NOT replace actual context with dataset context.**
> Suppose your dataset contains Reference Context, but your real retriever returns Actual Context. The response evaluation should use the actual context for faithfulness. Otherwise, we could accidentally conclude "the answer is faithful" because it matches manually supplied context, even though the real retriever never surfaced it.

---

## 8. The Six Response Evaluators Stay the Same

Your response evaluator directory remains:

```text
evaluation/
└── evaluators/
    └── response/
        ├── llm_judge.py
        ├── correctness.py
        ├── faithfulness.py
        ├── relevance.py
        ├── completeness.py
        ├── citation.py
        └── safety.py
```

Their responsibilities don't change:

| Evaluator | What it evaluates |
| :--- | :--- |
| **Correctness** | Is the answer factually correct? |
| **Faithfulness** | Is it supported by actual retrieved context? |
| **Relevance** | Does it answer the query? |
| **Completeness** | Does it cover expected information? |
| **Citation** | Are citations appropriate and supported? |
| **Safety** | Does it avoid unsupported/misleading guidance? |

The inputs to them are what change.

---

## 9. `llm_judge.py` Stays as the Shared Engine

Keep `llm_judge.py`. It should remain the common interface used by all response evaluators:

```text
correctness.py  ──┐
faithfulness.py ──┤
relevance.py    ──┤
completeness.py ──┼──→ llm_judge.py ──→ Judge LLM
citation.py     ──┤
safety.py       ──┘
```

No need for six separate LLM clients or calling implementations.

---

## 10. Common Graph Adapter

This is the one structural change I would strongly recommend. Instead of making every evaluation runner figure out how to invoke your graph, create an adapter:

```text
evaluation/
├── graph/
│   └── adapter.py
├── datasets/
├── evaluators/
└── runners/
```

The adapter's job is to provide a consistent evaluation-facing interface to your connected graph:

```python
result = run_graph(query)
```

Returning a structured schema:

```json
{
  "processed_input": "...",
  "intent": "...",
  "retrieved_context": ["..."],
  "response": "...",
  "citations": ["..."]
}
```

Then all four evaluation runners can consume the same unified result.

---

## 11. Cleaner Architecture Flow

Instead of individual runners containing bespoke graph logic:

```text
                 Connected RAG Graph
                         ↑
                         │
                  graph/adapter.py
                         │
        ┌────────────────┼────────────────┐
        ↓                ↓                ↓
Input Runner       Intent Runner    Retrieval Runner
        │                │                │
        └────────────────┼────────────────┘
                         ↓
                  Response Runner
                         ↓
                 Response Evaluators
```

The adapter isolates your evaluation system from the implementation details of the graph.

---

## 12. Enhanced Langfuse Tracing

Since the graph is connected, you can obtain a complete multi-tier trace in Langfuse for each test case:

```text
Trace
│
├── Input Processor
│    └── Evaluation score
│
├── Intent
│    └── Evaluation score
│
├── Retrieval
│    └── Evaluation scores
│
└── Response
     ├── Correctness
     ├── Faithfulness
     ├── Relevance
     ├── Completeness
     ├── Citation
     └── Safety
```

This lets you isolate exactly where the pipeline is failing instead of diagnosing a single end-to-end score.

---

## 13. Target Evaluation Directory Structure

```text
evaluation/
│
├── datasets/
│   ├── input_processor/
│   │   └── cases.jsonl
│   ├── intent/
│   │   └── cases.jsonl
│   ├── retrieval/
│   │   └── cases.jsonl
│   └── response/
│       └── cases.jsonl
│
├── graph/
│   └── adapter.py
│
├── evaluators/
│   ├── input_processor/
│   │   └── evaluator.py
│   │
│   ├── intent/
│   │   └── evaluator.py
│   │
│   ├── retrieval/
│   │   └── evaluator.py
│   │
│   └── response/
│       ├── llm_judge.py
│       ├── correctness.py
│       ├── faithfulness.py
│       ├── relevance.py
│       ├── completeness.py
│       ├── citation.py
│       └── safety.py
│
├── runners/
│   ├── run_input_processor.py
│   ├── run_intent.py
│   ├── run_retrieval.py
│   └── run_response.py
│
├── configs/
│   └── thresholds.yaml
│
├── reports/
│
└── README.md
```

---

## 14. Implementation Order

Don't start rewriting all the evaluators. Execute in this order:

- **Step 1 — Understand the Connected Graph**: Identify the entry point, inputs, outputs, and exposed stage outputs (processed input, intent, retrieved chunks, final response, citations).
- **Step 2 — Build `graph/adapter.py`**: Create one unified evaluation interface to your graph.
- **Step 3 — Connect the Three Existing Evaluations**: Wire Input Processor, Intent, and Retrieval runners to the actual graph outputs.
- **Step 4 — Build `llm_judge.py`**: Implement the shared judge client, followed by the six response evaluator modules.
- **Step 5 — Build `run_response.py`**: Execute the actual graph across all 50 response cases and score the resulting outputs.
- **Step 6 — Integrate Langfuse**: Publish per-case scores, aggregate summaries, reasoning text, and full execution traces.

---

## Key Takeaway

Your datasets and evaluation criteria remain intact; the execution strategy matures.

- **Before:** Evaluation $\rightarrow$ Individual isolated component
- **Now:** Evaluation $\rightarrow$ Actual connected graph $\rightarrow$ Capture intermediate stage outputs $\rightarrow$ Evaluate each stage

This structure demonstrates not only that comprehensive evaluations exist, but that failures can be precisely attributed to input processing, intent detection, retrieval quality, or response generation.