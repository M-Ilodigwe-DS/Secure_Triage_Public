Phase 01: Configuration and logging.

Goal: read settings from environment variables into one frozen object, and emit one-line JSON log events that never contain content.

Read first, completely:
- CLAUDE.md
- docs/SPEC.md sections 9 (config), 5.8 (logging)
- tests/test_01_config_logging.py  (the tests are the executable spec; also tests/conftest.py for the fakes)
- nothing yet (this is the first phase)

Create or change only:
- src/securetriage/config.py
- src/securetriage/logging_utils.py

Behaviour that matters:
- `Settings` is a frozen dataclass. `load_settings(env=None)` builds it from a mapping, so tests pass a dict and never touch the real environment.
- Bad values (a non-integer `TOP_K`, an unknown `LLM_BACKEND`) raise a clear error at start-up, not later in the middle of a run.
- `logging_utils.event(level, rid, name, **fields)` writes one JSON object per line with `rid`, `event`, `ts`. `digest(text)` returns a short sha256 prefix, so logs can refer to an alert without containing it.
- `Settings` holds no password at all, so it cannot leak one in a repr or a log. `resolve_neo4j_password(settings, env=None, ssm_client=None)` returns `NEO4J_PASSWORD` locally, or fetches the SSM SecureString named by `NEO4J_PASSWORD_PARAM` in AWS (the SSM client is injectable).

Note: Settings gains more fields in later phases (budget in 10, findings in 14, review settings in 15, connection tuning in 19). Do not add them now.

Rules: the tests are read-only; never weaken one. Make the smallest change that turns the named tests green. No new dependencies.
Plan first: list the files, functions and edge cases you found in the tests, and wait for me to say "go".
When green, run `pytest -q tests/test_01_config_logging.py`, then `pytest -q`, then `ruff check src tests`. Show me a short summary of the diff and anything you think a test gets wrong. Do not commit.
