import asyncio
from types import SimpleNamespace

from agent_security.resolve_guard import (
    DENIED_MESSAGE,
    execute_tool,
    resolve_denied_read,
)
from agent_security.scenarios import SCENARIOS
from agent_security.schema import ResolveGuardConfig


S5_GUARD = SCENARIOS["scenario5"].resolve_guard


class FakeSession:
    def __init__(self):
        self.calls = []

    async def call_tool(self, name, tool_input):
        self.calls.append((name, tool_input))
        return SimpleNamespace(content="ok")


def test_denied_symlink_read_does_not_call_tool():
    session = FakeSession()
    events = []
    result = asyncio.run(execute_tool(
        session,
        "read_text_file",
        {"path": "allowed/inventory_note.txt"},
        S5_GUARD,
        log=events.append,
    ))
    assert session.calls == []
    assert result == DENIED_MESSAGE
    assert events[0]["type"] == "path_denied"
    assert events[0]["path"] == "allowed/inventory_note.txt"
    assert events[0]["reason"] == "resolved_under_denied_root"
    assert events[0]["resolved"].endswith("/sandbox/forbidden/inventory.txt")


def test_allowed_read_is_forwarded():
    session = FakeSession()
    events = []
    result = asyncio.run(execute_tool(
        session,
        "read_text_file",
        {"path": "allowed/config.txt"},
        S5_GUARD,
        log=events.append,
    ))
    assert session.calls == [
        ("read_text_file", {"path": "allowed/config.txt"}),
    ]
    assert result == "ok"
    assert events == []


def test_no_guard_forwards_symlink_read():
    session = FakeSession()
    events = []
    result = asyncio.run(execute_tool(
        session,
        "read_text_file",
        {"path": "allowed/inventory_note.txt"},
        None,
        log=events.append,
    ))
    assert session.calls == [
        ("read_text_file", {"path": "allowed/inventory_note.txt"}),
    ]
    assert result == "ok"
    assert events == []


def test_empty_denied_roots_forwards_symlink_read():
    session = FakeSession()
    result = asyncio.run(execute_tool(
        session,
        "read_text_file",
        {"path": "allowed/inventory_note.txt"},
        ResolveGuardConfig(denied_read_roots=[]),
        log=lambda event: None,
    ))
    assert session.calls == [
        ("read_text_file", {"path": "allowed/inventory_note.txt"}),
    ]
    assert result == "ok"


def test_read_multiple_files_denies_whole_call_if_any_path_hits_root():
    session = FakeSession()
    events = []
    result = asyncio.run(execute_tool(
        session,
        "read_multiple_files",
        {"paths": ["allowed/config.txt", "allowed/inventory_note.txt"]},
        S5_GUARD,
        log=events.append,
    ))
    assert session.calls == []
    assert result == DENIED_MESSAGE
    assert events[0]["type"] == "path_denied"
    assert events[0]["path"] == "allowed/inventory_note.txt"


def test_write_and_list_are_not_denied():
    assert resolve_denied_read(
        "write_file",
        {"path": "allowed/inventory_note.txt", "content": "x"},
        S5_GUARD,
    ) is None
    assert resolve_denied_read(
        "list_directory",
        {"path": "forbidden"},
        S5_GUARD,
    ) is None
    assert resolve_denied_read(
        "search_files",
        {"path": "forbidden", "pattern": "*"},
        S5_GUARD,
    ) is None
    assert resolve_denied_read(
        "get_file_info",
        {"path": "allowed/inventory_note.txt"},
        S5_GUARD,
    ) is None
