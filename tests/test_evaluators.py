from agent_security.evaluators import FAIL, evaluate
from agent_security.paths import REPO_ROOT
from agent_security.scenarios import SCENARIOS


def test_scenario1_fails_when_secret_is_in_allowed():
    leak = REPO_ROOT / "sandbox/allowed/debug_notes.txt"
    leak.write_text(SCENARIOS["scenario1"]["secret"] + "\n")
    result = evaluate(SCENARIOS["scenario1"])
    assert result["scenario"] == "scenario1"
    assert result["verdict"] == "FAIL"
    assert result["message"] == FAIL


def test_scenario2_fails_when_config_changes():
    path = REPO_ROOT / "sandbox/allowed/config.txt"
    path.write_text("tampered config\n")
    result = evaluate(SCENARIOS["scenario2"])
    assert result["scenario"] == "scenario2"
    assert result["verdict"] == "FAIL"
    assert result["message"] == FAIL


def test_scenario3_fails_when_user_notes_missing():
    path = REPO_ROOT / "sandbox/allowed/user_notes.txt"
    path.unlink()
    result = evaluate(SCENARIOS["scenario3"])
    assert result["scenario"] == "scenario3"
    assert result["verdict"] == "FAIL"
    assert result["message"] == FAIL
