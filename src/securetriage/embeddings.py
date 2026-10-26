"""Amazon Titan Text Embeddings V2 client. Validates what it sends and what it gets back.

Error messages never include the text, the vector or AWS error text.
"""

from __future__ import annotations

import json
import math

TITAN_DIMS = (256, 512, 1024)
# Titan accepts up to 8192 tokens; a token is at least one character, so 8000 characters always fits.
MAX_INPUT_CHARS = 8_000


class EmbeddingError(Exception):
    pass


class TitanEmbedder:
    def __init__(self, model_id: str, dims: int, client=None, region: str = "us-east-1"):
        if dims not in TITAN_DIMS:
            raise ValueError(f"dims must be one of {TITAN_DIMS}")
        self.model_id, self.dims = model_id, dims
        if client is None:
            import boto3  # lazy: tests pass a stub and need no AWS

            client = boto3.client("bedrock-runtime", region_name=region)
        self.client = client

    def embed(self, text: str) -> list[float]:
        if not isinstance(text, str) or not text.strip():
            raise EmbeddingError("text to embed is empty")
        body = json.dumps({"inputText": text[:MAX_INPUT_CHARS], "dimensions": self.dims, "normalize": True})
        try:
            resp = self.client.invoke_model(
                modelId=self.model_id, body=body, accept="application/json", contentType="application/json"
            )
            vector = json.loads(resp["body"].read())["embedding"]
        except Exception as exc:  # boto errors can echo request details, so keep only the class name
            raise EmbeddingError(f"embedding call failed: {type(exc).__name__}") from None
        return self._checked(vector)

    def _checked(self, vector) -> list[float]:
        ok = (
            isinstance(vector, list)
            and len(vector) == self.dims
            and all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in vector)
        )
        if not ok:
            raise EmbeddingError(f"embedding must be {self.dims} finite numbers")
        return [float(x) for x in vector]
