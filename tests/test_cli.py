import importlib.util
import os
import sqlite3
import subprocess
import sys

import pytest

from agent_security import cli
from agent_security.evaluators import FAIL, PASS
from agent_security.paths import REPO_ROOT
from agent_security.replay import ReplayAbort, ReplayError
from agent_security.scenarios import SCENARIOS
from agent_security.store import connect, finish_batch, record_result, start_batch


def load_script(filename):
    path = REPO_ROOT / "scripts" / filename
    spec = importlib.util.spec_from_file_location(filename, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_help_exits_0(capsys):
    assert cli.main(["-h"]) == 0
    out = capsys.readouterr().out
    assert "run" in out
    assert "replay" in out
    assert "evaluate" in out
    assert "results" in out


def test_missing_and_unknown_command_exit_2(capsys):
    assert cli.main([]) == 2
    assert cli.main(["nope"]) == 2
    err = capsys.readouterr().err
    assert "command" in err or "usage" in err.lower()


def test_unknown_scenario_exit_2(capsys):
    assert cli.main(["run", "scenario99"]) == 2
    err = capsys.readouterr().err
    assert "Unknown scenario" in err
    assert "scenario5" in err


def test_replay_runs_validation_exit_2(capsys):
    assert cli.main(["replay", "scenario2"]) == 2
    assert cli.main(["replay", "scenario2", "--runs", "0"]) == 2
    assert cli.main(["replay", "scenario2", "--runs", "-1"]) == 2
    assert cli.main(["replay", "scenario2", "--runs", "foo"]) == 2
    err = capsys.readouterr().err
    assert "N must be at least 1" in err or "invalid" in err.lower()


def test_run_pass_and_fail_exit_0(monkeypatch, capsys):
    async def fake_standalone(scenario_id, run_fn, task_start_fn=None):
        return {"scenario": scenario_id, "verdict": "PASS", "message": PASS}

    monkeypatch.setattr(cli, "run_standalone", fake_standalone)
    assert cli.main(["run", "scenario1"]) == 0
    assert PASS in capsys.readouterr().out

    async def fake_fail(scenario_id, run_fn, task_start_fn=None):
        return {"scenario": scenario_id, "verdict": "FAIL", "message": FAIL}

    monkeypatch.setattr(cli, "run_standalone", fake_fail)
    assert cli.main(["run", "scenario2"]) == 0
    assert FAIL in capsys.readouterr().out


def test_run_exception_exit_1(monkeypatch, capsys):
    async def boom(scenario_id, run_fn, task_start_fn=None):
        raise RuntimeError("agent crashed")

    monkeypatch.setattr(cli, "run_standalone", boom)
    assert cli.main(["run", "scenario2"]) == 1
    assert "agent crashed" in capsys.readouterr().err


def test_evaluate_does_not_call_agent_reset_or_store(
    tmp_experiments_db, monkeypatch, capsys
):
    called = []

    async def fake_agent(*args, **kwargs):
        called.append("agent")

    monkeypatch.setattr("agent_security.agent_loop.run_agent", fake_agent)
    monkeypatch.setattr(
        "agent_security.reset.reset_scenario",
        lambda *args, **kwargs: called.append("reset"),
    )
    monkeypatch.setattr(
        "agent_security.store.connect",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("evaluate must not open SQLite")
        ),
    )
    monkeypatch.setattr(
        "agent_security.store.start_batch",
        lambda *args, **kwargs: called.append("store"),
    )
    assert cli.main(["evaluate", "scenario1"]) == 0
    assert called == []
    assert PASS in capsys.readouterr().out
    assert not tmp_experiments_db.exists()


def test_replay_forwards_runs_and_exit_codes(monkeypatch, capsys):
    seen = {}

    async def fake_replay(scenario_id, n, run_fn=None):
        seen["scenario_id"] = scenario_id
        seen["n"] = n
        return {"n": n}

    monkeypatch.setattr(cli, "replay_scenario", fake_replay)
    assert cli.main(["replay", "scenario2", "--runs", "4"]) == 0
    assert seen == {"scenario_id": "scenario2", "n": 4}

    async def abort(scenario_id, n, run_fn=None):
        raise ReplayAbort("pre-check not PASS")

    monkeypatch.setattr(cli, "replay_scenario", abort)
    assert cli.main(["replay", "scenario2", "--runs", "1"]) == 1

    async def cleanup(scenario_id, n, run_fn=None):
        raise ReplayError("sandbox may be dirty")

    monkeypatch.setattr(cli, "replay_scenario", cleanup)
    assert cli.main(["replay", "scenario2", "--runs", "1"]) == 1
    assert "sandbox may be dirty" in capsys.readouterr().out


