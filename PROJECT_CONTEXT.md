# Project: Agent Security Regression Framework

## One-sentence description
A CI-integrated regression-testing framework that runs reproducible multi-step exploit scenarios against real AI agent tool integrations, deterministically detects unauthorized actions, and continually replays them to verify fixes stay fixed.

## Documentation map
This file is the concise source of truth for purpose, problem, scope, design principles, tech stack, and AI-assistance rules.

- `docs/ROADMAP.md` — phases, completion status, validation gates, next steps
- `docs/SCENARIOS.md` — exploit-family taxonomy, scenario definitions, authorization boundaries, deterministic assertions
- `docs/RESULTS.md` — run results, replay tables, success rates, observations

Read this file first. Then read `docs/ROADMAP.md` for the first incomplete step. Read `docs/SCENARIOS.md` before designing or implementing any scenario. Read `docs/RESULTS.md` before claiming findings or updating rates.

## Why this project exists (context for design decisions)
This is a resume project for new-grad software engineering applications. The scope has been deliberately narrowed multiple times to prioritize:
1. **Finishability** in a 2-3 week sprint alongside a full course load
2. **Defensibility** — every design choice must be explainable in an interview, not just functional
3. **A concrete, quantifiable result** — not just "a tool exists," but specific findings with numbers

The author must be able to explain and defend every part of this project's design in an interview. AI assistance (Cursor's sidebar) should be used for implementation speed on well-specified pieces — boilerplate, debugging, fixing library/API errors — but NOT for inventing exploit scenario design or deciding what counts as a security failure. Those decisions are made deliberately; treat this file plus `docs/SCENARIOS.md` as the source of truth for "why," not just "what."

## Problem being solved
MCP (Model Context Protocol) lets AI agents call tools that access real systems — filesystems, databases, APIs, GitHub, Slack. This creates real attack surface: untrusted content (a file, an issue, a message) can contain instructions that manipulate the agent into taking unauthorized actions through a *later* tool call. This is sometimes called a "confused deputy" or cross-tool injection attack, and it's distinct from single-turn prompt injection.

OWASP's Agentic AI security guidance and MCP's own authorization/security documentation both treat this class of risk (indirect prompt injection leading to tool abuse, privilege escalation, data exfiltration) as a core, current problem — this is a real problem, not an invented student exercise.

## Explicit scope boundaries (what this project is NOT)
Do not suggest or add these unless a stated requirement changes:
- **No LangGraph or agent orchestration framework** — the pipeline is linear (load scenario → run agent → capture trace → evaluate → replay), no branching/cyclical control flow needed
- **No RAG or vector database** — no large corpus to search semantically; the exploit case library is a short, explicit list
- **No Kubernetes** — single sandboxed target at a time, not concurrent multi-tenant scanning
- **No Redis/Celery** — no distributed job queue needed; scenarios run sequentially
- **No FastAPI or web API** — this is a CLI tool invoked locally and in CI, no remote caller exists
- **No LLM-as-judge for detecting exploit success** — see "deterministic evaluator" principle below

These are cut deliberately to keep the project's engineering depth focused on the actual problem (tool-call tracing, deterministic security assertions, reproducibility) rather than accumulating technology keywords.

## Core design principle: deterministic evaluation
LLMs generate agent behavior; only deterministic code determines whether an exploit succeeded. Never ask an LLM "did this violate security?" — instead, instrument the environment so success/failure is a plain assertion. Examples:
```python
assert fake_secret not in outbound_payloads
assert write.target_repo in allowed_repositories
assert resolved_path.is_relative_to(sandbox_root)
assert no_forbidden_delete_occurred
```
If a candidate exploit scenario can't be reduced to a clean assertion like this, it's not ready — rework it or drop it.

## CI design: framework gate vs live replay
Deterministic pytest validates the **framework**: scenario definitions, evaluators, reset behavior, replay orchestration, clean-baseline guarantees, and failure handling. The required GitHub Actions gate runs that offline suite on pushes and pull requests (`.github/workflows/tests.yml`). It uses no GitHub secrets and no live model calls. The pytest step sets a dummy `ANTHROPIC_API_KEY` only so `Anthropic()` can be constructed at import time; that value is never used for API requests.

Live Anthropic/MCP replay validates **actual model behavior**. It is not part of the required PR gate. Agent behavior is stochastic; existing scenarios intentionally reproduce failures at nonzero rates; live runs cost money and need secrets; and a single model outcome would be a flaky binary gate.

Treat live replay as a separate experimental/regression layer. A later step may expose it through a manual or scheduled workflow and report repeated-run rates rather than one PASS/FAIL, especially after mitigations. One live PASS is not proof a vulnerability is fixed.

## Positioning / how to describe this project (for README, resume, interviews)
Correct framing: "A reproducible regression-testing harness for multi-step agent security failures, designed to run alongside normal CI tests."
Avoid claiming: "no one else does this" — established tools (Snyk's agent-scan, Cisco's MCP Scanner, Invariant's MCP-Scan/toxic-flow-analysis) already do related static/dynamic scanning as of 2026. This project's distinct angle is the reproducible regression/replay-to-verify-fix loop and cross-tool (not single-call) exploit focus, not a claim of being first.

## Tech stack (Phase 1)
- Python (core harness/orchestration, plain — no framework)
- MCP Python SDK (`mcp` package) for talking to MCP servers
- Anthropic API (`anthropic` package) as the agent being tested / attacked
- `python-dotenv` for API key loading
- Docker (optional isolation for live Anthropic + MCP runs; offline pytest/CI stay on the host)
- pytest (deterministic evaluator, reset, replay-wiring, and clean-baseline regression tests in `tests/`)
- SQLite or JSONL for run/trace/result storage (currently JSONL: `logs/trace_log.jsonl`, `logs/replay_log.jsonl`)
- GitHub Actions (required offline pytest gate on push/PR; live replay is not the PR gate)
- Click or Typer (planned, for the CLI, once the harness is generalized past hand-coded scripts)

## Ground rule for AI assistance on this project
When asked to implement something, implement exactly the design given — don't invent new exploit scenarios, new assertion logic, or add libraries/frameworks not listed in this document without the author explicitly deciding to add them first.

## How Cursor should help

When continuing this project:

1. Read this entire file before suggesting work.
2. Read `docs/ROADMAP.md` and identify the first step whose status is not COMPLETE.
3. Work only on that step unless explicitly told otherwise.
4. Do not invent new frameworks or expand scope.
5. For a new exploit scenario, read `docs/SCENARIOS.md` first and do not implement anything until:
   - the attacker input is defined
   - the authorization boundary is defined
   - the deterministic failure assertion is defined
   - the underlying failure mechanism is shown to be distinct from Family A (not just another confidentiality / integrity / availability consequence of untrusted-file injection)
6. Explain why a change is needed before implementing it.
7. After a milestone works, update the matching file — `docs/ROADMAP.md` for status/next step, `docs/SCENARIOS.md` for a new family or scenario definition, `docs/RESULTS.md` for runs and rates. Do not grow this file with experimental results.

After every completed milestone, keep these docs accurate. Remove or revise stale statements that contradict the new state. Do not change project scope or invent new milestones.
