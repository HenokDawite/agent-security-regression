import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_security.cli import main as cli_main

USAGE = (
    "Usage: python scripts/run_scenario.py "
    "scenario1|scenario2|scenario3|scenario4|scenario4b|scenario5|"
    "scenario6|scenario7|scenario8|scenario9|scenario10"
)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(USAGE)
        return 2
    return cli_main(["run", argv[0]])


if __name__ == "__main__":
    raise SystemExit(main())
