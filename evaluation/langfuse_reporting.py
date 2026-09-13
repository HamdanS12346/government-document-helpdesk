"""Optional Langfuse publishing for evaluation runs."""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv


class LangfuseReporter:
    """Publish aggregate and per-case evaluation scores to Langfuse."""

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
        """Publish one evaluation report without sending raw case input."""

        metrics = report["metrics"]
        cases = report["cases"]
        with self.client.start_as_current_observation(
            name=f"evaluation:{evaluation_name}",
            as_type="evaluator",
            input={"evaluation": evaluation_name, "total_cases": len(cases)},
            metadata={"source": "government-document-helpdesk"},
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
                        value=1.0 if case["passed"] else 0.0,
                        trace_id=trace_id,
                        data_type="NUMERIC",
                        comment=case["id"],
                    )
            observation.update(
                output={
                    "metrics": metrics,
                    "passed_cases": sum(case["passed"] for case in cases),
                }
            )
        self.client.flush()


def _numeric_metrics(metrics: dict[str, Any]):
    """Yield only scalar numeric metrics suitable for Langfuse scores."""

    for name, value in metrics.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            yield name, float(value)
