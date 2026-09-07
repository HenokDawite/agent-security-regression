import asyncio
import json
import sqlite3

import pytest

from agent_security.evaluators import FAIL, PASS, evaluate
from agent_security.replay import ReplayAbort, ReplayError, replay_scenario
from agent_security.reset import ResetError
from agent_security.scenarios import SCENARIOS
from agent_security.store import (
    SCHEMA_VERSION,
    StoreError,
    connect,
    execution_mode,
    fetch_batches,
    fetch_results,
    finish_batch,
    record_result,
    run_standalone,
    settings_json,
    start_batch,
)


def test_evaluate_does_not_create_db(tmp_experiments_db):
    assert not tmp_experiments_db.exists()
    result = evaluate(SCENARIOS["scenario1"])
    assert result["message"] == PASS
    assert not tmp_experiments_db.exists()


def test_settings_json_is_canonical():
    encoded = settings_json(SCENARIOS["scenario5"])
    assert encoded == json.dumps(
        {
            "approval_tools": False,
            "denied_read_roots": ["forbidden"],
            "toctou": False,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    keys = list(json.loads(encoded))
    assert keys == sorted(keys)


def test_schema_user_version(tmp_experiments_db):
    conn = connect()
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        foreign = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    finally:
        conn.close()
    assert version == SCHEMA_VERSION
    assert foreign == 1


def test_execution_mode_docker(tmp_experiments_db, monkeypatch):
    monkeypatch.setenv("ASL_EXECUTION_MODE", "docker")
    batch_id = start_batch("single", SCENARIOS["scenario1"], requested=1)
    assert fetch_batches()[0]["execution_mode"] == "docker"
    assert batch_id


def test_execution_mode_constrained_to_host_or_docker(monkeypatch):
    monkeypatch.delenv("ASL_EXECUTION_MODE", raising=False)
    assert execution_mode() == "host"
    monkeypatch.setenv("ASL_EXECUTION_MODE", "host")
    assert execution_mode() == "host"
    monkeypatch.setenv("ASL_EXECUTION_MODE", "docker")
    assert execution_mode() == "docker"
    monkeypatch.setenv("ASL_EXECUTION_MODE", "yes")
    with pytest.raises(StoreError, match="invalid ASL_EXECUTION_MODE"):
        execution_mode()
    monkeypatch.setenv("ASL_EXECUTION_MODE", "container")
    with pytest.raises(StoreError, match="invalid ASL_EXECUTION_MODE"):
        execution_mode()


def test_single_run_persistence(tmp_experiments_db, monkeypatch):
    monkeypatch.setenv("ASL_EXECUTION_MODE", "host")

    async def run_fn(scenario_id):
        return {"scenario": scenario_id, "verdict": "FAIL", "message": FAIL}

    result = asyncio.run(run_standalone("scenario2", run_fn))
    assert result["message"] == FAIL
    batches = fetch_batches()
    assert len(batches) == 1
    batch = batches[0]
    assert batch["kind"] == "single"
    assert batch["scenario_id"] == "scenario2"
    assert batch["evaluator"] == "file_unchanged"
    assert batch["mitigation_label"] == "none"
    assert batch["execution_mode"] == "host"
    assert batch["requested"] == 1
    assert batch["completed"] == 1
    assert batch["status"] == "completed"
    rows = fetch_results(batch["id"])
    assert len(rows) == 1
    assert rows[0]["replay_index"] == 1
    assert rows[0]["verdict"] == "FAIL"
    assert rows[0]["exploit_succeeded"] == 1
    assert rows[0]["source"] == "live"


def test_standalone_exception_marks_aborted(tmp_experiments_db):
    async def run_fn(scenario_id):
        raise RuntimeError("agent crashed")

    with pytest.raises(RuntimeError, match="agent crashed"):
        asyncio.run(run_standalone("scenario2", run_fn))

    batches = fetch_batches()
    assert len(batches) == 1
    batch = batches[0]
    assert batch["status"] == "aborted"
    assert batch["completed"] == 0
    assert batch["finished_at"] is not None
    assert "agent crashed" in (batch["abort_reason"] or "")
    assert fetch_results(batch["id"]) == []


def test_replay_persistence(tmp_logs, tmp_experiments_db):
    results = [
        {"scenario": "scenario2", "verdict": "FAIL", "message": FAIL},
        {"scenario": "scenario2", "verdict": "PASS", "message": PASS},
    ]

    async def run_fn(scenario_id):
        return results.pop(0)

    summary = asyncio.run(replay_scenario("scenario2", 2, run_fn=run_fn))
    assert summary["n"] == 2
    batches = fetch_batches()
    assert len(batches) == 1
    batch = batches[0]
    assert batch["kind"] == "replay"
    assert batch["requested"] == 2
    assert batch["completed"] == 2
    assert batch["status"] == "completed"
    rows = fetch_results(batch["id"])
    assert [row["verdict"] for row in rows] == ["FAIL", "PASS"]
    assert [row["replay_index"] for row in rows] == [1, 2]
    assert [row["exploit_succeeded"] for row in rows] == [1, 0]
    replay_lines = (tmp_logs / "replay_log.jsonl").read_text().strip().splitlines()
    assert len(replay_lines) == 2


def test_abort_before_run_starts_has_no_result_rows(
    tmp_logs, tmp_experiments_db, monkeypatch
):
    async def run_fn(scenario_id):
        raise AssertionError("run_fn should not be called")

    real_reset = replay_scenario.__globals__["reset_scenario"]
    state = {"calls": 0}

    def reset_then_real(scenario_id):
        state["calls"] += 1
        if state["calls"] == 1:
            raise ResetError("induced reset failure")
        return real_reset(scenario_id)

    monkeypatch.setattr("agent_security.replay.reset_scenario", reset_then_real)
    with pytest.raises(ReplayAbort, match="reset failed"):
        asyncio.run(replay_scenario("scenario2", 2, run_fn=run_fn))

    batches = fetch_batches()
    assert len(batches) == 1
    batch = batches[0]
    assert batch["status"] == "aborted"
    assert batch["completed"] == 0
    assert batch["requested"] == 2
    assert batch["finished_at"] is not None
    assert fetch_results(batch["id"]) == []


def test_replay_run_fn_exception_keeps_prior_rows(tmp_logs, tmp_experiments_db):
    state = {"calls": 0}

    async def run_fn(scenario_id):
        state["calls"] += 1
        if state["calls"] == 1:
            return {"scenario": scenario_id, "verdict": "FAIL", "message": FAIL}
        raise RuntimeError("agent crashed on run 2")

    with pytest.raises(RuntimeError, match="agent crashed on run 2"):
        asyncio.run(replay_scenario("scenario2", 2, run_fn=run_fn))

    batch = fetch_batches()[0]
    assert batch["status"] == "aborted"
    assert batch["completed"] == 1
    assert batch["requested"] == 2
    assert batch["finished_at"] is not None
    rows = fetch_results(batch["id"])
    assert len(rows) == 1
    assert rows[0]["replay_index"] == 1
    assert rows[0]["verdict"] == "FAIL"


def test_n_less_than_one_creates_no_batch(tmp_experiments_db):
    async def run_fn(scenario_id):
        raise AssertionError("run_fn should not be called")

    with pytest.raises(ReplayAbort, match="N must be at least 1"):
        asyncio.run(replay_scenario("scenario2", 0, run_fn=run_fn))
    assert not tmp_experiments_db.exists()


def test_duplicate_result_row_raises(tmp_experiments_db):
    batch_id = start_batch("single", SCENARIOS["scenario1"], requested=1)
    record_result(batch_id, 1, "PASS", PASS)
    with pytest.raises(sqlite3.IntegrityError):
        record_result(batch_id, 1, "FAIL", FAIL)
    rows = fetch_results(batch_id)
    assert len(rows) == 1
    assert rows[0]["verdict"] == "PASS"


def test_family_c_series_stay_separate(tmp_experiments_db):
    pre = start_batch(
        "replay",
        SCENARIOS["scenario5"],
        requested=1,
        evaluator="resolved_read_not_under",
        mitigation="none",
    )
    post = start_batch(
        "replay",
        SCENARIOS["scenario5"],
        requested=1,
        evaluator="resolved_read_not_executed_under",
        mitigation="resolved-path-guard",
    )
    record_result(pre, 1, "FAIL", FAIL)
    finish_batch(pre, "completed")
    record_result(post, 1, "PASS", PASS)
    finish_batch(post, "completed")
    batches = {batch["id"]: batch for batch in fetch_batches()}
    assert batches[pre]["evaluator"] == "resolved_read_not_under"
    assert batches[pre]["mitigation_label"] == "none"
    assert batches[post]["evaluator"] == "resolved_read_not_executed_under"
    assert batches[post]["mitigation_label"] == "resolved-path-guard"
    assert fetch_results(pre)[0]["exploit_succeeded"] == 1
    assert fetch_results(post)[0]["exploit_succeeded"] == 0


def test_interrupted_running_batch(tmp_experiments_db):
    # running remains until finish_batch succeeds. Abrupt process exit is one
    # cause; a failed finalization write is another.
    batch_id = start_batch("replay", SCENARIOS["scenario2"], requested=3)
    batches = fetch_batches()
    assert len(batches) == 1
    assert batches[0]["id"] == batch_id
    assert batches[0]["status"] == "running"
    assert batches[0]["completed"] == 0
    assert batches[0]["finished_at"] is None
    assert fetch_results(batch_id) == []


def test_transactional_completed_count_on_duplicate(tmp_experiments_db):
    batch_id = start_batch("replay", SCENARIOS["scenario2"], requested=2)
    record_result(batch_id, 1, "FAIL", FAIL)
    assert fetch_batches()[0]["completed"] == 1
    with pytest.raises(sqlite3.IntegrityError):
        record_result(batch_id, 1, "PASS", PASS)
    batch = fetch_batches()[0]
    assert batch["completed"] == 1
    assert batch["status"] == "running"
    assert len(fetch_results(batch_id)) == 1


def test_store_failure_does_not_change_pass_fail(
    tmp_logs, tmp_experiments_db, monkeypatch, capsys
):
    async def run_fn(scenario_id):
        return {"scenario": scenario_id, "verdict": "FAIL", "message": FAIL}

    monkeypatch.setattr(
        "agent_security.store.record_result",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("disk full")),
    )
    summary = asyncio.run(replay_scenario("scenario2", 1, run_fn=run_fn))
    assert summary["fail"] == 1
    assert summary["runs"][0]["verdict"] == "FAIL"
    assert summary["runs"][0]["message"] == FAIL
    err = capsys.readouterr().err
    assert "experiment history write failed" in err


def test_standalone_store_failure_still_returns_verdict(
    tmp_experiments_db, monkeypatch, capsys
):
    async def run_fn(scenario_id):
        return {"scenario": scenario_id, "verdict": "PASS", "message": PASS}

    monkeypatch.setattr(
        "agent_security.store.record_result",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("disk full")),
    )
    result = asyncio.run(run_standalone("scenario1", run_fn))
    assert result["verdict"] == "PASS"
    assert result["message"] == PASS
    err = capsys.readouterr().err
    assert "experiment history write failed" in err


def test_cleanup_failed_keeps_completed_results(
    tmp_logs, tmp_experiments_db, monkeypatch
):
    async def run_fn(scenario_id):
        return {"scenario": scenario_id, "verdict": "FAIL", "message": FAIL}

    monkeypatch.setattr(
        "agent_security.replay._final_reset",
        lambda scenario_id: RuntimeError("induced cleanup failure"),
    )
    with pytest.raises(ReplayError, match="sandbox may be dirty"):
        asyncio.run(replay_scenario("scenario2", 1, run_fn=run_fn))

    batch = fetch_batches()[0]
    assert batch["status"] == "cleanup_failed"
    assert batch["completed"] == 1
    assert batch["finished_at"] is not None
    assert fetch_results(batch["id"])[0]["verdict"] == "FAIL"
