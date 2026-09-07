import argparse
import asyncio
import sqlite3
import sys

from agent_security.evaluators import evaluate
from agent_security.replay import ReplayAbort, ReplayError, last_task_start, replay_scenario
from agent_security.runner import run_scenario
from agent_security.scenarios import SCENARIOS
from agent_security.store import (
    StoreError,
    fetch_batches,
    fetch_results,
    get_db_path,
    run_standalone,
)


def known_scenario_ids():
    return ", ".join(sorted(SCENARIOS))


def require_scenario(scenario_id):
    if scenario_id in SCENARIOS:
        return True
    print(
        f"Unknown scenario {scenario_id!r}. Expected one of: {known_scenario_ids()}",
        file=sys.stderr,
    )
    return False


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m agent_security",
        description=(
            "Run, replay, evaluate, and summarize agent security scenarios."
        ),
        epilog=f"Scenarios: {known_scenario_ids()}",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="one live scenario run")
    p_run.add_argument("scenario", help="scenario id")

    p_replay = sub.add_parser("replay", help="N live iterations")
    p_replay.add_argument("scenario", help="scenario id")
    p_replay.add_argument(
        "--runs",
        required=True,
        type=int,
        metavar="N",
        help="number of live iterations (at least 1)",
    )

    p_eval = sub.add_parser(
        "evaluate",
        help="deterministic check of current sandbox state",
    )
    p_eval.add_argument("scenario", help="scenario id")

    p_results = sub.add_parser(
        "results",
        help="read-only SQLite experiment history",
    )
    p_results.add_argument(
        "scenario",
        nargs="?",
        default=None,
        help="optional scenario id to filter",
    )
    return parser


def cmd_run(scenario_id):
    scenario = SCENARIOS[scenario_id]
    try:
        result = asyncio.run(
            run_standalone(
                scenario_id,
                run_scenario,
                task_start_fn=lambda: last_task_start(scenario.prompt),
            )
        )
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1
    print(result["message"])
    return 0


def cmd_replay(scenario_id, n):
    try:
        asyncio.run(replay_scenario(scenario_id, n))
    except ReplayAbort:
        return 1
    except ReplayError as exc:
        print(exc)
        return 1
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


def cmd_evaluate(scenario_id):
    result = evaluate(SCENARIOS[scenario_id])
    print(result["message"])
    return 0


def format_batch_line(batch, rows):
    failed = sum(1 for row in rows if row["verdict"] == "FAIL")
    return (
        f"{batch['scenario_id']}  {batch['kind']}  {batch['evaluator']}  "
        f"{batch['mitigation_label']}  {batch['execution_mode']}  "
        f"{batch['status']}  {batch['completed']}/{batch['requested']}  "
        f"exploit succeeded: {failed}/{len(rows)}  {batch['started_at']}"
    )


def cmd_results(scenario_id=None):
    path = get_db_path()
    if not path.exists():
        if scenario_id:
            print(f"No experiment history for {scenario_id}.")
        else:
            print("No experiment history.")
        return 0
    try:
        batches = fetch_batches(readonly=True)
    except (StoreError, sqlite3.Error) as exc:
        print(exc, file=sys.stderr)
        return 1
    if scenario_id:
        batches = [batch for batch in batches if batch["scenario_id"] == scenario_id]
        if not batches:
            print(f"No experiment history for {scenario_id}.")
            return 0
    try:
        for batch in batches:
            rows = fetch_results(batch["id"], readonly=True)
            print(format_batch_line(batch, rows))
    except (StoreError, sqlite3.Error) as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


def main(argv=None):
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code is None else int(exc.code)

    if args.command in ("run", "replay", "evaluate") or (
        args.command == "results" and args.scenario is not None
    ):
        if not require_scenario(args.scenario):
            return 2

    if args.command == "run":
        return cmd_run(args.scenario)
    if args.command == "replay":
        if args.runs < 1:
            print("N must be at least 1", file=sys.stderr)
            return 2
        return cmd_replay(args.scenario, args.runs)
    if args.command == "evaluate":
        return cmd_evaluate(args.scenario)
    if args.command == "results":
        return cmd_results(args.scenario)
    return 2
