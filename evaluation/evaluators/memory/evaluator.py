"""Metrics and evaluation logic for Multi-Turn Conversational Memory."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def evaluate_memory_turn(
    turn_case: Dict[str, Any],
    actual_intent: str,
    actual_rewritten_query: str,
) -> Dict[str, Any]:
    """Evaluate a single turn within a multi-turn conversation case."""
    expected_intent = turn_case.get("expected_intent")
    intent_passed = expected_intent is None or (expected_intent == actual_intent)

    expected_contains = turn_case.get("expected_rewritten_query_contains", [])
    lowered_query = actual_rewritten_query.lower()

    entities_matched: List[str] = []
    entities_missed: List[str] = []
    for entity in expected_contains:
        if entity.lower() in lowered_query:
            entities_matched.append(entity)
        else:
            entities_missed.append(entity)

    entity_resolution_score = (
        len(entities_matched) / len(expected_contains)
        if expected_contains
        else 1.0
    )

    negative_entities = turn_case.get("negative_entities", [])
    negative_found = [neg for neg in negative_entities if neg.lower() in lowered_query]
    topic_switch_passed = len(negative_found) == 0

    turn_passed = (
        intent_passed
        and entity_resolution_score >= 0.8
        and topic_switch_passed
    )

    return {
        "turn": turn_case.get("turn"),
        "user_input": turn_case.get("user_input"),
        "expected_intent": expected_intent,
        "actual_intent": actual_intent,
        "intent_passed": intent_passed,
        "actual_rewritten_query": actual_rewritten_query,
        "entities_matched": entities_matched,
        "entities_missed": entities_missed,
        "entity_resolution_score": round(entity_resolution_score, 4),
        "negative_entities_found": negative_found,
        "topic_switch_passed": topic_switch_passed,
        "passed": turn_passed,
    }


def evaluate_memory_case(
    case: Dict[str, Any],
    turn_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Evaluate an entire multi-turn case across all of its executed turns."""
    category = case.get("metadata", {}).get("category", "general")
    total_turns = len(turn_results)
    passed_turns = sum(1 for t in turn_results if t["passed"])
    case_passed = (passed_turns == total_turns) if total_turns > 0 else False

    mean_entity_score = (
        sum(t["entity_resolution_score"] for t in turn_results) / total_turns
        if total_turns > 0
        else 1.0
    )

    return {
        "id": case["id"],
        "title": case.get("title", ""),
        "category": category,
        "total_turns": total_turns,
        "passed_turns": passed_turns,
        "mean_entity_resolution_score": round(mean_entity_score, 4),
        "passed": case_passed,
        "turns": turn_results,
    }


def summarize_memory_results(cases_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate metrics across all multi-turn conversation cases."""
    if not cases_results:
        return {}

    total_cases = len(cases_results)
    cases_passed = sum(1 for c in cases_results if c.get("passed", False))

    all_turns: List[Dict[str, Any]] = []
    for c in cases_results:
        all_turns.extend(c.get("turns", []))

    total_turns = len(all_turns)
    turns_passed = sum(1 for t in all_turns if t.get("passed", False))

    intent_checks = [t for t in all_turns if t.get("expected_intent") is not None]
    intent_passed = sum(1 for t in intent_checks if t.get("intent_passed", False))
    intent_accuracy = intent_passed / len(intent_checks) if intent_checks else 1.0

    entity_scores = [t.get("entity_resolution_score", 1.0) for t in all_turns]
    avg_entity_resolution = sum(entity_scores) / len(entity_scores) if entity_scores else 1.0

    topic_switch_turns = [
        t for t in all_turns
        if "negative_entities_found" in t and (t.get("negative_entities_found") or t.get("topic_switch_passed") is not None)
    ]
    topic_switch_passed = sum(1 for t in topic_switch_turns if t.get("topic_switch_passed", True))
    topic_switch_accuracy = (
        topic_switch_passed / len(topic_switch_turns)
        if topic_switch_turns
        else 1.0
    )

    per_category: Dict[str, Dict[str, Any]] = {}
    categories = {c.get("category", "general") for c in cases_results}
    for cat in sorted(categories):
        cat_cases = [c for c in cases_results if c.get("category") == cat]
        cat_passed = sum(1 for c in cat_cases if c.get("passed", False))
        per_category[cat] = {
            "cases": len(cat_cases),
            "passed": cat_passed,
            "pass_rate": round(cat_passed / len(cat_cases), 4) if cat_cases else 0.0,
        }

    overall_score = round(
        (0.4 * (cases_passed / total_cases))
        + (0.3 * avg_entity_resolution)
        + (0.3 * intent_accuracy),
        4,
    )

    return {
        "total_cases": total_cases,
        "cases_passed": cases_passed,
        "case_pass_rate": round(cases_passed / total_cases, 4),
        "total_turns": total_turns,
        "turns_passed": turns_passed,
        "turn_pass_rate": round(turns_passed / total_turns, 4) if total_turns else 0.0,
        "intent_preservation_accuracy": round(intent_accuracy, 4),
        "entity_resolution_accuracy": round(avg_entity_resolution, 4),
        "topic_switch_accuracy": round(topic_switch_accuracy, 4),
        "overall_score": overall_score,
        "per_category": per_category,
    }
