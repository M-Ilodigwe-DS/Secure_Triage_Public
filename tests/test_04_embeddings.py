"""Phase 4: the embedding client. Build embeddings.py until this passes."""

import json

import pytest
from securetriage.embeddings import EmbeddingError, TitanEmbedder

from conftest import DIMS, StubBedrockRuntime


def make(**kw):
    stub = StubBedrockRuntime(**kw)
    return TitanEmbedder("amazon.titan-embed-text-v2:0", DIMS, client=stub), stub


def test_request_shape():
    emb, stub = make()
    emb.embed("hello")
    assert stub.calls[0] == {"inputText": "hello", "dimensions": DIMS, "normalize": True}


def test_vector_is_returned_as_floats():
    emb, _ = make()
    v = emb.embed("hello")
    assert len(v) == DIMS and all(isinstance(x, float) for x in v)


def test_empty_text_rejected():
    emb, _ = make()
    with pytest.raises(EmbeddingError):
        emb.embed("   ")


def test_oversized_text_is_truncated():
    emb, stub = make()
    emb.embed("a" * 20_000)
    assert len(stub.calls[0]["inputText"]) == 8_000


def test_wrong_length_rejected():
    emb, _ = make(bad=[0.1] * 10)
    with pytest.raises(EmbeddingError):
        emb.embed("x")


def test_non_finite_rejected():
    emb, _ = make(bad=[float("nan")] * DIMS)
    with pytest.raises((EmbeddingError, ValueError)):
        emb.embed("x")


def test_dims_must_be_a_titan_size():
    with pytest.raises(ValueError):
        TitanEmbedder("m", 300, client=object())


def test_request_body_is_valid_json_string():
    emb, stub = make()
    emb.embed("x")
    json.dumps(stub.calls[0])
