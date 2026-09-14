"""Optional Langfuse publishing for evaluation runs."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class LangfuseReporter:
    """Publish aggregate, per-case evaluation scores, and full reports to Langfuse."""

    def __init__(self, client: Any) -> None:
        self.client = client

    @classmethod
    def from_environment(cls) -> "LangfuseReporter":
        """Create a reporter, requiring the three Langfuse runtime settings."""

        load_dotenv()
        required = (
            "LANGFUSE_PUBLIC_KEY",
            "LANGFUSE_SECRET_KEY",
            "LANGFUSE_BASE_URL",
        )
        missing = [name for name in required if not os.getenv(name)]
        if missing:
            raise RuntimeError(
                "Langfuse publishing requires: " + ", ".join(missing)
            )

        from langfuse import Langfuse

        return cls(Langfuse())

    def publish(self, evaluation_name: str, report: dict[str, Any]) -> None:
        """Publish one evaluation report with its entire content to Langfuse."""

        metrics = report["metrics"]
        cases = report["cases"]
        with self.client.start_as_current_observation(
            name=f"evaluation:{evaluation_name}",
            as_type="evaluator",
            input={"evaluation": evaluation_name, "total_cases": len(cases)},
            metadata={"source": "government-document-helpdesk", "evaluation_name": evaluation_name},
        ) as observation:
            trace_id = getattr(observation, "trace_id", None)
            if trace_id:
                for metric_name, value in _numeric_metrics(metrics):
                    self.client.create_score(
                        name=metric_name,
                        value=value,
                        trace_id=trace_id,
                        data_type="NUMERIC",
                    )
                for case in cases:
                    self.client.create_score(
                        name="case_passed",
                        value=1.0 if case.get("passed", False) else 0.0,
                        trace_id=trace_id,
                        data_type="NUMERIC",
                        comment=case["id"],
                    )
            observation.update(output=report)
        self.client.flush()

    def publish_file(self, file_path: Path | str, evaluation_name: str | None = None) -> None:
        """Publish a single evaluation report JSON file to Langfuse."""

        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Report file not found: {path}")
        report = json.loads(path.read_text(encoding="utf-8"))
        default_name = path.parent.name if path.stem == "latest" and path.parent.name != "reports" else path.stem
        name = evaluation_name or default_name
        self.publish(name, report)

    def publish_directory(self, dir_path: Path | str) -> list[str]:
        """Publish all evaluation report JSON files in a directory to Langfuse."""

        directory = Path(dir_path)
        if not directory.is_dir():
            raise NotADirectoryError(f"Directory not found: {directory}")
        published = []
        for file in sorted(directory.rglob("*.json")):
            self.publish_file(file)
            published.append(str(file.relative_to(directory)))
        return published


def _numeric_metrics(metrics: dict[str, Any]):
    """Yield only scalar numeric metrics suitable for Langfuse scores."""

    for name, value in metrics.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            yield name, float(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish evaluation reports to Langfuse.")
    parser.add_argument(
        "target",
        nargs="?",
        default=str(PROJECT_ROOT / "evaluation/reports"),
        help="Path to a report JSON file or directory of reports (default: evaluation/reports)",
    )
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Custom evaluation name when publishing a single file (default: file stem or parent folder name for 'latest.json')",
    )
    args = parser.parse_args()
    target_path = Path(args.target)

    reporter = LangfuseReporter.from_environment()
    if target_path.is_file():
        reporter.publish_file(target_path, evaluation_name=args.name)
        print(f"Published report from {target_path} to Langfuse.")
    elif target_path.is_dir():
        published = reporter.publish_directory(target_path)
        print(
            f"Published {len(published)} reports from {target_path} to Langfuse: "
            f"{', '.join(published) if published else 'None'}"
        )
    else:
        print(f"Target path does not exist: {target_path}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
