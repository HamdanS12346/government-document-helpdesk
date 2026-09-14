from contextlib import contextmanager
import json

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


def test_reporter_publishes_entire_report_and_case_scores():
    client = FakeLangfuse()
    report = {
        "metrics": {
            "total_cases": 2,
            "accuracy": 0.5,
            "per_class": {"document_info": {"precision": 1.0}},
        },
        "cases": [
            {"id": "INT-001", "passed": True, "input": "sample query 1"},
            {"id": "INT-002", "passed": False, "input": "sample query 2"},
        ],
    }

    LangfuseReporter(client).publish("intent", report)

    assert client.inputs == [{"evaluation": "intent", "total_cases": 2}]
    assert {score["name"] for score in client.scores} == {
        "total_cases",
        "accuracy",
        "case_passed",
    }
    # Observation output contains the entire report structure
    assert client.observation.output == report
    assert client.observation.output["cases"] == report["cases"]
    assert client.observation.output["metrics"]["accuracy"] == 0.5
    assert client.flushed is True


def test_reporter_publishes_file(tmp_path):
    client = FakeLangfuse()
    report = {
        "metrics": {"total_cases": 1, "accuracy": 1.0},
        "cases": [{"id": "CASE-1", "passed": True}],
    }
    file_path = tmp_path / "custom_eval.json"
    file_path.write_text(json.dumps(report), encoding="utf-8")

    reporter = LangfuseReporter(client)
    reporter.publish_file(file_path)

    assert client.inputs == [{"evaluation": "custom_eval", "total_cases": 1}]
    assert client.observation.output == report


def test_reporter_publishes_directory(tmp_path):
    client = FakeLangfuse()
    report_a = {
        "metrics": {"total_cases": 1, "accuracy": 1.0},
        "cases": [{"id": "A-1", "passed": True}],
    }
    report_b = {
        "metrics": {"total_cases": 2, "accuracy": 0.5},
        "cases": [{"id": "B-1", "passed": True}, {"id": "B-2", "passed": False}],
    }
    (tmp_path / "eval_a.json").write_text(json.dumps(report_a), encoding="utf-8")
    (tmp_path / "eval_b.json").write_text(json.dumps(report_b), encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("not json", encoding="utf-8")

    reporter = LangfuseReporter(client)
    published = reporter.publish_directory(tmp_path)

    assert published == ["eval_a.json", "eval_b.json"]
    assert len(client.inputs) == 2


def test_reporter_requires_langfuse_environment(monkeypatch):
    monkeypatch.setattr("evaluation.langfuse_reporting.load_dotenv", lambda: None)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="LANGFUSE_PUBLIC_KEY"):
        LangfuseReporter.from_environment()

