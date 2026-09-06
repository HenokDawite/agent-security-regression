import hashlib
from pathlib import Path

from agent_security.evaluators import (
    _is_read_tool,
    _read_paths,
    _resolve_sandbox_path,
)


def file_identity(path: Path):
    return {
        "inode": path.stat().st_ino,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def watch_path(toctou):
    return _resolve_sandbox_path(toctou["watch_path"])


def read_includes_watch(tool, tool_input, toctou):
    if not _is_read_tool(tool):
        return False
    watched = watch_path(toctou)
    return any(_resolve_sandbox_path(raw) == watched for raw in _read_paths(tool_input))


def apply_swap(toctou):
    path = watch_path(toctou)
    old = file_identity(path)
    path.unlink()
    path.write_text(toctou["replace_with"])
    new = file_identity(path)
    return old, new


def after_tool(toctou, tool, tool_input, state, log):
    if not toctou or not read_includes_watch(tool, tool_input, toctou):
        return
    path = watch_path(toctou)
    lexical = toctou["watch_path"]
    if not state.get("swapped"):
        checked = file_identity(path)
        log({
            "type": "object_check",
            "path": lexical,
            "inode": checked["inode"],
            "sha256": checked["sha256"],
        })
        old, new = apply_swap(toctou)
        log({
            "type": "toctou_swap",
            "path": lexical,
            "old_inode": old["inode"],
            "new_inode": new["inode"],
            "old_sha256": old["sha256"],
            "new_sha256": new["sha256"],
        })
        state["swapped"] = True
        return
    used = file_identity(path)
    log({
        "type": "object_use",
        "path": lexical,
        "inode": used["inode"],
        "sha256": used["sha256"],
    })
