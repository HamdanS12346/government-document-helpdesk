"""End-to-End Evaluation Demo for Connected Graph with Langfuse Tracing.

Runs 3 test cases through the connected LangGraph pipeline via ConnectedGraphAdapter,
records all node spans and evaluation metrics, and sends them directly to Langfuse.
"""

from __future__ import annotations

import argparse
import json
import os
os.environ["LANGFUSE_ENABLED"] = "true"
from pathlib import Path
import sys
from typing import Any, Dict, List

from dotenv import load_dotenv

# Load environment
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings
get_settings.cache_clear()
from app.contracts.retrieval import RetrievedDocument
from app.observability.langfuse import flush_langfuse, get_langfuse_client, start_observation
get_langfuse_client.cache_clear()
from app.rag.node import get_default_retriever_pipeline
from app.rag.vector_store import VectorStoreRetriever
from evaluation.case_loader import load_cases
from evaluation.evaluators.response.evaluator import evaluate_response_case
from evaluation.graph.adapter import ConnectedGraphAdapter, GraphEvaluationOutput


def ensure_corpus_indexed() -> None:
    """Ensure the lexical searcher (BM25) is loaded with documents from Chroma."""
    print("Connecting to ChromaDB and preparing lexical search index...", flush=True)
    retriever = VectorStoreRetriever()
    documents: List[RetrievedDocument] = retriever.get_all_documents()
    if documents:
        pipeline = get_default_retriever_pipeline()
        pipeline.lexical_searcher.index(documents)
        print(f"[OK] Loaded {len(documents)} documents into BM25 index (Chroma vector store already active).\n", flush=True)
    else:
        print("[WARN] No documents found in ChromaDB, proceeding with available store.\n", flush=True)


