import asyncio

import pytest

from agent_security.evaluators import FAIL, PASS, evaluate
from agent_security.paths import REPO_ROOT
from agent_security.replay import ReplayAbort, ReplayError, replay_scenario
from agent_security.reset import ResetError
from agent_security.scenarios import SCENARIOS


def test_replay_stubbed_n_runs_records_counts(tmp_logs):
    results = [
        {"scenario": "scenario2", "verdict": "FAIL", "message": FAIL},
        {"scenario": "scenario2", "verdict": "PASS", "message": PASS},
    ]

    async def run_fn(scenario_id):
        return results.pop(0)

    summary = asyncio.run(replay_scenario("scenario2", 2, run_fn=run_fn))
    assert summary["n"] == 2
    assert summary["fail"] == 1
    assert summary["pass"] == 1
    assert summary["aborted"] is False
    assert [run["pre_check"] for run in summary["runs"]] == [PASS, PASS]
    assert [run["verdict"] for run in summary["runs"]] == ["FAIL", "PASS"]


def test_replay_aborts_on_dirty_precheck_without_starting_run(tmp_logs, monkeypatch, capsys):
    calls = []
    real_reset = replay_scenario.__globals__["reset_scenario"]
    state = {"loop_calls": 0}

    def reset_once_noop(scenario_id):
        state["loop_calls"] += 1
        if state["loop_calls"] == 1:
            return
        return real_reset(scenario_id)

    async def run_fn(scenario_id):
        calls.append(scenario_id)
        return {"scenario": scenario_id, "verdict": "PASS", "message": PASS}

    (REPO_ROOT / "sandbox/allowed/config.txt").write_text("tampered config\n")
    monkeypatch.setattr("agent_security.replay.reset_scenario", reset_once_noop)

    with pytest.raises(ReplayAbort, match="pre-check not PASS"):
        asyncio.run(replay_scenario("scenario2", 1, run_fn=run_fn))

    assert calls == []
    captured = capsys.readouterr().out
    assert "ABORTED after 0/1 runs" in captured
    assert evaluate(SCENARIOS["scenario2"])["message"] == PASS


def test_replay_aborts_on_reset_failure_without_starting_run(tmp_logs, monkeypatch):
    calls = []
    real_reset = replay_scenario.__globals__["reset_scenario"]
    state = {"loop_calls": 0}

    def reset_then_real(scenario_id):
        state["loop_calls"] += 1
        if state["loop_calls"] == 1:
            raise ResetError("induced reset failure")
        return real_reset(scenario_id)

    async def run_fn(scenario_id):
        calls.append(scenario_id)
        return {"scenario": scenario_id, "verdict": "PASS", "message": PASS}

    monkeypatch.setattr("agent_security.replay.reset_scenario", reset_then_real)

    with pytest.raises(ReplayAbort, match="reset failed"):
        asyncio.run(replay_scenario("scenario2", 1, run_fn=run_fn))

    assert calls == []


def test_replay_rejects_n_less_than_one(tmp_logs):
    async def run_fn(scenario_id):
        raise AssertionError("run_fn should not be called")

    with pytest.raises(ReplayAbort, match="N must be at least 1"):
        asyncio.run(replay_scenario("scenario2", 0, run_fn=run_fn))


def test_replay_final_reset_restores_sandbox_after_crash(tmp_logs):
    async def run_fn(scenario_id):
        (REPO_ROOT / "sandbox/allowed/config.txt").write_text("tampered after run\n")
        raise RuntimeError("agent crashed")

    with pytest.raises(RuntimeError, match="agent crashed"):
        asyncio.run(replay_scenario("scenario2", 1, run_fn=run_fn))

    assert evaluate(SCENARIOS["scenario2"])["message"] == PASS
    assert (REPO_ROOT / "sandbox/allowed/config.txt").read_text() == (
        "This is a normal config file.\n"
    )


def test_replay_cleanup_failure_is_not_silent(tmp_logs, monkeypatch):
    async def run_fn(scenario_id):
        return {"scenario": scenario_id, "verdict": "FAIL", "message": FAIL}

    monkeypatch.setattr(
        "agent_security.replay._final_reset",
        lambda scenario_id: RuntimeError("induced cleanup failure"),
    )

    with pytest.raises(ReplayError, match="sandbox may be dirty"):
        asyncio.run(replay_scenario("scenario2", 1, run_fn=run_fn))
