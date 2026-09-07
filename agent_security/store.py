import hashlib
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime
from pathlib import Path

from agent_security import paths
from agent_security.runner import get_scenario

SCHEMA_VERSION = 1
AGENT_MODEL = "claude-sonnet-4-6"
SOURCE_LIVE = "live"


class StoreError(Exception):
    pass


def get_db_path():
    return Path(paths.EXPERIMENTS_DB)


def execution_mode():
    mode = os.environ.get("ASL_EXECUTION_MODE", "host")
    if mode in ("host", "docker"):
        return mode
    raise StoreError(
        f"invalid ASL_EXECUTION_MODE={mode!r}; expected 'host' or 'docker'"
    )


def mitigation_label(scenario):
    if scenario.resolve_guard is not None:
        return "resolved-path-guard"
    return "none"


def settings_json(scenario):
    roots = []
    if scenario.resolve_guard is not None:
        roots = list(scenario.resolve_guard.denied_read_roots)
    payload = {
        "approval_tools": bool(scenario.approval_tools),
        "denied_read_roots": roots,
        "toctou": scenario.toctou is not None,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def prompt_sha256(prompt):
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _now():
    return datetime.utcnow().isoformat()


def connect(db_path=None):
    path = Path(db_path) if db_path is not None else get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current == 0:
        _init_schema(conn)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
    elif current != SCHEMA_VERSION:
        conn.close()
        raise StoreError(
            f"unsupported experiments.sqlite schema version {current}; "
            f"expected {SCHEMA_VERSION}"
        )
    return conn


def _init_schema(conn):
    conn.executescript(
        """
        CREATE TABLE run_batches (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            scenario_id TEXT NOT NULL,
            evaluator TEXT NOT NULL,
            model TEXT NOT NULL,
            mitigation_label TEXT NOT NULL,
            settings_json TEXT NOT NULL,
            prompt_sha256 TEXT NOT NULL,
            execution_mode TEXT NOT NULL,
            requested INTEGER NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            abort_reason TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT
        );

        CREATE TABLE run_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL,
            replay_index INTEGER NOT NULL,
            verdict TEXT NOT NULL,
            message TEXT NOT NULL,
            exploit_succeeded INTEGER NOT NULL,
            pre_check TEXT,
            task_start TEXT,
            window_start TEXT,
            window_end TEXT,
            source TEXT NOT NULL DEFAULT 'live',
            FOREIGN KEY (batch_id) REFERENCES run_batches(id),
            UNIQUE (batch_id, replay_index)
        );
        """
    )


def start_batch(
    kind,
    scenario,
    requested,
    evaluator=None,
    mitigation=None,
    db_path=None,
):
    # Inserts status=running. Normal paths later finish as completed, aborted,
    # or cleanup_failed. running can remain if the process never reaches
    # finalization, or if the finish write itself fails.
    batch_id = uuid.uuid4().hex
    conn = connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO run_batches (
                id, kind, scenario_id, evaluator, model, mitigation_label,
                settings_json, prompt_sha256, execution_mode, requested,
                completed, status, abort_reason, started_at, finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'running', NULL, ?, NULL)
            """,
            (
                batch_id,
                kind,
                scenario.id,
                evaluator if evaluator is not None else scenario.evaluator,
                AGENT_MODEL,
                mitigation if mitigation is not None else mitigation_label(scenario),
                settings_json(scenario),
                prompt_sha256(scenario.prompt),
                execution_mode(),
                requested,
                _now(),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return batch_id


def record_result(
    batch_id,
    replay_index,
    verdict,
    message,
    pre_check=None,
    task_start="",
    window_start="",
    window_end="",
    source=SOURCE_LIVE,
    db_path=None,
):
    exploit_succeeded = 1 if verdict == "FAIL" else 0
    conn = connect(db_path)
    try:
        conn.execute("BEGIN")
        conn.execute(
            """
            INSERT INTO run_results (
                batch_id, replay_index, verdict, message, exploit_succeeded,
                pre_check, task_start, window_start, window_end, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_id,
                replay_index,
                verdict,
                message,
                exploit_succeeded,
                pre_check,
                task_start,
                window_start,
                window_end,
                source,
            ),
        )
        conn.execute(
            "UPDATE run_batches SET completed = completed + 1 WHERE id = ?",
            (batch_id,),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def finish_batch(batch_id, status, abort_reason=None, db_path=None):
    conn = connect(db_path)
    try:
        conn.execute(
            """
            UPDATE run_batches
            SET status = ?, abort_reason = ?, finished_at = ?
            WHERE id = ?
            """,
            (status, abort_reason, _now(), batch_id),
        )
        conn.commit()
    finally:
        conn.close()


def report_store_error(exc):
    print(f"ERROR: experiment history write failed: {exc}", file=sys.stderr)


def try_start_batch(*args, **kwargs):
    try:
        return start_batch(*args, **kwargs)
    except Exception as exc:
        report_store_error(exc)
        return None


def try_record_result(*args, **kwargs):
    try:
        record_result(*args, **kwargs)
        return True
    except Exception as exc:
        report_store_error(exc)
        return False


def try_finish_batch(*args, **kwargs):
    try:
        finish_batch(*args, **kwargs)
        return True
    except Exception as exc:
        report_store_error(exc)
        return False


async def run_standalone(scenario_id, run_fn, task_start_fn=None):
    """Own a single-run batch around an already-evaluated live result.

    `run_fn` must be the shared runner (or a test stub), not this wrapper.
    """
    scenario = get_scenario(scenario_id)
    batch_id = try_start_batch("single", scenario, requested=1)
    window_start = _now()
    try:
        result = await run_fn(scenario_id)
    except Exception as exc:
        if batch_id is not None:
            try_finish_batch(batch_id, "aborted", str(exc))
        raise
    window_end = _now()
    task_start = task_start_fn() if task_start_fn is not None else window_start
    if batch_id is not None:
        try_record_result(
            batch_id,
            1,
            result["verdict"],
            result["message"],
            task_start=task_start or "",
            window_start=window_start,
            window_end=window_end,
        )
        try_finish_batch(batch_id, "completed")
    return result


def fetch_batches(db_path=None):
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM run_batches ORDER BY started_at, id"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def fetch_results(batch_id=None, db_path=None):
    conn = connect(db_path)
    try:
        if batch_id is None:
            rows = conn.execute(
                "SELECT * FROM run_results ORDER BY id"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM run_results WHERE batch_id = ? ORDER BY replay_index",
                (batch_id,),
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
