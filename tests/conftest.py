"""Shared test doubles. Nothing here talks to AWS, Neo4j or Anthropic.

A "stub" is a hand-written fake with the same shape as the real thing. It lets us test OUR logic with no cloud.
"""

import copy
import hashlib
import io
import json
import math
from types import SimpleNamespace as NS

import pytest

# ---- which tests count yet? ----------------------------------------------------------------------------------
# The tests for all 21 build phases live in this folder from day one, but your code does not. The file PHASE (one
# whole number, written by YOU, Claude Code cannot edit it) says how far the build has got. A plain `pytest -q`,
# the /phase-done skill and CI all run only the test files of phases 1..PHASE. No PHASE file means "run everything"
# (that is how the answer key is checked). Naming a test file on the command line always runs it, whatever PHASE says.
PHASE_OF = {
    "test_01_config_logging.py": 1, "test_02_guard.py": 2, "test_03_chunking.py": 3, "test_04_embeddings.py": 4,
    "test_05_graph.py": 5, "test_06_ingest.py": 6, "test_07_retrieve.py": 7, "test_08_tools.py": 8,
    "test_09_agent.py": 9, "test_15_budget.py": 10, "test_10_evals.py": 11, "test_11_data.py": 12,
    "test_16_orchestrate.py": 13, "test_22_datapoints_api.py": 14, "test_12_handler.py": 15,
    "test_19_findings.py": 15, "test_24_hitl.py": 15, "test_17_runner.py": 16, "test_18_sdk_agent.py": 16,
    "test_20_findings_agents.py": 17, "test_13_mcp.py": 18, "test_21_graph_hardening.py": 19,
    "test_14_scripts.py": 19, "test_23_dashboard_app.py": 20,
}


def _current_phase():
    import pathlib

    f = pathlib.Path(__file__).resolve().parent.parent / "PHASE"
    if not f.exists():
        return None
    try:
        return int(f.read_text().strip())
    except ValueError:
        raise pytest.UsageError("PHASE must contain one whole number, for example 5") from None


def pytest_ignore_collect(collection_path, config):
    phase = _current_phase()
    need = PHASE_OF.get(collection_path.name)
    if phase is None or need is None or need <= phase:
        return None
    if any(collection_path.name in str(a) for a in config.invocation_params.args):
        return None  # you asked for this file by name
    return True


def pytest_report_header(config):
    phase = _current_phase()
    return f"PHASE file: tests for phases 1..{phase} only" if phase is not None else "no PHASE file: all tests"


DIMS = 256


def fake_vec(text: str, dims: int = DIMS) -> list[float]:
    seed = hashlib.sha256(text.encode()).digest()
    raw = [(seed[i % 32] - 127.5) / 127.5 for i in range(dims)]
    norm = math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw]


class StubBedrockRuntime:
    """Pretends to be boto3 'bedrock-runtime'. Returns a deterministic vector for any text."""

    def __init__(self, dims=DIMS, bad=None):
        self.dims, self.bad, self.calls = dims, bad, []

    def invoke_model(self, body, modelId, accept, contentType):
        req = json.loads(body)
        self.calls.append(req)
        vec = self.bad if self.bad is not None else fake_vec(req["inputText"], req["dimensions"])
        return {"body": io.BytesIO(json.dumps({"embedding": vec}).encode())}


class FakeEmbedder:
    def __init__(self, dims=DIMS):
        self.dims, self.texts = dims, []

    def embed(self, text):
        self.texts.append(text)
        return fake_vec(text, self.dims)


# ---- a fake Neo4j driver: records sessions, modes and queries ----
class FakeRecord:
    def __init__(self, row):
        self._row = row

    def data(self):
        return dict(self._row)


class FakeResult(list):
    """What session.run returns: iterable rows, plus consume()."""

    def consume(self):
        return None


class FakeTx:
    def __init__(self, session):
        self.session = session

    def run(self, query, parameters=None, **kw):
        self.session.driver.log.append({"kind": "tx", "query": query, "params": parameters or {}})
        return [FakeRecord(r) for r in self.session.driver.rows_for(query)]


