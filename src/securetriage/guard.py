"""Checks that run in our own code around the model: schema, sanitising, fail-closed, verdict policy.

Error strings name a path and a rule, never the offending value, so they are safe to log.
"""

from __future__ import annotations

import copy
import json
import re

SEVERITIES = ("informational", "low", "medium", "high", "critical", "unknown")

# action -> tier. "approval" actions are disruptive: a person must approve them.
ACTION_TIERS = {
    "none": "auto",
    "monitor": "auto",
    "open_ticket": "auto",
    "escalate_to_human": "auto",
    "request_credential_reset": "approval",
    "request_isolation": "approval",
}

VERDICT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["severity", "technique", "confidence", "summary", "evidence", "citations", "recommended_action"],
    "properties": {
        "severity": {"type": "string", "enum": list(SEVERITIES)},
        # [0-9], not \d: \d also matches non-ASCII digits.
        "technique": {"type": "string", "pattern": r"^T[0-9]{4}(\.[0-9]{3})?$"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "summary": {"type": "string", "maxLength": 600},
        "evidence": {"type": "array", "maxItems": 6, "items": {"type": "string", "maxLength": 300}},
        "citations": {"type": "array", "maxItems": 6, "items": {"type": "string", "maxLength": 64}},
        "recommended_action": {"type": "string", "enum": list(ACTION_TIERS)},
    },
}

_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
# Reasons are fixed codes or exception class names; anything else could carry alert text or secrets.
_REASON_UNSAFE = re.compile(r"[^A-Za-z0-9_ .:\-]")


def _type_ok(kind: str, value) -> bool:
    # bool is a subclass of int in Python; a verdict must not pass True as a number.
    if kind == "object":
        return isinstance(value, dict)
    if kind == "array":
        return isinstance(value, list)
    if kind == "string":
        return isinstance(value, str)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "null":
        return value is None
    return False


def validate(schema: dict, value, path: str = "$") -> str | None:
    """Small JSON-schema subset. Returns None when valid, else a short error with a path."""
    kind = schema.get("type")
    if kind is not None and not _type_ok(kind, value):
        return f"{path}: expected {kind}"
    if "enum" in schema and value not in schema["enum"]:
        return f"{path}: not an allowed value"
    if isinstance(value, str):
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            return f"{path}: longer than {schema['maxLength']}"
        if "minLength" in schema and len(value) < schema["minLength"]:
            return f"{path}: shorter than {schema['minLength']}"
        # fullmatch, not search: a "$" anchor alone would accept a trailing newline.
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value):
            return f"{path}: does not match the pattern"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            return f"{path}: below {schema['minimum']}"
        if "maximum" in schema and value > schema["maximum"]:
            return f"{path}: above {schema['maximum']}"
    if isinstance(value, list):
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            return f"{path}: more than {schema['maxItems']} items"
        if "minItems" in schema and len(value) < schema["minItems"]:
            return f"{path}: fewer than {schema['minItems']} items"
        if "items" in schema:
            for i, item in enumerate(value):
                err = validate(schema["items"], item, f"{path}[{i}]")
                if err:
                    return err
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                return f"{path}: required field '{key}' is missing"
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in props:
                    return f"{path}: unexpected field"
        for key, sub in props.items():
            if key in value:
                err = validate(sub, value[key], f"{path}.{key}")
                if err:
                    return err
    return None


def _strip(value):
    if isinstance(value, str):
        return _CONTROL.sub("", value)
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            key = _strip(str(k))
            if key in out:
                raise ValueError("alert has keys that collide after cleaning")  # never drop data silently
            out[key] = _strip(v)
        return out
    if isinstance(value, (list, tuple)):
        return [_strip(v) for v in value]
    return value


def sanitize_alert(alert, max_chars: int) -> str:
    """Alert -> bounded text for the user message. Raises ValueError for anything but a JSON object."""
    if not isinstance(alert, dict):
        raise ValueError("alert must be a JSON object")
    if max_chars < 1:
        raise ValueError("max_chars must be at least 1")  # a negative slice would drop the tail, not cap
    try:
        cleaned = _strip(alert)  # may raise ValueError("... collide ..."), which should keep its own message
        text = json.dumps(cleaned, sort_keys=True, ensure_ascii=False)
    except RecursionError:
        raise ValueError("alert is nested too deeply") from None
    except (TypeError, OverflowError):
        raise ValueError("alert is not serialisable as JSON") from None
    return text[:max_chars]


def fail_closed(reason: str) -> dict:
    """The verdict used whenever anything goes wrong: a person looks at it."""
    return {
        "severity": "unknown",
        "technique": "T0000",
        "confidence": "low",
        "summary": "Automatic triage did not complete; a person must review this alert.",
        "evidence": [],
        "citations": [],
        "recommended_action": "escalate_to_human",
        "requires_approval": False,
        "degraded": True,
        "reason": _REASON_UNSAFE.sub("", str(reason))[:100],
    }


def finalize_verdict(v: dict, retrieved_uids, evidence_calls: int) -> tuple[dict | None, str]:
    """Policy after the schema. Returns (verdict, "") or (None, why). Never trusts model-set flags."""
    err = validate(VERDICT_SCHEMA, v)
    if err:
        return None, f"schema: {err}"
    if evidence_calls < 1:
        return None, "no successful evidence call before the verdict"
    retrieved = set(retrieved_uids)
    if any(c not in retrieved for c in v["citations"]):
        return None, "citation was not retrieved in this run"
    out = copy.deepcopy(v)
    if ACTION_TIERS[out["recommended_action"]] == "approval" and not out["citations"]:
        out["recommended_action"] = "escalate_to_human"
    out["requires_approval"] = ACTION_TIERS[out["recommended_action"]] == "approval"
    out["degraded"] = False
    return out, ""
