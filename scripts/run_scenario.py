import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_security.replay import last_task_start
from agent_security.runner import get_scenario, run_scenario
from agent_security.store import run_standalone

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/run_scenario.py scenario1|scenario2|scenario3|scenario4|scenario4b|scenario5|scenario6|scenario7|scenario8|scenario9|scenario10")
        raise SystemExit(2)
    scenario = get_scenario(sys.argv[1])
    result = asyncio.run(run_standalone(
        sys.argv[1],
        run_scenario,
        task_start_fn=lambda: last_task_start(scenario.prompt),
    ))
    print(result["message"])
