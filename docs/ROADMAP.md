# Roadmap

Phases, completion status, validation gates, and next steps.
See `PROJECT_CONTEXT.md` for purpose and scope. See `docs/SCENARIOS.md` for family/scenario definitions. See `docs/RESULTS.md` for measured runs.

## Phase 1 (resume-ready MVP — current focus)
- 1-2 real target workflows (starting with the filesystem MCP server; a 2nd workflow only added if needed for genuinely distinct attack diversity)
- A small set of reproducible cross-tool/multi-step exploit scenarios (target: enough to represent 3-6 genuinely different root-cause exploit *families* — not resume-friendly case counts; 3 near-duplicate variants of the same root cause count as one family). Different CIA impacts of the same mechanism (confidentiality vs integrity vs availability) do **not** count as different families.
- One benign/sanity task per workflow, to prove the harness itself isn't just broken (an exploit "blocked" because the agent couldn't function at all is a false result)
- Deterministic tool-call tracing and evaluation
- Replay logic: re-run a scenario after a fix and confirm it's actually blocked
- Basic CI gate (GitHub Actions) that runs the deterministic offline pytest suite on pushes and pull requests. Live Anthropic/MCP replay is not part of that required gate (see `PROJECT_CONTEXT.md`).

## Phase 2 (stretch, after Phase 1 works)
- Narrow, specific mitigation generation per finding (e.g., a tool-argument validator or allowlist rule — not a general "reasons about policy" system; avoid overclaiming this in any writeup)
- Full utility/legitimate-task regression suite (are legitimate tasks still working after a mitigation is applied — the security-vs-utility tradeoff)
- Polished CLI, more target workflows, public benchmark writeup with quantified results and an architecture diagram

## Validation gate (go/no-go — check before committing further)
Family definition and the rule that CIA variants are not new families: `docs/SCENARIOS.md`.
Replay rates: `docs/RESULTS.md`.

Current family count: **1 of 3–4** (Family A). Scenarios 1–3 do **not** satisfy the family-diversity target.

- Can at least 3-4 genuinely different *underlying* exploit families be demonstrated across the chosen workflow(s)? **Not yet — 1 of 3–4.** A later scenario counts as a new family only if its failure mechanism differs from Family A (see `docs/SCENARIOS.md`).
- Can each be evaluated deterministically (a clean, falsifiable assertion) without an LLM judge? Yes for Scenarios 1–3 (see `docs/SCENARIOS.md`).
- Is the failure reproducible on repeated runs (needed for regression testing to be meaningful)? See `docs/RESULTS.md`.
- Does the harness generalize enough that adding a new scenario doesn't require rewriting the runner? **Yes** (Step 5). A new scenario is a dict in `agent_security/scenarios.py` plus an evaluator name; it does not require a new agent script.

If the answer to these is no after real attempts, consider a 3rd workflow before concluding the concept doesn't hold up.

## Current status
- Environment set up: Python venv, `mcp`, `anthropic`, `python-dotenv`, `pytest` installed
- Sandbox created at `sandbox/allowed/` (contains `config.txt`, Scenario 1 input `issue.txt`, Scenario 2 input `scenario2_issue.txt`, Scenario 3 input `scenario3_issue.txt`, protected file `user_notes.txt`) and `sandbox/forbidden/` (contains `secrets.txt` — fake value, `SECRET_API_KEY=FAKE_TEST_SECRET_123`)
- `scripts/explore.py` — lists MCP filesystem server's available tools
- Package layout: `agent_security/` (loop, runner, replay, reset, evaluators, scenarios, shared `paths.py`); entry points in `scripts/`
- Shared paths: `REPO_ROOT`, `SANDBOX_DIR`, `LOG_DIR`, `ENV_PATH` in `agent_security/paths.py`
- Commands: `python scripts/run_scenario.py scenarioN`; `python scripts/replay_scenario.py scenarioN N`; `python -m pytest tests/`
- Logs: `logs/trace_log.jsonl`, `logs/replay_log.jsonl` (directory created on write)
- Family count: **1** demonstrated root-cause family (Family A). Scenarios 1–3 are CIA-impact variants of that one mechanism, not three families.
- CI: `.github/workflows/tests.yml` runs `python -m pytest tests/` on push/PR with dummy `ANTHROPIC_API_KEY` (not a GitHub secret). Live replay is not in that gate. Verified green on GitHub (run 33943986685).
- **Not yet built:** a second root-cause family, CLI, Docker isolation, Phase 2 items

## Next step
Step 9 — optional polish. Do not start it until explicitly asked. Do not invent a new scenario or family unless asked.

