# Build phases: what Claude Code builds, in order, and what proves it

One prompt file per phase. Paste a file's contents into Claude Code in plan mode. The tests in `tests/` are the proof. "Tests passing" is the cumulative count when you finish the phase (367 at the end).

| Phase | Prompt file | Creates | Tests that must pass | Tests passing |
|---|---|---|---|---|
| 1 | `prompts/01-foundation.md` | `src/securetriage/config.py`, `src/securetriage/logging_utils.py` | `test_01_config_logging.py` | 9 |
| 2 | `prompts/02-guard.md` | `src/securetriage/guard.py` | `test_02_guard.py` | 32 |
| 3 | `prompts/03-chunking.md` | `src/securetriage/chunking.py` | `test_03_chunking.py` | 55 |
| 4 | `prompts/04-embeddings.md` | `src/securetriage/embeddings.py` | `test_04_embeddings.py` | 63 |
| 5 | `prompts/05-graph.md` | `src/securetriage/graph.py` | `test_05_graph.py` | 77 |
| 6 | `prompts/06-ingest.md` | `src/securetriage/ingest.py` | `test_06_ingest.py` | 83 |
| 7 | `prompts/07-retrieve.md` | `src/securetriage/retrieve.py` | `test_07_retrieve.py` | 90 |
| 8 | `prompts/08-tools.md` | `src/securetriage/tools.py` | `test_08_tools.py` | 101 |
| 9 | `prompts/09-agent.md` | `src/securetriage/llm.py`, `src/securetriage/agent.py` | `test_09_agent.py` | 121 |
| 10 | `prompts/10-budget.md` | `src/securetriage/budget.py` | `test_15_budget.py` | 130 |
| 11 | `prompts/11-evals.md` | `src/securetriage/evals.py` | `test_10_evals.py` | 136 |
| 12 | `prompts/12-cli.md` | `src/securetriage/cli.py`, `src/securetriage/__main__.py` | `test_11_data.py` | 147 |
| 13 | `prompts/13-orchestrate.md` | `src/securetriage/orchestrate.py` | `test_16_orchestrate.py` | 164 |
| 14 | `prompts/14-findings.md` | `src/securetriage/store.py`, `src/securetriage/findings.py`, `src/securetriage/dashboard.py`, `src/securetriage/datapoints_api.py`, (and additions to src/securetriage/tools.py and config.py) | `test_22_datapoints_api.py` | 190 |
| 15 | `prompts/15-review-desk.md` | `src/securetriage/hitl.py`, `src/securetriage/handler.py`, (additions to store.py, config.py, cli.py) | `test_12_handler.py`, `test_19_findings.py`, `test_24_hitl.py` | 278 |
| 16 | `prompts/16-runner-sdk.md` | `src/securetriage/sdk_agent.py`, (additions to cli.py and evals.py) | `test_17_runner.py`, `test_18_sdk_agent.py` | 312 |
| 17 | `prompts/17-analyst.md` | `src/securetriage/analyst.py`, (additions to cli.py and orchestrate.py) | `test_20_findings_agents.py` | 334 |
| 18 | `prompts/18-mcp.md` | `src/securetriage/mcp_server.py` | `test_13_mcp.py` | 336 |
| 19 | `prompts/19-hardening.md` | (additions to graph.py, handler.py, tools.py, cli.py) | `test_21_graph_hardening.py`, `test_14_scripts.py` | 359 |
| 20 | `prompts/20-dashboard-app.md` | `dashboard_app/app.py`, `dashboard_app/data.py`, `dashboard_app/requirements.txt` | `test_23_dashboard_app.py` | 367 |
| 21 | `prompts/21-infra.md` | `infra/template.yaml`, `infra/build.sh`, `infra/iam-dev-policy.json`, `infra/iam-findings-policy.json`, `infra/iam-reviewer-policy.json`, `infra/iam-agent-sdk-policy.json`, `infra/github-oidc-trust.json` | `test_24_hitl.py (the two infrastructure tests)` | 367 |

Phase 00 (`prompts/00-orient.md`) changes nothing; run it first.

**Order matters.** Each phase imports only modules from earlier phases. The reference solution in `answer_key/` was installed phase by phase in exactly this order and the cumulative tests passed at every step.
**Files that grow:** `config.py` (phases 1, 10, 14, 15, 19), `tools.py` (8, 14, 19), `cli.py` (12, 15, 16, 17, 19), `store.py` (14, 15), `handler.py` (15, 19), `evals.py` (11, 16), `graph.py` (5, 19). When a later prompt says "add", it means add to the existing file.
**Two things to know.** `test_19_findings.py` cannot be collected before `handler.py` exists, so phase 14 is proven by `test_22` and phase 15 turns tests 12, 19 and 24 green together. The two infrastructure tests in `test_24` read `answer_key/infra/` until you build `infra/` in phase 21.
**The `PHASE` file.** The tests for all 21 phases are in `tests/` from day one. `PHASE` holds one number, written by you (`echo 5 > PHASE`), and a plain `pytest -q`, `/phase-done` and the GitHub check run only the tests of phases 1 up to that number. Claude Code cannot edit it. Name a test file on the command line and it always runs.

Also in this folder: `recovery.md` (what to paste when a session goes wrong) and `review.md` (review prompts).
