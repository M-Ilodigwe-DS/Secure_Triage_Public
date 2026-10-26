Phase 02: The guard: validation, sanitising and fail-closed.

Goal: build the checks that run in our own code around the model: a schema validator, an alert sanitiser, the fail-closed verdict and the verdict policy.

Read first, completely:
- CLAUDE.md
- docs/SPEC.md sections 5.1, 5.5, 5.6, 5.7
- tests/test_02_guard.py  (the tests are the executable spec; also tests/conftest.py for the fakes)
- the modules from earlier phases

Create or change only:
- src/securetriage/guard.py

Behaviour that matters:
- `validate(schema, value)` is a small JSON-schema-subset validator written by hand (types, enum, pattern, min/max length and items, required, `additionalProperties: false`). It returns `None` when valid, or a short error string with a path like `$.evidence[2]`.
- `sanitize_alert(alert, max_chars)`: the alert must be a JSON object; serialise with sorted keys; strip control characters; cap at 8000 characters. Anything else raises.
- `fail_closed(reason)` returns the verdict used whenever anything goes wrong: severity `unknown`, technique `T0000`, action `escalate_to_human`, `degraded: true`, plus the reason.
- `finalize_verdict(v, retrieved_uids, evidence_calls)` applies the policy after the schema: at least one successful evidence call; every citation must be a passage id actually retrieved in this run; disruptive actions need a citation or are downgraded to `escalate_to_human`; those actions set `requires_approval`.
- Export `SEVERITIES`, `ACTION_TIERS` (action to tier: `auto` or `approval`) and `VERDICT_SCHEMA`. Later phases import them.

Note: This is the most security-critical file in the project. Plan it carefully and read every line.

Rules: the tests are read-only; never weaken one. Make the smallest change that turns the named tests green. No new dependencies.
Plan first: list the files, functions and edge cases you found in the tests, and wait for me to say "go".
When green, run `pytest -q tests/test_02_guard.py`, then `pytest -q`, then `ruff check src tests`. Show me a short summary of the diff and anything you think a test gets wrong. Do not commit.