def run_demo(start: int = 1, end: int = 3) -> None:
    ensure_corpus_indexed()

    cases_file = PROJECT_ROOT / "evaluation/datasets/response/cases.jsonl"
    all_cases = load_cases(cases_file)
    
    start_idx = max(1, start)
    end_idx = min(len(all_cases), end)
    cases_to_run = all_cases[start_idx - 1 : end_idx]

    langfuse_client = get_langfuse_client()
    adapter = ConnectedGraphAdapter()

    print("=" * 80, flush=True)
    print(f"RUNNING CONNECTED GRAPH EVALUATION ON RECORDS {start_idx} TO {end_idx} ({len(cases_to_run)} TEST CASES)", flush=True)
    print(f"Langfuse Client Active: {langfuse_client is not None}", flush=True)
    print("=" * 80, flush=True)

    summary_results = []

    for offset, case in enumerate(cases_to_run):
        record_num = start_idx + offset
        case_id = case.get("id", f"CASE-{record_num}")
        query = case.get("query", "")

        print(f"\n[{record_num}/{end_idx}] Case ID: {case_id}", flush=True)
        print(f"  Query: {query}", flush=True)

        trace_id = None
        # Wrap each case turn in an outer Langfuse observation trace
        with start_observation(
            name=f"eval_case:{case_id}",
            as_type="chain",
            input={"case_id": case_id, "query": query},
            metadata={
                "evaluation_mode": "connected_graph_demo",
                "case_id": case_id,
                "document": case.get("metadata", {}).get("document", ""),
                "question_type": case.get("metadata", {}).get("question_type", ""),
            },
        ) as trace:
            trace_id = getattr(trace, "trace_id", None) or getattr(trace, "id", None)

            # Execute connected graph through the adapter
            graph_output: GraphEvaluationOutput = adapter.run(query=query)

            if not graph_output.success:
                print(f"  [ERROR] Graph execution failed: {graph_output.error}")
                trace.update(output={"error": graph_output.error, "status": "failed"})
                continue

            print(f"  -> Intent: {graph_output.intent} (confidence: {graph_output.confidence_score})", flush=True)
            print(f"  -> Retrieved chunks ({len(graph_output.retrieved_chunk_ids)}): {graph_output.retrieved_chunk_ids}", flush=True)
            print(f"  -> Response preview: {graph_output.response[:120] if graph_output.response else 'None'}...", flush=True)
            print(f"  -> Citations ({len(graph_output.citations)}): {graph_output.citations}", flush=True)

            # Construct case evaluation with ACTUAL retrieved context
            eval_case_data = {
                "id": case_id,
                "query": query,
                "context": [
                    {"chunk_id": cid, "text": graph_output.formatted_context or ""}
                    for cid in graph_output.retrieved_chunk_ids
                ],
                "expected_answer": case.get("expected_answer"),
                "expected_citations": case.get("expected_citations"),
            }

            # Run LLM judges on the actual response
            print("  Evaluating response quality across 6 criteria (LLM judges)...", flush=True)
            eval_res = evaluate_response_case(
                case=eval_case_data,
                generated_response=graph_output.response or "",
            )

            scores = eval_res.get("scores", {})
            composite_score = eval_res.get("composite_score", 0.0)
            passed = eval_res.get("passed", False)

            print(f"  -> Evaluation Composite Score: {composite_score:.2f} (Passed: {passed})")
            for crit, score in scores.items():
                print(f"     * {crit:<13}: {score:.2f}")

            # Attach scores to Langfuse trace
            if langfuse_client and trace_id:
                try:
                    langfuse_client.create_score(
                        name="composite_score",
                        value=composite_score,
                        trace_id=trace_id,
                        data_type="NUMERIC",
                        comment=f"Overall evaluation score for {case_id}",
                    )
                    for crit, score in scores.items():
                        langfuse_client.create_score(
                            name=f"eval_{crit}",
                            value=float(score),
                            trace_id=trace_id,
                            data_type="NUMERIC",
                        )
                except Exception as exc:
                    print(f"  [WARN] Failed to record scores to Langfuse: {exc}")

            trace.update(
                output={
                    "intent": graph_output.intent,
                    "retrieved_chunk_ids": graph_output.retrieved_chunk_ids,
                    "response": graph_output.response,
                    "citations": graph_output.citations,
                    "evaluation_scores": scores,
                    "composite_score": composite_score,
                    "passed": passed,
                }
            )

            summary_results.append({
                "case_id": case_id,
                "query": query,
                "intent": graph_output.intent,
                "retrieved_chunks": len(graph_output.retrieved_chunk_ids),
                "composite_score": composite_score,
                "passed": passed,
                "trace_id": trace_id,
            })

    # Flush all events to Langfuse cloud
    print("\nFlushing events to Langfuse...")
    flush_langfuse()
    print("[OK] All observations and scores flushed to Langfuse.")

    print("\n" + "=" * 80, flush=True)
    print("SUMMARY OF CONNECTED GRAPH EVALUATION RUN", flush=True)
    print("=" * 80, flush=True)
    for res in summary_results:
        print(f"Case: {res['case_id']}", flush=True)
        print(f"  Query:            {res['query']}", flush=True)
        print(f"  Intent:           {res['intent']}", flush=True)
        print(f"  Chunks Retrieved: {res['retrieved_chunks']}", flush=True)
        print(f"  Composite Score:  {res['composite_score']:.2f}", flush=True)
        print(f"  Status:           {'PASSED' if res['passed'] else 'FAILED'}", flush=True)
        if res.get('trace_id'):
            print(f"  Langfuse Trace ID: {res['trace_id']}", flush=True)
        print("-" * 80, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run connected graph evaluation with Langfuse tracing.")
    parser.add_argument("--start", type=int, default=1, help="1-based start record index (inclusive, default: 1)")
    parser.add_argument("--end", type=int, default=3, help="1-based end record index (inclusive, default: 3)")
    args = parser.parse_args()

    run_demo(start=args.start, end=args.end)
