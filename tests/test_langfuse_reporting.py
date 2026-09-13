from contextlib import contextmanager

import pytest

from evaluation.langfuse_reporting import LangfuseReporter


class FakeObservation:
    trace_id = "trace-123"

    def __init__(self):
        self.output = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def update(self, **kwargs):
        self.output = kwargs["output"]


class FakeLangfuse:
    def __init__(self):
        self.observation = FakeObservation()
        self.scores = []
        self.flushed = False
        self.inputs = []

    @contextmanager
    def start_as_current_observation(self, **kwargs):
        self.inputs.append(kwargs["input"])
        yield self.observation

    def create_score(self, **kwargs):
        self.scores.append(kwargs)

    def flush(self):
        self.flushed = True


def test_reporter_publishes_metrics_and_case_scores_without_case_inputs():
    client = FakeLangfuse()
    report = {
        "metrics": {
            "total_cases": 2,
            "accuracy": 0.5,
            "per_class": {"document_info": {"precision": 1.0}},
        },
        "cases": [
            {"id": "INT-001", "passed": True, "input": "private query"},
            {"id": "INT-002", "passed": False, "input": "private query 2"},
        ],
    }

    LangfuseReporter(client).publish("intent", report)

    assert client.inputs == [{"evaluation": "intent", "total_cases": 2}]
    assert {score["name"] for score in client.scores} == {
        "total_cases",
        "accuracy",
        "case_passed",
    }
    assert all("private query" not in str(score) for score in client.scores)
    assert client.observation.output["metrics"]["accuracy"] == 0.5
    assert client.flushed is True


def test_reporter_requires_langfuse_environment(monkeypatch):
    monkeypatch.setattr("evaluation.langfuse_reporting.load_dotenv", lambda: None)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="LANGFUSE_PUBLIC_KEY"):
        LangfuseReporter.from_environment()
