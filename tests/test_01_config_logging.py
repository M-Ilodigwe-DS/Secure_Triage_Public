"""Phase 1: configuration and logging. Build config.py and logging_utils.py until this passes."""

import json
import logging

import pytest
from securetriage.config import load_settings, resolve_neo4j_password
from securetriage.logging_utils import digest, event


def test_defaults_per_backend():
    assert load_settings({}).model == "anthropic.claude-haiku-5-5"
    assert load_settings({"LLM_BACKEND": "anthropic"}).model == "claude-haiku-5-5"


def test_env_overrides():
    s = load_settings({"TRIAGE_MODEL": "m", "EMBED_DIMS": "512", "TOP_K": "3", "TOOL_CHOICE": "auto",
                       "NEO4J_URI": "neo4j+s://x.databases.neo4j.io"})
    assert (s.model, s.embed_dims, s.top_k, s.tool_choice) == ("m", 512, 3, "auto")
    assert s.neo4j_uri.startswith("neo4j+s://")


@pytest.mark.parametrize("env", [{"LLM_BACKEND": "openai"}, {"TOOL_CHOICE": "tool"}])
def test_rejects_bad_values(env):
    with pytest.raises(ValueError):
        load_settings(env)


def test_password_from_env_wins():
    s = load_settings({})
    assert resolve_neo4j_password(s, {"NEO4J_PASSWORD": "pw"}) == "pw"


def test_password_from_ssm():
    class Ssm:
        def get_parameter(self, Name, WithDecryption):
            assert WithDecryption is True and Name == "/securetriage/neo4j"
            return {"Parameter": {"Value": "from-ssm"}}

    s = load_settings({"NEO4J_PASSWORD_PARAM": "/securetriage/neo4j"})
    assert resolve_neo4j_password(s, {}, ssm_client=Ssm()) == "from-ssm"


def test_password_missing_everywhere():
    with pytest.raises(RuntimeError):
        resolve_neo4j_password(load_settings({}), {})


def test_digest_is_short_and_stable():
    assert digest("abc") == digest("abc") and len(digest("abc")) == 12 and digest("abc") != digest("abd")


def test_event_logs_one_json_object(caplog):
    with caplog.at_level(logging.INFO, logger="securetriage"):
        event(logging.INFO, "r1", "start", alert_sha="abc")
    rec = json.loads(caplog.records[0].message)
    assert rec["rid"] == "r1" and rec["event"] == "start" and rec["alert_sha"] == "abc" and "ts" in rec
