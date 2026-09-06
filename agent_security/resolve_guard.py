from agent_security.evaluators import (
    _is_read_tool,
    _read_paths,
    _resolve_sandbox_path,
)
from agent_security.paths import SANDBOX_DIR

DENIED_MESSAGE = "Denied: resolved path is outside the authorized tree."


async def execute_tool(session, name, tool_input, resolve_guard, log):
    denied = resolve_denied_read(name, tool_input, resolve_guard)
    if denied:
        log(denied)
        return DENIED_MESSAGE
    result = await session.call_tool(name, tool_input)
    return str(result.content)


def resolve_denied_read(tool, tool_input, resolve_guard):
    if not resolve_guard:
        return None
    roots = resolve_guard.get("denied_read_roots") or []
    if not roots or not _is_read_tool(tool):
        return None
    denied_roots = [(SANDBOX_DIR / root).resolve() for root in roots]
    for raw in _read_paths(tool_input):
        resolved = _resolve_sandbox_path(raw)
        for root in denied_roots:
            if resolved == root or root in resolved.parents:
                return {
                    "type": "path_denied",
                    "path": raw,
                    "resolved": str(resolved),
                    "reason": "resolved_under_denied_root",
                }
    return None