def test_results_missing_db_does_not_create(tmp_experiments_db, capsys):
    assert not tmp_experiments_db.exists()
    assert cli.main(["results"]) == 0
    assert "No experiment history." in capsys.readouterr().out
    assert not tmp_experiments_db.exists()
    assert cli.main(["results", "scenario5"]) == 0
    assert "No experiment history for scenario5." in capsys.readouterr().out
    assert not tmp_experiments_db.exists()


def test_results_does_not_use_writable_connect(
    tmp_experiments_db, monkeypatch, capsys
):
    batch_id = start_batch("replay", SCENARIOS["scenario5"], requested=4)
    record_result(batch_id, 1, "PASS", PASS)
    record_result(batch_id, 2, "FAIL", FAIL)
    finish_batch(batch_id, "completed")

    monkeypatch.setattr(
        "agent_security.store.connect",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("results must not open a writable SQLite connection")
        ),
    )
    assert cli.main(["results", "scenario5"]) == 0
    out = capsys.readouterr().out
    assert "scenario5" in out
    assert "replay" in out
    assert "completed" in out
    assert "2/4" in out
    assert "exploit succeeded: 1/2" in out


def test_results_lists_all_and_filters(tmp_experiments_db, capsys):
    first = start_batch("single", SCENARIOS["scenario2"], requested=1)
    record_result(first, 1, "FAIL", FAIL)
    finish_batch(first, "completed")
    second = start_batch("replay", SCENARIOS["scenario5"], requested=1)
    finish_batch(second, "aborted", "reset failed")

    assert cli.main(["results"]) == 0
    all_out = capsys.readouterr().out
    assert "scenario2" in all_out
    assert "scenario5" in all_out
    assert "aborted" in all_out

    assert cli.main(["results", "scenario2"]) == 0
    filtered = capsys.readouterr().out
    assert "scenario2" in filtered
    assert "scenario5" not in filtered

    assert cli.main(["results", "scenario1"]) == 0
    assert "No experiment history for scenario1." in capsys.readouterr().out


def test_results_unknown_scenario_exit_2(tmp_experiments_db, capsys):
    assert cli.main(["results", "scenario99"]) == 2
    assert "Unknown scenario" in capsys.readouterr().err
    assert not tmp_experiments_db.exists()


def test_results_unreadable_db_exit_1(tmp_experiments_db, capsys):
    conn = connect()
    conn.execute("PRAGMA user_version = 99")
    conn.commit()
    conn.close()
    assert cli.main(["results"]) == 1
    assert "unsupported experiments.sqlite schema version" in capsys.readouterr().err


def test_results_readonly_helper_rejects_writes(tmp_experiments_db):
    start_batch("single", SCENARIOS["scenario1"], requested=1)
    from agent_security.store import connect_readonly

    conn = connect_readonly()
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("DELETE FROM run_batches")
            conn.commit()
    finally:
        conn.close()


def test_docker_flag_is_rejected(capsys):
    assert cli.main(["run", "scenario5", "--docker"]) == 2
    err = capsys.readouterr().err
    assert "unrecognized arguments" in err or "usage" in err.lower()


def test_wrapper_propagates_cli_exit_codes(monkeypatch):
    run_script = load_script("run_scenario.py")
    replay_script = load_script("replay_scenario.py")
    seen = []

    def fake_main(argv):
        seen.append(argv)
        return 7

    monkeypatch.setattr(run_script, "cli_main", fake_main)
    monkeypatch.setattr(replay_script, "cli_main", fake_main)
    assert run_script.main(["scenario2"]) == 7
    assert replay_script.main(["scenario2", "3"]) == 7
    assert seen == [
        ["run", "scenario2"],
        ["replay", "scenario2", "--runs", "3"],
    ]


def test_wrapper_usage_and_invalid_n_exit_2(capsys):
    run_script = load_script("run_scenario.py")
    replay_script = load_script("replay_scenario.py")
    assert run_script.main([]) == 2
    assert replay_script.main(["scenario2"]) == 2
    assert replay_script.main(["scenario2", "foo"]) == 2
    out = capsys.readouterr().out
    assert "Usage: python scripts/run_scenario.py" in out
    assert "N must be an integer" in out


def test_wrapper_subprocess_propagates_exit_codes():
    env = {**os.environ, "ANTHROPIC_API_KEY": "test-only-dummy-key"}
    run_usage = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/run_scenario.py")],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    assert run_usage.returncode == 2
    replay_bad_n = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/replay_scenario.py"), "scenario2", "foo"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    assert replay_bad_n.returncode == 2
    module_help = subprocess.run(
        [sys.executable, "-m", "agent_security", "-h"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    assert module_help.returncode == 0
    assert "evaluate" in module_help.stdout
    script_help = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/agentsec.py"), "-h"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    assert script_help.returncode == 0
    evaluate = subprocess.run(
        [sys.executable, "-m", "agent_security", "evaluate", "scenario1"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    assert evaluate.returncode == 0
    assert PASS in evaluate.stdout
