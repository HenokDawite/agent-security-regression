import pytest
from pydantic import ValidationError

from agent_security.evaluators import CHECKS
from agent_security.schema import (
    EVALUATOR_NAMES,
    Scenario,
    load_scenarios,
    scenario_with_evaluator,
)
from agent_security.scenarios import SCENARIOS


def _valid(**overrides):
    data = {
        "id": "scenarioX",
        "prompt": "do the thing",
        "evaluator": "token_bound_to_execute_action",
        "reset": {},
    }
    data.update(overrides)
    return data


def test_evaluator_names_match_checks():
    assert set(EVALUATOR_NAMES) == set(CHECKS)


def test_existing_literals_validate():
    assert set(SCENARIOS) == {
        "scenario1",
        "scenario2",
        "scenario3",
        "scenario4",
        "scenario4b",
        "scenario5",
        "scenario6",
        "scenario7",
        "scenario8",
        "scenario9",
        "scenario10",
    }
    for key, scenario in SCENARIOS.items():
        assert scenario.id == key


def test_missing_required_base_fields():
    with pytest.raises(ValidationError):
        Scenario.model_validate({"prompt": "p", "evaluator": "path_is_file", "reset": {}, "path": "x"})
    with pytest.raises(ValidationError):
        Scenario.model_validate({"id": "scenarioX", "evaluator": "token_bound_to_execute_action", "reset": {}})
    with pytest.raises(ValidationError):
        Scenario.model_validate({"id": "scenarioX", "prompt": "p", "evaluator": "token_bound_to_execute_action"})


def test_unknown_field_is_rejected():
    with pytest.raises(ValidationError):
        Scenario.model_validate(_valid(evalutor="token_bound_to_execute_action"))


def test_strict_types_reject_coercion():
    with pytest.raises(ValidationError):
        Scenario.model_validate(_valid(approval_tools="yes"))
    with pytest.raises(ValidationError):
        Scenario.model_validate(_valid(approval_tools=1))
    with pytest.raises(ValidationError):
        Scenario.model_validate(_valid(reset={"remove_secret_from_allowed": "true"}))


def test_unknown_evaluator_name():
    with pytest.raises(ValidationError):
        Scenario.model_validate(_valid(evaluator="resolved_read_not_exectued_under"))


def test_evaluator_required_fields():
    with pytest.raises(ValidationError, match="requires original"):
        Scenario.model_validate(_valid(
            evaluator="file_unchanged",
            path="sandbox/allowed/config.txt",
        ))
    with pytest.raises(ValidationError, match="requires secret"):
        Scenario.model_validate(_valid(evaluator="secret_not_in_allowed"))
    Scenario.model_validate(_valid(
        evaluator="file_unchanged",
        path="sandbox/allowed/config.txt",
        original="This is a normal config file.\n",
    ))


def test_registry_key_must_match_id():
    raw = {"scenario1": _valid(id="scenario2")}
    with pytest.raises(ValueError, match="does not match id"):
        load_scenarios(raw)


def test_reset_cross_field_requires_parent_fields():
    with pytest.raises(ValidationError, match="remove_secret_from_allowed"):
        Scenario.model_validate(_valid(
            reset={"remove_secret_from_allowed": True},
        ))
    with pytest.raises(ValidationError, match="remove_relocated_notes"):
        Scenario.model_validate(_valid(
            reset={"remove_relocated_notes": True},
        ))
    Scenario.model_validate(_valid(
        evaluator="secret_not_in_allowed",
        secret="SECRET",
        search_dir="sandbox/allowed",
        reset={"remove_secret_from_allowed": True},
    ))
    Scenario.model_validate(_valid(
        evaluator="path_is_file",
        path="sandbox/allowed/user_notes.txt",
        reset={"remove_relocated_notes": True},
    ))


def test_malformed_nested_configs():
    with pytest.raises(ValidationError):
        Scenario.model_validate(_valid(
            resolve_guard={"denied_read_roots": "forbidden"},
        ))
    with pytest.raises(ValidationError):
        Scenario.model_validate(_valid(
            resolve_guard={"denied_read_roots": ["forbidden"], "extra": True},
        ))
    with pytest.raises(ValidationError):
        Scenario.model_validate(_valid(
            resolve_guard={"denied_read_roots": [""]},
        ))
    with pytest.raises(ValidationError):
        Scenario.model_validate(_valid(
            toctou={"watch_path": "allowed/package.txt"},
        ))
    with pytest.raises(ValidationError):
        Scenario.model_validate(_valid(
            reset={"restore_files": {1: "contents"}},
        ))


def test_historical_scenario5_override_is_revalidated():
    historical = scenario_with_evaluator(
        SCENARIOS["scenario5"], "resolved_read_not_under"
    )
    assert historical.evaluator == "resolved_read_not_under"
    assert historical.forbidden_dir == "forbidden"
    assert historical.prompt == SCENARIOS["scenario5"].prompt
    with pytest.raises(ValidationError):
        scenario_with_evaluator(SCENARIOS["scenario5"], "not_a_real_check")
