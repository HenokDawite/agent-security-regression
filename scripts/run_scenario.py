import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_security.runner import run_scenario

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/run_scenario.py scenario1|scenario2|scenario3|scenario4|scenario4b|scenario5|scenario6|scenario7|scenario8|scenario9")
        raise SystemExit(2)
    result = asyncio.run(run_scenario(sys.argv[1]))
    print(result["message"])