class FakeSession:
    def __init__(self, driver, config):
        self.driver, self.config = driver, config
        driver.sessions.append(self)
        self.reads, self.writes = 0, 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute_read(self, fn, *a, **kw):
        self.reads += 1
        if self.driver.reject_writes_in_read:
            self.driver.read_hook = True
        return fn(FakeTx(self), *a, **kw)

    def execute_write(self, fn, *a, **kw):
        self.writes += 1
        return fn(FakeTx(self), *a, **kw)

    def run(self, query, parameters=None, **kw):
        self.driver.log.append({"kind": "auto", "query": query, "params": parameters or {}})
        return FakeResult([FakeRecord(r) for r in self.driver.rows_for(query)])


class FakeDriver:
    def __init__(self, scripted=None, reject_writes_in_read=False):
        self.scripted, self.log, self.sessions = scripted or {}, [], []
        self.reject_writes_in_read, self.read_hook, self.closed = reject_writes_in_read, False, False

    def rows_for(self, query):
        for key, rows in self.scripted.items():
            if key in query:
                if isinstance(rows, Exception):
                    raise rows
                return rows
        return []

    def session(self, **config):
        return FakeSession(self, config)

    def close(self):
        self.closed = True


# ---- a fake Claude client that plays back scripted responses ----
def block(type_, **kw):
    return NS(type=type_, **kw)


def tool_use(name, args, id_="tu_1"):
    return block("tool_use", name=name, input=args, id=id_)


class StubLLM:
    """Each script item is (content_blocks, stop_reason) or just content_blocks, or an Exception."""

    def __init__(self, script, usage=None):
        self.script, self.calls = list(script), []
        self.usage = usage or dict(input_tokens=100, output_tokens=10)
        self.messages = NS(create=self._create)

    def _create(self, **kw):
        # snapshot the messages: the agent keeps appending to its list, and we want to see each call as it was sent
        self.calls.append({**kw, "messages": copy.deepcopy(kw["messages"])})
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        content, stop = item if isinstance(item, tuple) else (item, "tool_use")
        return NS(content=content, stop_reason=stop, usage=NS(**self.usage))


GOOD_VERDICT = {
    "severity": "high", "technique": "T1078", "confidence": "medium",
    "summary": "Role used from a new address with unusual S3 volume.",
    "evidence": ["asset i-web-01 is prod and critical", "src 203.0.113.50 is new"],
    "citations": ["rb-credential-compromise#0"], "recommended_action": "escalate_to_human",
}

ROWS = [{"uid": "rb-credential-compromise#0", "text": "Use this runbook when GuardDuty reports unusual API calls.",
         "title": "Runbook: Suspected IAM credential compromise", "score": 0.92, "techniques": ["T1078", "T1110"]}]


@pytest.fixture
def settings():
    from securetriage.config import Settings

    return Settings(model="stub-model", embed_dims=DIMS, max_turns=6)


def make_registry(store=None):
    from securetriage.graph import GraphReader
    from securetriage.retrieve import Retriever
    from securetriage.tools import EventIndex, build_registry

    driver = FakeDriver({
        "queryNodes": ROWS,
        "NEXT": [],
        "MATCH (a:Asset": [{"uid": "i-web-01", "kind": "ec2", "owner": "payments", "criticality": "high",
                            "env": "prod", "connected_to": ["db-orders-01"]}],
    })
    reader = GraphReader(driver, "neo4j", DIMS)
    events = EventIndex([{"ts": "2026-10-22T03:11:09Z", "principal": "role-ci-deployer", "asset": "i-web-01",
                          "event": "AssumeRole", "alert_ref": "alert-0001"}])
    return build_registry(reader, Retriever(reader, FakeEmbedder(), 5), events, 6000, store)


@pytest.fixture
def registry():
    return make_registry()


@pytest.fixture
def findings_store(tmp_path):
    from securetriage.store import SqliteFindingsStore

    return SqliteFindingsStore(str(tmp_path / "findings.db"))


@pytest.fixture
def registry_s(findings_store):
    """The triage registry plus the three findings tools, backed by a temporary SQLite file."""
    return make_registry(findings_store)
