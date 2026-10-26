"""Runbook parsing, heading chunker and the injection screen.

Everything read here is untrusted text. The screen only flags and blanks chunks; nothing in a runbook is ever followed.
It is a heuristic with known gaps (see data/redteam/expected.json); human review of runbook changes is the real control.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field

from .logging_utils import event

MAX_CHARS = 1200
OVERLAP = 150
REQUIRED = ("id", "title", "owner", "version")
ID_RE = re.compile(r"^[A-Za-z0-9_.:\-]{1,64}$")
TECHNIQUE_RE = re.compile(r"^T[0-9]{4}(\.[0-9]{3})?$")
HEADING_RE = re.compile(r"^#{1,3}\s+\S")

# name -> pattern. "exfiltrate" is the bare verb, so the noun "exfiltration" (used in real runbooks) is not matched.
_SCREEN = {
    "override_instructions": r"\b(ignore|disregard)\s+(?:(?:all|any|the|your|these|those)\s+)*"
                             r"(previous|prior|above|earlier|system)\b",
    "role_switch": r"\byou\s+are\s+now\b",
    "system_prompt": r"\bsystem\s+prompt\b",
    "fake_tag": r"</?\s*(system|assistant|human|user|instructions?)\s*>",
    "conceal_from_analyst": r"\bdo\s+not\s+tell\s+the\s+analyst\b",
    "exfiltrate_verb": r"\bexfiltrate\b",
}
_PATTERNS = {name: re.compile(rx, re.IGNORECASE) for name, rx in _SCREEN.items()}


@dataclass(frozen=True)
class Doc:
    id: str
    title: str
    owner: str
    version: str
    techniques: list[str]
    body: str
    sha: str  # of the raw file, so a changed runbook is re-ingested


@dataclass
class ChunkSet:
    doc: Doc
    chunks: list[str]  # a quarantined chunk is "" so chunk numbers stay stable
    quarantined: list[tuple[int, list[str]]] = field(default_factory=list)  # (chunk number, pattern names)


def parse_front_matter(raw: str) -> tuple[dict, str]:
    lines = raw.lstrip("﻿").replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        raise ValueError("runbook has no front matter")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise ValueError("front matter is not closed") from None
    meta: dict = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        key, sep, value = line.partition(":")  # first colon only: titles contain colons
        if not sep or not key.strip():
            raise ValueError("malformed front matter line")
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            meta[key.strip()] = [v.strip() for v in value[1:-1].split(",") if v.strip()]
        else:
            meta[key.strip()] = value
    return meta, "\n".join(lines[end + 1:])


def load_doc(raw: str) -> Doc:
    meta, body = parse_front_matter(raw)
    for key in REQUIRED:
        if not meta.get(key):
            raise ValueError(f"front matter is missing '{key}'")
    if not ID_RE.match(meta["id"]):
        raise ValueError("front matter 'id' has characters that are not allowed")
    techniques = meta.get("techniques", [])
    if not isinstance(techniques, list) or not all(TECHNIQUE_RE.match(t) for t in techniques):
        raise ValueError("front matter 'techniques' must be a list of T#### ids")
    return Doc(meta["id"], meta["title"], meta["owner"], meta["version"], techniques, body,
               hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest())


def _sections(body: str) -> list[str]:
    sections: list[list[str]] = [[]]
    in_fence = False
    for line in body.replace("\r\n", "\n").split("\n"):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and HEADING_RE.match(line) and sections[-1]:
            sections.append([])
        sections[-1].append(line)
    return ["\n".join(s).strip() for s in sections if "".join(s).strip()]


def _tail(text: str) -> str:
    """The last ~OVERLAP characters, starting at a word boundary."""
    t = text[-OVERLAP:]
    i = t.find(" ")
    return t[i + 1:] if 0 <= i < len(t) - 1 else t


def _pack(section: str) -> list[str]:
    out: list[str] = []
    cur = ""
    for para in (p.strip() for p in re.split(r"\n\s*\n", section)):
        if not para:
            continue
        if len(para) > MAX_CHARS:  # one huge paragraph: fixed windows that always move forward
            if cur:
                out.append(cur)
                cur = ""
            i = 0
            while True:
                out.append(para[i:i + MAX_CHARS])
                if i + MAX_CHARS >= len(para):
                    break
                i += MAX_CHARS - OVERLAP
            continue
        if cur and len(cur) + 2 + len(para) > MAX_CHARS:
            out.append(cur)
            cur = _tail(cur) + "\n\n" + para
        else:
            cur = f"{cur}\n\n{para}" if cur else para
    if cur:
        out.append(cur)
    return out


def chunk_body(body: str) -> list[str]:
    return [c for section in _sections(body) for c in _pack(section)]


def scan_text(text: str) -> list[str]:
    """Names of the injection patterns that match; an empty list means the text looks clean."""
    return [name for name, rx in _PATTERNS.items() if rx.search(text)]


def prepare(raw_text: str) -> ChunkSet:
    doc = load_doc(raw_text)
    chunks = chunk_body(doc.body)
    quarantined: list[tuple[int, list[str]]] = []
    for i, text in enumerate(chunks):
        hits = scan_text(text)
        if hits:
            quarantined.append((i, hits))
            chunks[i] = ""
            event(logging.WARNING, doc.id, "chunk_quarantined", chunk=i, patterns=hits)  # names only, no text
    return ChunkSet(doc, chunks, quarantined)
