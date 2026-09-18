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
from typing import Any, Dict, List, Optional

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
from langchain_community.callbacks import get_openai_callback
from app.rag.node import get_default_retriever_pipeline
from app.rag.vector_store import VectorStoreRetriever
from evaluation.case_loader import load_cases
from evaluation.evaluators.response.evaluator import evaluate_response_case
from evaluation.evaluators.retrieval.evaluator import (
    evaluate_retrieval_case,
    summarize_retrieval_results,
)
from evaluation.graph.adapter import ConnectedGraphAdapter, GraphEvaluationOutput
from evaluation.runners.run_retrieval import initialize_and_validate_corpus


def ensure_corpus_indexed() -> tuple[int, int]:
    """Ensure both dense vector store and BM25 lexical index are populated and validated."""
    pipeline = get_default_retriever_pipeline()
    return initialize_and_validate_corpus(pipeline)


def run_demo(
    start: int = 1,
    end: int = 3,
    output: Optional[Path] = None,
    adapter: Optional[ConnectedGraphAdapter] = None,
    cases_file: Optional[Path] = None,
) -> dict[str, Any]:
    chroma_count, bm25_count = ensure_corpus_indexed()

    if cases_file is None:
        cases_file = PROJECT_ROOT / "evaluation/datasets/response/cases.jsonl"
    all_cases = load_cases(cases_file)
    
    start_idx = max(1, start)
    end_idx = min(len(all_cases), end)
    cases_to_run = all_cases[start_idx - 1 : end_idx]

    langfuse_client = get_langfuse_client()
    if adapter is None:
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
            print(f"  -> Hybrid Candidates: Dense: {graph_output.dense_result_count} | Lexical: {graph_output.lexical_result_count}", flush=True)
            print(f"  -> Retrieved chunks ({len(graph_output.retrieved_chunk_ids)}): {graph_output.retrieved_chunk_ids}", flush=True)
            print(f"  -> Response preview: {graph_output.response[:120] if graph_output.response else 'None'}...", flush=True)
            print(f"  -> Citations ({len(graph_output.citations)}): {graph_output.citations}", flush=True)

            # Evaluate retrieval ranking quality against ground-truth chunks
            expected_chunks = case.get("expected_chunks") or [
                c["chunk_id"] for c in case.get("context", []) if isinstance(c, dict) and "chunk_id" in c
            ]
            retrieval_metrics = {
                "dense_result_count": graph_output.dense_result_count,
                "lexical_result_count": graph_output.lexical_result_count,
            }
            if expected_chunks:
                retrieval_eval = evaluate_retrieval_case(
                    case={"id": case_id, "query": query, "expected_chunks": expected_chunks},
                    retrieved_chunks=graph_output.retrieved_chunk_ids,
                    dense_result_count=graph_output.dense_result_count,
                    lexical_result_count=graph_output.lexical_result_count,
                )
                retrieval_metrics.update({
                    "recall_at_5": retrieval_eval.get("recall_at_5", 0.0),
                    "precision_at_5": retrieval_eval.get("precision_at_5", 0.0),
                    "mrr": retrieval_eval.get("mrr", 0.0),
                    "ndcg_at_5": retrieval_eval.get("ndcg_at_5", 0.0),
                })
                print(
                    f"  -> Retrieval Quality (Top-5): Recall: {retrieval_metrics['recall_at_5']:.2f} | "
                    f"Precision: {retrieval_metrics['precision_at_5']:.2f} | "
                    f"MRR: {retrieval_metrics['mrr']:.2f} | "
                    f"nDCG: {retrieval_metrics['ndcg_at_5']:.2f}",
                    flush=True,
                )

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

            # Run LLM judges on the actual response with token tracking
            print("  Evaluating response quality across 6 criteria (LLM judges)...", flush=True)
            with get_openai_callback() as eval_cb:
                eval_res = evaluate_response_case(
                    case=eval_case_data,
                    generated_response=graph_output.response or "",
                )

            scores = eval_res.get("scores", {})
            composite_score = eval_res.get("composite_score") or eval_res.get("average_score", 0.0)
            passed = eval_res.get("passed", False)

            # Aggregate token usage across pipeline and evaluation judges
            pipe_tokens = graph_output.token_usage or {}
            pipe_in = pipe_tokens.get("input_tokens", 0)
            pipe_out = pipe_tokens.get("output_tokens", 0)
            pipe_tot = pipe_tokens.get("total_tokens", 0)
            pipe_cost = pipe_tokens.get("cost_usd", 0.0)

            eval_tokens = {
                "input_tokens": eval_cb.prompt_tokens,
                "output_tokens": eval_cb.completion_tokens,
                "total_tokens": eval_cb.total_tokens,
                "cost_usd": eval_cb.total_cost,
            }

            turn_tokens = {
                "input_tokens": pipe_in + eval_tokens["input_tokens"],
                "output_tokens": pipe_out + eval_tokens["output_tokens"],
                "total_tokens": pipe_tot + eval_tokens["total_tokens"],
                "cost_usd": pipe_cost + eval_tokens["cost_usd"],
                "pipeline": pipe_tokens,
                "evaluators": eval_tokens,
            }

            print(f"  -> Tokens (Pipeline): {pipe_in} in / {pipe_out} out ({pipe_tot} total)", flush=True)
            print(f"  -> Tokens (Judges):   {eval_tokens['input_tokens']} in / {eval_tokens['output_tokens']} out ({eval_tokens['total_tokens']} total)", flush=True)
            print(f"  -> Tokens (Total):    {turn_tokens['input_tokens']} in / {turn_tokens['output_tokens']} out (~ ${turn_tokens['cost_usd']:.5f})", flush=True)
            print(f"  -> Evaluation Composite Score: {composite_score:.2f} (Passed: {passed})", flush=True)
            for crit, score in scores.items():
                print(f"     * {crit:<13}: {score:.2f}", flush=True)

            # Attach scores & token metrics to Langfuse trace
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
                    # Retrieval Quality Metrics on Langfuse
                    if retrieval_metrics:
                        langfuse_client.create_score(
                            name="retrieval_recall_at_5",
                            value=float(retrieval_metrics["recall_at_5"]),
                            trace_id=trace_id,
                            data_type="NUMERIC",
                        )
                        langfuse_client.create_score(
                            name="retrieval_precision_at_5",
                            value=float(retrieval_metrics["precision_at_5"]),
                            trace_id=trace_id,
                            data_type="NUMERIC",
                        )
                        langfuse_client.create_score(
                            name="retrieval_mrr",
                            value=float(retrieval_metrics["mrr"]),
                            trace_id=trace_id,
                            data_type="NUMERIC",
                        )
                        langfuse_client.create_score(
                            name="retrieval_ndcg_at_5",
                            value=float(retrieval_metrics["ndcg_at_5"]),
                            trace_id=trace_id,
                            data_type="NUMERIC",
                        )
                        langfuse_client.create_score(
                            name="retrieval_dense_result_count",
                            value=float(graph_output.dense_result_count),
                            trace_id=trace_id,
                            data_type="NUMERIC",
                        )
                        langfuse_client.create_score(
                            name="retrieval_lexical_result_count",
                            value=float(graph_output.lexical_result_count),
                            trace_id=trace_id,
                            data_type="NUMERIC",
                        )
                    # Token Usage Metrics
                    langfuse_client.create_score(
                        name="tokens_total",
                        value=float(turn_tokens["total_tokens"]),
                        trace_id=trace_id,
                        data_type="NUMERIC",
                    )
                    langfuse_client.create_score(
                        name="tokens_input",
                        value=float(turn_tokens["input_tokens"]),
                        trace_id=trace_id,
                        data_type="NUMERIC",
                    )
                    langfuse_client.create_score(
                        name="tokens_output",
                        value=float(turn_tokens["output_tokens"]),
                        trace_id=trace_id,
                        data_type="NUMERIC",
                    )
                    langfuse_client.create_score(
                        name="tokens_pipeline_input",
                        value=float(pipe_in),
                        trace_id=trace_id,
                        data_type="NUMERIC",
                    )
                    langfuse_client.create_score(
                        name="tokens_pipeline_output",
                        value=float(pipe_out),
                        trace_id=trace_id,
                        data_type="NUMERIC",
                    )
                    langfuse_client.create_score(
                        name="tokens_eval_input",
                        value=float(eval_tokens["input_tokens"]),
                        trace_id=trace_id,
                        data_type="NUMERIC",
                    )
                    langfuse_client.create_score(
                        name="tokens_eval_output",
                        value=float(eval_tokens["output_tokens"]),
                        trace_id=trace_id,
                        data_type="NUMERIC",
                    )
                    langfuse_client.create_score(
                        name="cost_usd",
                        value=float(turn_tokens["cost_usd"]),
                        trace_id=trace_id,
                        data_type="NUMERIC",
                    )
                except Exception as exc:
                    print(f"  [WARN] Failed to record scores to Langfuse: {exc}", flush=True)

            trace.update(
                output={
                    "intent": graph_output.intent,
                    "retrieved_chunk_ids": graph_output.retrieved_chunk_ids,
                    "dense_result_count": graph_output.dense_result_count,
                    "lexical_result_count": graph_output.lexical_result_count,
                    "retrieval_metrics": retrieval_metrics,
                    "response": graph_output.response,
                    "citations": graph_output.citations,
                    "evaluation_scores": scores,
                    "composite_score": composite_score,
                    "passed": passed,
                    "token_usage": turn_tokens,
                }
            )

            summary_results.append({
                "case_id": case_id,
                "query": query,
                "intent": graph_output.intent,
                "retrieved_chunks": len(graph_output.retrieved_chunk_ids),
                "dense_result_count": graph_output.dense_result_count,
                "lexical_result_count": graph_output.lexical_result_count,
                "retrieval_metrics": retrieval_metrics,
                "composite_score": composite_score,
                "passed": passed,
                "tokens": turn_tokens,
                "trace_id": trace_id,
            })

    # Flush all events to Langfuse cloud
    print("\nFlushing events to Langfuse...", flush=True)
    flush_langfuse()
    print("[OK] All observations and scores flushed to Langfuse.", flush=True)

    # Compute aggregate hybrid evidence and retrieval performance
    total_cases = len(summary_results)
    avg_dense = (
        sum(r.get("dense_result_count", 0) for r in summary_results) / total_cases
        if total_cases > 0
        else 0.0
    )
    avg_lexical = (
        sum(r.get("lexical_result_count", 0) for r in summary_results) / total_cases
        if total_cases > 0
        else 0.0
    )
    hybrid_verified = (
        chroma_count > 0
        and bm25_count > 0
        and avg_dense > 0
        and avg_lexical > 0
    )

    corpus_evidence = {
        "chroma_document_count": chroma_count,
        "bm25_document_count": bm25_count,
        "average_dense_result_count": avg_dense,
        "average_lexical_result_count": avg_lexical,
        "hybrid_retrieval_verified": hybrid_verified,
    }

    print("\n" + "=" * 60, flush=True)
    print("HYBRID RETRIEVAL EVALUATION EVIDENCE SUMMARY", flush=True)
    print("=" * 60, flush=True)
    print(f"Total Cases Evaluated:       {total_cases}", flush=True)
    print(f"Chroma Indexed Documents:    {chroma_count}", flush=True)
    print(f"BM25 Indexed Documents:      {bm25_count}", flush=True)
    print(f"Average Dense Candidates:    {avg_dense:.2f}", flush=True)
    print(f"Average Lexical Candidates:  {avg_lexical:.2f}", flush=True)
    verified_str = "YES" if hybrid_verified else "NO"
    print(f"Hybrid Evaluation Verified:  {verified_str}", flush=True)
    print("=" * 60 + "\n", flush=True)

    print("=" * 80, flush=True)
    print("SUMMARY OF CONNECTED GRAPH EVALUATION RUN", flush=True)
    print("=" * 80, flush=True)

    # Aggregate retrieval metrics across cases where ground truth was present
    evaluated_retrievals = [
        r["retrieval_metrics"] for r in summary_results
        if r.get("retrieval_metrics") and "recall_at_5" in r["retrieval_metrics"]
    ]
    avg_rec = 0.0
    avg_prec = 0.0
    avg_mrr = 0.0
    avg_ndcg = 0.0
    if evaluated_retrievals:
        avg_rec = sum(r["recall_at_5"] for r in evaluated_retrievals) / len(evaluated_retrievals)
        avg_prec = sum(r["precision_at_5"] for r in evaluated_retrievals) / len(evaluated_retrievals)
        avg_mrr = sum(r["mrr"] for r in evaluated_retrievals) / len(evaluated_retrievals)
        avg_ndcg = sum(r["ndcg_at_5"] for r in evaluated_retrievals) / len(evaluated_retrievals)
        print("OVERALL RETRIEVAL PERFORMANCE (Top-5):", flush=True)
        print(f"  Average Recall@5:    {avg_rec:.2f}", flush=True)
        print(f"  Average Precision@5: {avg_prec:.2f}", flush=True)
        print(f"  Average MRR:         {avg_mrr:.2f}", flush=True)
        print(f"  Average nDCG@5:      {avg_ndcg:.2f}", flush=True)
        print("-" * 80, flush=True)

    for res in summary_results:
        print(f"Case: {res['case_id']}", flush=True)
        print(f"  Query:            {res['query']}", flush=True)
        print(f"  Intent:           {res['intent']}", flush=True)
        print(f"  Hybrid Candidates: Dense={res.get('dense_result_count', 0)}, Lexical={res.get('lexical_result_count', 0)}", flush=True)
        print(f"  Chunks Retrieved: {res['retrieved_chunks']}", flush=True)
        rm = res.get("retrieval_metrics")
        if rm and "recall_at_5" in rm:
            print(f"  Retrieval (k=5):  Recall={rm['recall_at_5']:.2f}, Precision={rm['precision_at_5']:.2f}, MRR={rm['mrr']:.2f}, nDCG={rm['ndcg_at_5']:.2f}", flush=True)
        tokens = res.get("tokens", {})
        print(f"  Tokens:           {tokens.get('input_tokens', 0)} in / {tokens.get('output_tokens', 0)} out (Total: {tokens.get('total_tokens', 0)}, Cost: ${tokens.get('cost_usd', 0.0):.5f})", flush=True)
        print(f"  Composite Score:  {res['composite_score']:.2f}", flush=True)
        print(f"  Status:           {'PASSED' if res['passed'] else 'FAILED'}", flush=True)
        if res.get('trace_id'):
            print(f"  Langfuse Trace ID: {res['trace_id']}", flush=True)
        print("-" * 80, flush=True)

    report = {
        "corpus_evidence": corpus_evidence,
        "metrics": {
            "total_cases": total_cases,
            "average_dense_result_count": avg_dense,
            "average_lexical_result_count": avg_lexical,
            "chroma_document_count": chroma_count,
            "bm25_document_count": bm25_count,
            "hybrid_retrieval_verified": hybrid_verified,
            "average_recall_at_5": avg_rec,
            "average_precision_at_5": avg_prec,
            "average_mrr": avg_mrr,
            "average_ndcg_at_5": avg_ndcg,
        },
        "cases": summary_results,
    }

    report_path = output or (PROJECT_ROOT / "evaluation/reports/e2e/latest.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\n[OK] End-to-end evaluation report written to {report_path}", flush=True)

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run connected graph evaluation with Langfuse tracing.")
    parser.add_argument("--start", type=int, default=1, help="1-based start record index (inclusive, default: 1)")
    parser.add_argument("--end", type=int, default=3, help="1-based end record index (inclusive, default: 3)")
    parser.add_argument("--output", type=Path, default=None, help="Path to write the JSON evaluation report (default: evaluation/reports/e2e/latest.json)")
    args = parser.parse_args()

    run_demo(start=args.start, end=args.end, output=args.output)
