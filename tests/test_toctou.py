import hashlib

from agent_security.paths import REPO_ROOT
from agent_security.scenarios import SCENARIOS
from agent_security.toctou import after_tool


def test_toctou_hook_swaps_after_check_read():
    scenario = SCENARIOS["scenario8"]
    path = REPO_ROOT / "sandbox/allowed/package.txt"
    original = scenario["checked_original"]
    assert path.read_text() == original
    before = path.stat().st_ino
    before_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    events = []
    state = {"swapped": False}

    after_tool(
        scenario["toctou"],
        "list_directory",
        {"path": "allowed"},
        state,
        events.append,
    )
    assert state["swapped"] is False
    assert path.read_text() == original
    assert events == []

    after_tool(
        scenario["toctou"],
        "read_text_file",
        {"path": "allowed/package.txt"},
        state,
        events.append,
    )

    assert state["swapped"] is True
    assert path.read_text() == scenario["toctou"]["replace_with"]
    after_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    assert after_hash != before_hash
    assert [event["type"] for event in events] == ["object_check", "toctou_swap"]
    assert events[0]["inode"] == before
    assert events[0]["sha256"] == before_hash
    assert events[1]["old_inode"] == before
    assert events[1]["new_inode"] == path.stat().st_ino
    assert events[1]["old_sha256"] == before_hash
    assert events[1]["new_sha256"] == after_hash

    after_tool(
        scenario["toctou"],
        "read_text_file",
        {"path": "allowed/package.txt"},
        state,
        events.append,
    )
    assert events[-1]["type"] == "object_use"
    assert events[-1]["inode"] == path.stat().st_ino
    assert events[-1]["sha256"] == after_hash
    assert path.read_text() == scenario["toctou"]["replace_with"]
