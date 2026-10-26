"""Phase 2: guardrails that run in OUR code. Build guard.py until this passes."""

import copy

import pytest
from securetriage.guard import ACTION_TIERS, VERDICT_SCHEMA, fail_closed, finalize_verdict, sanitize_alert, validate

from conftest import GOOD_VERDICT


def test_valid_verdict_passes_schema():
    assert validate(VERDICT_SCHEMA, GOOD_VERDICT) is None


@pytest.mark.parametrize("change", [
    {"severity": "catastrophic"}, {"technique": "T12"}, {"confidence": "certain"},
    {"recommended_action": "delete_everything"}, {"summary": "x" * 601}, {"extra_field": 1},
    {"evidence": ["a"] * 7}, {"citations": "not-a-list"},
])
def test_schema_rejects_bad_values(change):
    assert validate(VERDICT_SCHEMA, {**GOOD_VERDICT, **change}) is not None


def test_schema_rejects_missing_required():
    v = copy.deepcopy(GOOD_VERDICT)
    del v["summary"]
    assert "required" in validate(VERDICT_SCHEMA, v)


def test_validate_integer_and_bool():
    s = {"type": "integer", "minimum": 1, "maximum": 5}
    assert validate(s, 3) is None and validate(s, 9) is not None and validate(s, True) is not None


def test_sanitize_strips_control_chars_sorts_and_caps():
    out = sanitize_alert({"b": "x\x00y\x07", "a": 1}, 8000)
    assert out.index('"a"') < out.index('"b"') and "\x00" not in out and "\x07" not in out
    assert len(sanitize_alert({"d": "A" * 20_000}, 100)) == 100


@pytest.mark.parametrize("bad", [[1, 2], "text", None, 5])
def test_sanitize_requires_object(bad):
    with pytest.raises(ValueError):
        sanitize_alert(bad, 100)


def test_fail_closed_shape():
    v = fail_closed("because")
    assert v["degraded"] is True and v["recommended_action"] == "escalate_to_human"
    assert v["severity"] == "unknown" and v["technique"] == "T0000"
    assert validate(VERDICT_SCHEMA, {k: v[k] for k in VERDICT_SCHEMA["properties"] if k in v}) is None


def test_policy_accepts_good_verdict():
    v, why = finalize_verdict(GOOD_VERDICT, {"rb-credential-compromise#0"}, 1)
    assert why == "" and v["degraded"] is False and v["requires_approval"] is False


def test_policy_needs_tool_evidence():
    v, why = finalize_verdict(GOOD_VERDICT, {"rb-credential-compromise#0"}, 0)
    assert v is None and "evidence" in why


def test_policy_rejects_uncited_passage_ids():
    v, why = finalize_verdict(GOOD_VERDICT, {"some-other#1"}, 1)
    assert v is None and "citation" in why


def test_disruptive_action_needs_a_citation():
    v = {**GOOD_VERDICT, "citations": [], "recommended_action": "request_isolation"}
    out, _ = finalize_verdict(v, set(), 1)
    assert out["recommended_action"] == "escalate_to_human" and out["requires_approval"] is False


def test_disruptive_action_with_citation_requires_approval():
    v = {**GOOD_VERDICT, "recommended_action": "request_credential_reset"}
    out, _ = finalize_verdict(v, {"rb-credential-compromise#0"}, 1)
    assert out["requires_approval"] is True


def test_action_tiers_cover_the_schema_enum():
    assert set(ACTION_TIERS) == set(VERDICT_SCHEMA["properties"]["recommended_action"]["enum"])
