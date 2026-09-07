import json
from datetime import datetime

from agent_security.evaluators import PASS, evaluate
from agent_security.paths import LOG_DIR, REPLAY_LOG, TRACE_LOG
from agent_security.reset import ResetError, reset_scenario
from agent_security.runner import get_scenario, run_scenario
from agent_security.store import try_finish_batch, try_record_result, try_start_batch


class ReplayError(Exception):
    pass


class ReplayAbort(ReplayError):
    pass


def last_task_start(prompt):
    timestamp = ""
    if not TRACE_LOG.exists():
        return timestamp
    for line in TRACE_LOG.read_text().splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("type") == "task_start" and event.get("prompt") == prompt:
            timestamp = event.get("timestamp", "")
    return timestamp


def summarize(scenario_id, runs):
    n = len(runs)
    failed = sum(1 for run in runs if run["verdict"] == "FAIL")
    blocked = n - failed
    print(f"{scenario_id}  N={n}")
    for run in runs:
        print(
            f"  run {run['run']}  {run['message']}   "
            f"task_start={run['task_start']}"
        )
    print(f"exploit succeeded: {failed}/{n}")
    print(f"blocked: {blocked}/{n}")
    return {
        "scenario": scenario_id,
        "n": n,
        "fail": failed,
        "pass": blocked,
        "runs": runs,
        "aborted": False,
    }


def print_aborted(scenario_id, requested, runs, reason):
    completed = len(runs)
    print(f"{scenario_id}  ABORTED after {completed}/{requested} runs")
    for run in runs:
        print(
            f"  run {run['run']}  {run['message']}   "
            f"task_start={run['task_start']}"
        )
    if completed:
        failed = sum(1 for run in runs if run["verdict"] == "FAIL")
        print(f"completed exploit succeeded: {failed}/{completed}")
        print(f"completed blocked: {completed - failed}/{completed}")
    print(reason)
    _record({
        "type": "batch_aborted",
        "scenario": scenario_id,
        "completed": completed,
        "requested": requested,
        "reason": str(reason),
    })


def report_cleanup_failure(scenario_id, exc):
    print(f"CLEANUP FAILED: {exc}")
    print("ERROR: sandbox may be dirty.")
    _record({
        "type": "cleanup_failed",
        "scenario": scenario_id,
        "error": str(exc),
    })


def _record(record):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(REPLAY_LOG, "a") as handle:
        handle.write(json.dumps(record) + "\n")


def _final_reset(scenario_id):
    try:
        reset_scenario(scenario_id)
    except Exception as exc:
        report_cleanup_failure(scenario_id, exc)
        return exc
    return None


async def replay_scenario(scenario_id, n, run_fn=None):
    if n < 1:
        raise ReplayAbort("N must be at least 1")
    if run_fn is None:
        run_fn = run_scenario
    scenario = get_scenario(scenario_id)
    runs = []
    result = None
    main_error = None
    terminal = None
    abort_reason = None
    batch_id = try_start_batch("replay", scenario, requested=n)
    try:
        for i in range(1, n + 1):
            try:
                reset_scenario(scenario_id)
            except ResetError as exc:
                raise ReplayAbort(
                    f"ABORT: reset failed on run {i}; "
                    f"ABORTED after {len(runs)}/{n} runs. {exc}"
                ) from exc

            pre = evaluate(scenario)
            if pre["message"] != PASS:
                raise ReplayAbort(
                    f"ABORT: pre-check not PASS on run {i}; "
                    f"ABORTED after {len(runs)}/{n} runs. {pre['message']}"
                )

            window_start = datetime.utcnow().isoformat()
            result_run = await run_fn(scenario_id)
            window_end = datetime.utcnow().isoformat()
            record = {
                "scenario": scenario_id,
                "run": i,
                "pre_check": pre["message"],
                "verdict": result_run["verdict"],
                "message": result_run["message"],
                "task_start": last_task_start(scenario.prompt),
                "window_start": window_start,
                "window_end": window_end,
            }
            runs.append(record)
            _record(record)
            if batch_id is not None:
                try_record_result(
                    batch_id,
                    i,
                    record["verdict"],
                    record["message"],
                    pre_check=record["pre_check"],
                    task_start=record["task_start"],
                    window_start=record["window_start"],
                    window_end=record["window_end"],
                )
        result = summarize(scenario_id, runs)
        terminal = "completed"
    except ReplayAbort as exc:
        main_error = exc
        terminal = "aborted"
        abort_reason = str(exc)
        print_aborted(scenario_id, n, runs, exc)
    except Exception as exc:
        main_error = exc
        terminal = "aborted"
        abort_reason = str(exc)
    finally:
        cleanup_error = _final_reset(scenario_id)

    if cleanup_error is not None:
        terminal = "cleanup_failed"
        abort_reason = str(cleanup_error)
    if batch_id is not None and terminal is not None:
        try_finish_batch(batch_id, terminal, abort_reason)

    if result is not None and cleanup_error is None:
        return result
    if result is not None and cleanup_error is not None:
        raise ReplayError(
            f"Batch completed ({result['fail']}/{result['n']} exploit succeeded) "
            f"but CLEANUP FAILED: {cleanup_error}\n"
            f"ERROR: sandbox may be dirty."
        ) from cleanup_error
    if main_error is not None and cleanup_error is not None:
        raise ReplayError(
            f"{main_error}\n"
            f"CLEANUP ALSO FAILED: {cleanup_error}\n"
            f"ERROR: sandbox may be dirty."
        ) from main_error
    if cleanup_error is not None:
        raise ReplayError(
            f"CLEANUP FAILED: {cleanup_error}\n"
            f"ERROR: sandbox may be dirty."
        ) from cleanup_error
    raise main_error
