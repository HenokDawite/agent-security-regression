from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SANDBOX_DIR = REPO_ROOT / "sandbox"
LOG_DIR = REPO_ROOT / "logs"
ENV_PATH = REPO_ROOT / ".env"
TRACE_LOG = LOG_DIR / "trace_log.jsonl"
REPLAY_LOG = LOG_DIR / "replay_log.jsonl"
