import pytest

from agent_security.evaluators import PASS, evaluate
from agent_security.scenarios import SCENARIOS


@pytest.mark.parametrize("scenario_id", list(SCENARIOS))
def test_clean_sandbox_evaluates_pass(scenario_id):
    result = evaluate(SCENARIOS[scenario_id])
    assert result["scenario"] == scenario_id
    assert result["verdict"] == "PASS"
    assert result["message"] == PASS
