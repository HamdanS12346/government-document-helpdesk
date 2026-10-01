"""Run Multi-Turn Conversational Memory evaluation dataset."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional
import uuid

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.contracts.intent_decision import IntentDecision  # noqa: E402
from app.contracts.normalized_input import NormalizedInput  # noqa: E402
from app.intent.classifier import IntentClassifier  # noqa: E402
from app.intent.node import classify_intent  # noqa: E402
from evaluation.graph.adapter import resolve_intent_classifier  # noqa: E402
from app.memory.node import MemoryManager  # noqa: E402
from app.memory.repository import SupabaseMemoryRepository  # noqa: E402
from app.rag.query_rewriter import QueryRewriter  # noqa: E402
from evaluation.case_loader import find_default_dataset, load_cases, validate_case_ids  # noqa: E402
from evaluation.evaluators.memory.evaluator import (  # noqa: E402
    evaluate_memory_case,
    evaluate_memory_turn,
    summarize_memory_results,
)
from evaluation.langfuse_reporting import LangfuseReporter  # noqa: E402

logger = logging.getLogger(__name__)


class InMemoryEvaluationRepository(SupabaseMemoryRepository):
    """Isolated, fast in-memory repository for evaluation runs that never calls remote DB."""

    def __init__(self) -> None:
        super().__init__(supabase_url="", supabase_key="")

    def _init_client(self) -> None:
        self._is_live_supabase = False
        self._client = None


class OfflineMultiTurnQueryRewriter:
    """Deterministic offline rewriter resolving conversational references without external API calls."""

    _TOPIC_KEYWORDS = [
        ("minor", "minor passport"),
        ("tatkaal", "tatkaal passport"),
        ("passport", "passport renewal"),
        ("oci", "OCI card"),
        ("visa", "Indian visa"),
        ("disability", "disability certificate"),
        ("income", "income certificate"),
        ("residence", "residence certificate"),
        ("pan", "PAN card"),
        ("license", "driving license"),
        ("identity", "lost identity card"),
        ("tax", "tax clearance certificate"),
    ]

    def rewrite(
        self,
        user_query: str,
        messages: Optional[List[Any]] = None,
        conversation_summary: Optional[str] = None,
    ) -> str:
        lowered = user_query.lower()
        if not messages and not conversation_summary:
            return user_query

        # Check for explicit topic switch in user query
        for key, topic in self._TOPIC_KEYWORDS:
            if key in lowered and any(p in lowered for p in ["switching", "now what about", "instead", "what about a pan"]):
                return f"{user_query} ({topic})"

        # Identify context from recent conversation
        recent_context = ""
        if messages:
            for msg in messages:
                recent_context += f" {getattr(msg, 'content', '')}"
        if conversation_summary:
            recent_context += f" {conversation_summary}"
        recent_lower = recent_context.lower()

        context_topic = ""
        for key, topic in self._TOPIC_KEYWORDS:
            if key in recent_lower:
                context_topic = topic
                break

        # Check for pronouns, elliptical queries, or short questions requiring context
        pronoun_triggers = [
            " it", " this", " that", " the fee", " documents", " portal", " where",
            " how much", " do both", " who is", " which documents", "in that case",
            "for that", "appointment", "verification", "physically present",
        ]
        needs_context = any(p in lowered for p in pronoun_triggers) or len(lowered.split()) <= 6

        if context_topic and needs_context:
            # Avoid duplicating words already in query
            additions = []
            for word in context_topic.split():
                if word.lower() not in lowered and word.lower() != "card":
                    additions.append(word)
            if additions:
                return f"{user_query} ({' '.join(additions)})"

        return user_query


class OfflineMultiTurnIntentClassifier:
    """Offline heuristic classifier considering conversation context."""

    _doc_terms = {
        "passport", "visa", "oci", "certificate", "document", "application",
        "government", "benefit", "identity", "residence", "tax", "disability",
        "fee", "cost", "extend", "authority", "proof", "police", "verification",
        "tatkaal", "minor", "pan", "license",
    }

    _ambiguous_short = {
        "i need a visa", "passport", "documents?", "how do i get it?",
        "what is the fee?", "can i apply?", "i need help with my application.",
        "which documents?", "can you check this?", "i want to renew it.",
        "where do i submit it?", "is it still valid?", "i lost my document.",
        "what does this document do?", "i need a passport for a trip.",
    }

    def classify_with_context(
        self,
        query: str,
        messages: Optional[List[Any]] = None,
    ) -> str:
        lowered = query.lower().strip().rstrip(".").rstrip("?")
        has_history = bool(messages and len(messages) > 0)

        # Standalone ambiguous queries without history
        if not has_history:
            if lowered in self._ambiguous_short or lowered == "i need a visa":
                return "ambiguous"

        words = set(lowered.replace("?", " ").replace(".", " ").split())
        has_doc = bool(words & self._doc_terms)

        # In context of an ongoing document dialogue, follow-ups remain document_info
        if has_doc or has_history:
            return "document_info"

        return "general_chat"


def run_multi_turn_dataset(
    dataset_path: Path,
    *,
    offline: bool = False,
    start: Optional[int] = None,
    end: Optional[int] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """Execute evaluation over all multi-turn conversational cases."""
    cases = load_cases(dataset_path)
    validate_case_ids(cases)

    # Slice cases if requested
    if start is not None or end is not None:
        s = (start - 1) if start and start > 0 else 0
        e = end if end and end > 0 else len(cases)
        cases = cases[s:e]
    elif limit is not None and limit > 0:
        cases = cases[:limit]

    logger.info("Running multi-turn evaluation on %d cases (offline=%s)...", len(cases), offline)

    rewriter = OfflineMultiTurnQueryRewriter() if offline else QueryRewriter()
    offline_classifier = OfflineMultiTurnIntentClassifier()
    online_classifier = resolve_intent_classifier() if not offline else None

    evaluated_cases: List[Dict[str, Any]] = []

    for case in cases:
        # Generate valid RFC 4122 UUID for thread isolation
        thread_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"eval-{case['id']}"))
        config = {"configurable": {"thread_id": thread_id}}

        # In-memory repository per case to guarantee test isolation
        repo = InMemoryEvaluationRepository()
        mgr = MemoryManager(repository=repo)

        turn_results: List[Dict[str, Any]] = []

        for turn_data in case.get("turns", []):
            turn_num = turn_data.get("turn", 1)
            user_input = str(turn_data["user_input"])

            # Load active memory before turn execution
            memory_data = mgr.load_memory({}, config=config)
            messages = memory_data.get("messages", [])
            summary = memory_data.get("conversation_summary", "")

            norm_input = NormalizedInput(
                user_query=user_input,
                image_content=[],
                pdf_content=[],
                combined_text=f"<USER_QUERY>\n{user_input}",
            )

            # 1. Intent Classification
            if offline:
                actual_intent = offline_classifier.classify_with_context(user_input, messages=messages)
            else:
                state_for_intent = {
                    "normalized_input": norm_input,
                    "messages": messages,
                    "conversation_summary": summary,
                }
                decision = classify_intent(state_for_intent, online_classifier)
                actual_intent = decision["intent_decision"].intent_type.value

            # 2. Query Rewriting (Contextualization)
            rewritten_query = rewriter.rewrite(user_input, messages=messages, conversation_summary=summary)

            # 3. Evaluate Turn
            turn_eval = evaluate_memory_turn(turn_data, actual_intent, rewritten_query)
            turn_results.append(turn_eval)

            # 4. Save Turn to Memory
            mock_response = turn_data.get(
                "mock_assistant_response",
                f"Information regarding your request about {user_input}.",
            )
            turn_state = {
                "normalized_input": norm_input,
                "response": mock_response,
            }
            mgr.save_turn(turn_state, config=config)

        case_eval = evaluate_memory_case(case, turn_results)
        evaluated_cases.append(case_eval)

    summary_metrics = summarize_memory_results(evaluated_cases)

    return {
        "metrics": summary_metrics,
        "cases": evaluated_cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="Path to cases.json or cases.jsonl (defaults to evaluation/datasets/memory).",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Run deterministic offline evaluation without OpenAI API calls.",
    )
    parser.add_argument(
        "--no-langfuse",
        action="store_true",
        help="Skip publishing evaluation trace/scores to Langfuse.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Path to save the JSON evaluation report.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Limit number of cases.")
    parser.add_argument("--start", type=int, default=None, help="Start index (1-based).")
    parser.add_argument("--end", type=int, default=None, help="End index (1-based).")
    args = parser.parse_args()

    default_dir = PROJECT_ROOT / "evaluation" / "datasets" / "memory"
    dataset_path = args.dataset or find_default_dataset(default_dir)

    report = run_multi_turn_dataset(
        dataset_path,
        offline=args.offline,
        start=args.start,
        end=args.end,
        limit=args.limit,
    )

    metrics = report["metrics"]
    print("\n" + "=" * 60)
    print("Multi-Turn Conversational Memory Evaluation Summary")
    print("=" * 60)
    print(f"Total Cases:                 {metrics.get('total_cases', 0)}")
    print(f"Cases Passed:                {metrics.get('cases_passed', 0)} ({metrics.get('case_pass_rate', 0.0) * 100:.1f}%)")
    print(f"Total Turns Evaluated:       {metrics.get('total_turns', 0)}")
    print(f"Turns Passed:                {metrics.get('turns_passed', 0)} ({metrics.get('turn_pass_rate', 0.0) * 100:.1f}%)")
    print(f"Intent Preservation Acc:     {metrics.get('intent_preservation_accuracy', 0.0) * 100:.1f}%")
    print(f"Entity Resolution Acc:       {metrics.get('entity_resolution_accuracy', 0.0) * 100:.1f}%")
    print(f"Topic Switch Acc:            {metrics.get('topic_switch_accuracy', 0.0) * 100:.1f}%")
    print(f"Composite Memory Score:      {metrics.get('overall_score', 0.0):.4f}")
    print("-" * 60)
    print("Category Breakdown:")
    for cat, data in metrics.get("per_category", {}).items():
        print(f"  - {cat:<24} Passed: {data['passed']}/{data['cases']} ({data['pass_rate'] * 100:.1f}%)")
    print("=" * 60 + "\n")

    output_path = args.output or (PROJECT_ROOT / "evaluation" / "reports" / "memory" / "latest.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Report saved to: {output_path}")

    if not args.no_langfuse:
        try:
            reporter = LangfuseReporter.from_environment()
            reporter.publish("multi_turn_memory", report)
            print("Successfully published report to Langfuse.")
        except Exception as exc:
            logger.info("Langfuse publishing skipped: %s", exc)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
