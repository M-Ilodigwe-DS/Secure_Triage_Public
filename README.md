# SecureTriage

A security-alert triage agent, built one small tested phase at a time with Claude Code.
Given a cloud security alert (for example an AWS GuardDuty finding), the finished system will retrieve
matching runbook passages and asset context, then return a schema-validated verdict with a severity,
a MITRE ATT&CK technique, cited evidence and a recommended action. It only recommends; a person decides.

All data in this project is invented. No credentials are stored in this repository.

## Status

| Phase | What it adds | State |
|---|---|---|
| 1 | Configuration from environment variables, safe logging | Done |
| 2 | The guard: schema validation, alert sanitising, fail-closed verdicts, verdict policy | Done |
| 3 | Runbook parsing, chunking and an injection screen | Done |
| 4 | Embedding client (Amazon Titan Text Embeddings V2) with strict response checks | Done |
| 5 to 21 | Neo4j graph layer, ingestion, retrieval, tool gate, model loop, cost controls, evals, CLI, multi-agent mode, findings store, human review desk, dashboard, AWS infrastructure | Planned |

Nothing here has been run against live Neo4j, AWS Bedrock or any cloud account yet.

## Design rules

- The model proposes and code disposes: every tool call passes an allow-list, a risk class and a schema check.
- Fail closed: any error returns "escalate to a human", never a guess.
- Untrusted text (alerts, runbooks, model output) is data, never instructions; error messages and logs never contain it.
- Read-only access for the agent; secrets only in environment variables or a secrets manager, never in files.
- Tests come first and are locked: a phase is finished when its tests pass.

## Run the tests

```
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
ruff check src tests
```

The file `PHASE` holds the number of the phase being built. `pytest` runs only the tests of phases 1 up to that number.

## Layout

| Path | Purpose |
|---|---|
| `docs/SPEC.md` | The numbered specification the tests and prompts point at |
| `prompts/` | One prompt per phase (what Claude Code is asked to build) and the phase plan in `INDEX.md` |
| `src/securetriage/` | The code built so far |
| `tests/` | The tests for phases 1 to 4 and the shared stand-ins |
| `CLAUDE.md`, `.claude/` | Standing rules, permissions, hooks and a reviewer agent for Claude Code |