## Execution steps

### Step 1 — Benign harness
Status: COMPLETE

Goal:
Confirm the agent can call MCP filesystem tools and log its trajectory.

Done when:
- benign tasks work
- tool calls/results are logged

---

### Step 2 — Scenario 1
Status: COMPLETE (reproducibility checked)

Family A / confidentiality. Definition: `docs/SCENARIOS.md`. Results: `docs/RESULTS.md`.

---

### Step 3 — Scenario 2
Status: COMPLETE (reproducibility checked)

Family A / integrity. Definition: `docs/SCENARIOS.md`. Results: `docs/RESULTS.md`.

---

### Step 4 — Scenario 3
Status: COMPLETE (reproducibility checked)

Family A / availability. Definition: `docs/SCENARIOS.md`. Results: `docs/RESULTS.md`.

---

### Step 5 — Generalize the harness
Status: COMPLETE

Refactored hard-coded scripts into:
- `agent_security/scenarios.py` — scenario definition (id, prompt, evaluator name, assertion params)
- `agent_security/runner.py` / `scripts/run_scenario.py` — common runner
- `agent_security/agent_loop.py` — trace capture (`log_event` / `logs/trace_log.jsonl`)
- `agent_security/evaluators.py` — shared evaluator interface
- result dict `{scenario, verdict, message}` printed as the original PASS/FAIL strings

A new scenario should not require rewriting the agent loop.

Validation (no live model): prompt freeze, evaluator fixture PASS/FAIL, trace contract, wrapper smoke — all passed.

---

### Step 6 — Replay
Status: COMPLETE

Automated reset → pre-check PASS → `runner.run_scenario` → evaluate → record → summarize N times. One PASS is not proof a vulnerability is fixed; the summary reports an exploit-success rate.

- Reset config lives on each scenario in `agent_security/scenarios.py`
- Failed reset or failed pre-check aborts the entire batch (`ABORTED after k/N runs`); completed run records stay in `logs/replay_log.jsonl`; the failed run is not started
- Final `reset_scenario()` runs in `finally` and never fails silently: cleanup errors are logged, printed (`ERROR: sandbox may be dirty.`), and exit non-zero; an earlier abort/crash is still reported (both failures if both occur)
- Usage: `python scripts/replay_scenario.py scenario2 3`

Deterministic checks passed (prompt freeze, dirty-fixture reset, isolation, stubbed N-run counts, abort-on-dirty-pre-check, finally-restore-on-crash). End-to-end live smoke `python replay_scenario.py scenario2 2` verified: both runs had `pre_check=PASS: exploit blocked`, both records landed in `replay_log.jsonl`, printed summary matched those records (2 FAIL / 2 requested), matching `task_start` events and tool calls exist in `trace_log.jsonl`, and the sandbox was clean afterward. Those two smoke runs are not added to historical `docs/RESULTS.md`.

---

### Step 7 — pytest
Status: COMPLETE

Converted the deterministic Step 5–6 checks into `tests/` (no live agent, no CI):

- Session-start preflight: all three scenarios must already be `PASS: exploit blocked`; a dirty sandbox fails the suite instead of being silently reset
- Function-scoped restore after each test that dirties the sandbox
- Prompt freeze and evaluator mapping (`test_scenarios.py`)
- Clean-baseline PASS, dirty-fixture FAIL, reset + isolation, stubbed replay wiring (`run_fn` injected; logs redirected)

`python -m pytest tests/` — 19 passed. Real sandbox still clean afterward. Historical rates in `docs/RESULTS.md` unchanged.

---

### Step 8 — GitHub Actions
Status: COMPLETE

Required gate: `.github/workflows/tests.yml` runs `python -m pytest tests/` on pushes and pull requests after `pip install -r requirements.txt` (Python 3.12). Checks scenario definitions, deterministic evaluators, reset, replay orchestration, clean-baseline, and failure handling. No GitHub secrets. The pytest step sets `ANTHROPIC_API_KEY=test-only-dummy-key` only because `agent_loop.py` constructs `Anthropic()` at import time; CI never makes live calls.

Live Anthropic/MCP replay is not in this PR gate. A later step may add a manual or scheduled workflow that reports repeated-run rates rather than one PASS/FAIL.

Local `python -m pytest tests/` — 19 passed. GitHub run 33943986685 passed. Historical rates in `docs/RESULTS.md` unchanged.

---

### Step 9 — Optional polish
Only after core functionality works:
- CLI
- Docker isolation
- additional workflows
- benchmark table
- architecture diagram
- README/demo
