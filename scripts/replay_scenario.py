import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_security.replay import ReplayAbort, ReplayError, replay_scenario

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python scripts/replay_scenario.py scenario1|scenario2|scenario3 N")
        raise SystemExit(2)
    try:
        n = int(sys.argv[2])
    except ValueError:
        print("N must be an integer")
        raise SystemExit(2)
    try:
        asyncio.run(replay_scenario(sys.argv[1], n))
    except ReplayAbort:
        raise SystemExit(1)
    except ReplayError as exc:
        print(exc)
        raise SystemExit(1)
