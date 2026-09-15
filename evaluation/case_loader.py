"""Shared loaders for evaluation case files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_cases(path: Path) -> list[dict[str, Any]]:
    """Load JSON array or JSON Lines evaluation cases."""

    if path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Evaluation dataset must contain a list: {path}")
    return payload


def find_default_dataset(directory: Path) -> Path:
    """Prefer the planned JSONL name, then support the current JSON dataset."""

    for name in ("cases.jsonl", "cases.json"):
        candidate = directory / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"No cases.jsonl or cases.json found in {directory}")


def validate_case_ids(cases: list[dict[str, Any]]) -> None:
    """Reject missing or duplicate case identifiers before a run."""

    ids = [case.get("id") for case in cases]
    if any(not case_id for case_id in ids):
        raise ValueError("Every evaluation case must have a non-empty id")
    if len(ids) != len(set(ids)):
        raise ValueError("Evaluation case ids must be unique")
