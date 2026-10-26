Phase 04: The embedding client.

Goal: wrap Amazon Titan Text Embeddings V2 in a small class that validates what it sends and what it gets back.

Read first, completely:
- CLAUDE.md
- docs/SPEC.md sections 7 (Titan V2 facts)
- tests/test_04_embeddings.py  (the tests are the executable spec; also tests/conftest.py for the fakes)
- the modules from earlier phases

Create or change only:
- src/securetriage/embeddings.py

Behaviour that matters:
- `TitanEmbedder(model_id, dims, client=None, region=...)`. When `client` is None it creates a `bedrock-runtime` boto3 client; tests pass a stub, so no AWS is needed.
- Request body: `{"inputText": text, "dimensions": dims, "normalize": true}`. `dims` must be 256, 512 or 1024. Empty or oversized input raises before any call.
- The response must be a list of exactly `dims` finite floats, otherwise `EmbeddingError`. Never print the vector or the text.

Note: The unit tests prove our checks, not that Bedrock accepts the request. The live smoke test in A8 proves that.

Rules: the tests are read-only; never weaken one. Make the smallest change that turns the named tests green. No new dependencies.
Plan first: list the files, functions and edge cases you found in the tests, and wait for me to say "go".
When green, run `pytest -q tests/test_04_embeddings.py`, then `pytest -q`, then `ruff check src tests`. Show me a short summary of the diff and anything you think a test gets wrong. Do not commit.
