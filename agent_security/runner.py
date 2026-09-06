from agent_security.agent_loop import run_agent
from agent_security.evaluators import evaluate
from agent_security.scenarios import SCENARIOS


def get_scenario(scenario_id):
    try:
        return SCENARIOS[scenario_id]
    except KeyError:
        known = ", ".join(sorted(SCENARIOS))
        raise SystemExit(f"Unknown scenario {scenario_id!r}. Expected one of: {known}")


async def run_scenario(scenario_id):
    scenario = get_scenario(scenario_id)
    await run_agent(
        scenario["prompt"],
        toctou=scenario.get("toctou"),
    )
    return evaluate(scenario)
