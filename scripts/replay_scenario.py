import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_security.cli import main as cli_main

USAGE = (
    "Usage: python scripts/replay_scenario.py "
    "scenario1|scenario2|scenario3|scenario4|scenario4b|scenario5|"
    "scenario6|scenario7|scenario8|scenario9|scenario10 N"
)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print(USAGE)
        return 2
    try:
        int(argv[1])
    except ValueError:
        print("N must be an integer")
        return 2
    return cli_main(["replay", argv[0], "--runs", argv[1]])


if __name__ == "__main__":
    raise SystemExit(main())
