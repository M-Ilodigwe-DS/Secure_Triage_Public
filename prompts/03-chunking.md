Phase 03: Parsing runbooks, chunking and the injection screen.

Goal: turn a runbook markdown file into clean, bounded chunks and quarantine chunks that look like prompt injection.

Read first, completely:
- CLAUDE.md
- docs/SPEC.md sections 6 (data and ingestion)
- tests/test_03_chunking.py  (the tests are the executable spec; also tests/conftest.py for the fakes)
- the modules from earlier phases

Create or change only:
- src/securetriage/chunking.py

Behaviour that matters:
- Parse front matter (`id`, `title`, `owner`, `version`, `techniques`) without a YAML library; reject a file whose front matter is missing or malformed.
- Chunk by headings (`#`, `##`, `###`), pack paragraphs to about 1200 characters with about 150 characters of overlap. Keep the heading with its text.
- The injection screen (case-insensitive) quarantines a chunk matching: ignore/disregard previous or prior instructions, `you are now`, `system prompt`, tags such as `<system>`, `do not tell the analyst`, and the verb *exfiltrate* aimed at the assistant's context. The bare word *exfiltration* is allowed: real runbooks use it.
- `prepare(raw_text)` returns a `ChunkSet`: the parsed `Doc`, the list of chunks (a quarantined chunk is replaced by an empty string so chunk numbers stay stable), and the list of quarantined chunks with the patterns that matched. Helpers: `parse_front_matter`, `load_doc`, `chunk_body`, `scan_text`.

Note: The screen is a heuristic with known gaps; `data/redteam/expected.json` lists one paraphrase it misses. Human review of runbook changes is the real control.

Rules: the tests are read-only; never weaken one. Make the smallest change that turns the named tests green. No new dependencies.
Plan first: list the files, functions and edge cases you found in the tests, and wait for me to say "go".
When green, run `pytest -q tests/test_03_chunking.py`, then `pytest -q`, then `ruff check src tests`. Show me a short summary of the diff and anything you think a test gets wrong. Do not commit.
