import json
import shutil
from datetime import datetime

from agent_security.paths import LOG_DIR, REPO_ROOT, SANDBOX_DIR, TRACE_LOG
from agent_security.runner import get_scenario


class ResetError(Exception):
    pass


def reset_scenario(scenario_id):
    scenario = get_scenario(scenario_id)
    reset = scenario.get("reset")
    if not reset:
        raise ResetError(f"No reset config for {scenario_id}")

    try:
        for rel in reset.get("clean_dirs", []):
            path = REPO_ROOT / rel
            if path.is_dir():
                shutil.rmtree(path)
            elif path.is_file():
                path.unlink()
            path.mkdir(parents=True, exist_ok=True)

        for rel, contents in reset.get("restore_files", {}).items():
            path = REPO_ROOT / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents)

        for rel, target in reset.get("restore_symlinks", {}).items():
            path = REPO_ROOT / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.is_symlink() or path.exists():
                path.unlink()
            path.symlink_to(target)

        for rel in reset.get("remove_files", []):
            path = REPO_ROOT / rel
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)

        if reset.get("remove_secret_from_allowed"):
            _remove_secret_from_allowed(scenario)

        if reset.get("remove_relocated_notes"):
            _remove_relocated_notes(scenario)
    except Exception as exc:
        raise ResetError(f"reset failed for {scenario_id}: {exc}") from exc

    _log_reset(scenario_id)


def _log_reset(scenario_id):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    event = {
        "type": "reset",
        "scenario": scenario_id,
        "timestamp": datetime.utcnow().isoformat(),
    }
    with open(TRACE_LOG, "a") as handle:
        handle.write(json.dumps(event) + "\n")


def _remove_secret_from_allowed(scenario):
    secret = scenario["secret"]
    allowed = REPO_ROOT / scenario["search_dir"]
    for path in list(allowed.rglob("*")):
        if not path.is_file():
            continue
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        if secret in text:
            path.unlink()


def _remove_relocated_notes(scenario):
    required = (REPO_ROOT / scenario["path"]).resolve()
    for path in list(SANDBOX_DIR.rglob("*")):
        if not path.is_file():
            continue
        if path.resolve() == required:
            continue
        if path.name.startswith("user_notes"):
            path.unlink()
    archive = SANDBOX_DIR / "allowed" / "archive"
    if archive.is_dir():
        shutil.rmtree(archive)
