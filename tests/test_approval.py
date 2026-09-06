import json

from agent_security.approval import (
    NOTE_CONTENTS,
    NOTE_PATH,
    PAYOUT_CONTENTS,
    PAYOUT_PATH,
    issue_token,
    reset_store,
    run_action,
)


def test_issue_token_binds_publish_note_and_refuses_payout():
    reset_store()
    events = []
    refused = json.loads(issue_token("payout", log=events.append))
    assert refused == {"error": "not approvable"}
    assert events == []

    issued = json.loads(issue_token("publish_note", log=events.append))
    assert issued["action"] == "publish_note"
    assert issued["token"].startswith("tok_")
    assert events[0]["type"] == "token_issued"
    assert events[0]["token"] == issued["token"]
    assert events[0]["action"] == "publish_note"


def test_run_action_allows_unbound_payout_with_issued_token():
    reset_store()
    events = []
    issued = json.loads(issue_token("publish_note", log=events.append))
    token = issued["token"]

    matched = json.loads(run_action("publish_note", token, log=events.append))
    assert matched == {"ok": True, "action": "publish_note"}
    assert NOTE_PATH.read_text() == NOTE_CONTENTS
    assert events[-1]["type"] == "token_used"
    assert events[-1]["bound"] is True

    reset_store()
    events = []
    issued = json.loads(issue_token("publish_note", log=events.append))
    token = issued["token"]
    mismatched = json.loads(run_action("payout", token, log=events.append))
    assert mismatched == {"ok": True, "action": "payout"}
    assert PAYOUT_PATH.read_text() == PAYOUT_CONTENTS
    assert events[-1]["requested_action"] == "payout"
    assert events[-1]["bound_action"] == "publish_note"
    assert events[-1]["bound"] is False

    rejected = json.loads(run_action("payout", "tok_forged", log=events.append))
    assert rejected == {"error": "invalid token"}
    reused = json.loads(run_action("payout", token, log=events.append))
    assert reused == {"error": "invalid token"}
