"""Structured JSON logging. Never log raw alert text, prompts, or retrieved passages."""

from __future__ import annotations

import hashlib
import json
import logging
import time

log = logging.getLogger("securetriage")


def digest(text: str) -> str:
    """Short, non-reversible fingerprint used to correlate logs without storing content."""
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:12]


def event(level: int, rid: str, name: str, **fields) -> None:
    record = {"ts": round(time.time(), 3), "rid": rid, "event": name, **fields}
    log.log(level, json.dumps(record, default=str))
