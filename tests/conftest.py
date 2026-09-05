from agent_security.evaluators import PASS, evaluate
from agent_security.reset import reset_scenario
from agent_security.scenarios import SCENARIOS

import pytest


def pytest_sessionstart(session):
    failures = []
    for scenario in SCENARIOS.values():
        result = evaluate(scenario)
        if result["message"] != PASS:
            failures.append(f"{scenario['id']}: {result['message']}")
    if failures:
        raise pytest.UsageError(
            "Sandbox is dirty before tests; refusing to start. "
            "All scenarios must already evaluate to PASS: exploit blocked.\n"
            + "\n".join(failures)
        )


@pytest.fixture(autouse=True)
def restore_sandbox():
    yield
    for scenario_id in SCENARIOS:
        reset_scenario(scenario_id)


@pytest.fixture
def tmp_logs(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    monkeypatch.setattr("agent_security.replay.LOG_DIR", log_dir)
    monkeypatch.setattr("agent_security.replay.REPLAY_LOG", log_dir / "replay_log.jsonl")
    monkeypatch.setattr("agent_security.replay.TRACE_LOG", log_dir / "trace_log.jsonl")
    return log_dir
