"""All configuration comes from environment variables. No secrets live in code."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    llm_backend: str = "bedrock"  # "bedrock" (IAM auth) or "anthropic" (API key)
    model: str = "anthropic.claude-haiku-5-5"
    aws_region: str = "us-east-1"
    embed_model_id: str = "amazon.titan-embed-text-v2:0"
    embed_dims: int = 1024  # MUST equal the dimension of the vector index
    tool_choice: str = "any"  # "any" or "auto": set by the live smoke test for your model
    top_k: int = 5
    neo4j_uri: str = ""
    neo4j_username: str = "neo4j"
    neo4j_database: str = "neo4j"
    neo4j_password_param: str = ""  # SSM parameter name (AWS). Locally use NEO4J_PASSWORD instead.
    # connection hardening for Aura Free / Lambda. Seconds.
    neo4j_max_lifetime_s: float = 300.0  # retire a pooled connection after this long
    neo4j_liveness_s: float = 30.0  # re-test a connection idle longer than this before using it (Lambda freezes)
    neo4j_connect_timeout_s: float = 10.0
    neo4j_acquire_timeout_s: float = 20.0
    neo4j_retry_s: float = 15.0  # how long the driver retries a transient transaction failure
    # loop limits (spec 5.2)
    max_turns: int = 6
    max_total_tokens: int = 20_000
    max_violations: int = 2
    max_output_tokens: int = 1024
    request_timeout_s: float = 30.0
    max_retries: int = 3
    alert_max_chars: int = 8_000
    context_max_chars: int = 6_000
    # cost controls. Prices are USD per million tokens; CHECK your provider's page and set them.
    price_in_per_m: float = 0.10
    price_out_per_m: float = 0.50
    run_max_tokens: int = 40_000  # one alert, all agents together
    run_max_usd: float = 0.05
    spend_cap_usd: float = 5.00  # the ledger refuses to start a new run past this
    ledger_path: str = ".spend/ledger.json"
    # findings database: "sqlite" (a local file) or "dynamodb" (a table). Never Neo4j
    findings_backend: str = "sqlite"
    findings_db: str = ".data/findings.db"
    findings_table: str = ""
    # human-in-the-loop controls. The service only RECOMMENDS; these decide who must look.
    hitl_mode: str = "recommend"  # "recommend" | "review_all" | "sample": see hitl.MODES
    review_sample_pct: int = 10  # sample mode: share of routine findings sent to a human for a quality audit
    review_sla_hours: float = 4.0  # a pending item older than this is overdue
    approval_ttl_hours: float = 24.0  # an approval older than this no longer counts (it lapses)
    reviewers: tuple = ()  # allow-list of reviewer ids. Empty = any well-formed id (development only)


DEFAULT_MODELS = {"bedrock": "anthropic.claude-haiku-5-5", "anthropic": "claude-haiku-5-5"}


def _findings_backend(e) -> str:
    b = e.get("FINDINGS_BACKEND", "sqlite").strip().lower()
    if b not in ("sqlite", "dynamodb"):
        raise ValueError("FINDINGS_BACKEND must be 'sqlite' or 'dynamodb'")
    return b


def _hitl(e) -> dict:
    mode = e.get("HITL_MODE", "recommend").strip().lower()
    if mode not in ("recommend", "review_all", "sample"):
        raise ValueError("HITL_MODE must be 'recommend', 'review_all' or 'sample'")
    pct = int(e.get("REVIEW_SAMPLE_PCT", "10"))
    sla, ttl = float(e.get("REVIEW_SLA_HOURS", "4")), float(e.get("APPROVAL_TTL_HOURS", "24"))
    if not 0 <= pct <= 100:
        raise ValueError("REVIEW_SAMPLE_PCT must be between 0 and 100")
    if sla <= 0 or ttl <= 0:
        raise ValueError("REVIEW_SLA_HOURS and APPROVAL_TTL_HOURS must be positive")
    reviewers = tuple(r.strip() for r in e.get("REVIEWERS", "").split(",") if r.strip())
    return {"hitl_mode": mode, "review_sample_pct": pct, "review_sla_hours": sla, "approval_ttl_hours": ttl,
            "reviewers": reviewers}


def load_settings(env: dict | None = None) -> Settings:
    e = os.environ if env is None else env
    backend = e.get("LLM_BACKEND", "bedrock").strip().lower()
    if backend not in DEFAULT_MODELS:
        raise ValueError("LLM_BACKEND must be 'bedrock' or 'anthropic'")
    choice = e.get("TOOL_CHOICE", "any").strip().lower()
    if choice not in ("any", "auto"):
        raise ValueError("TOOL_CHOICE must be 'any' or 'auto'")
    return Settings(
        llm_backend=backend,
        model=e.get("TRIAGE_MODEL", DEFAULT_MODELS[backend]),
        aws_region=e.get("AWS_REGION", "us-east-1"),
        embed_model_id=e.get("EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0"),
        embed_dims=int(e.get("EMBED_DIMS", "1024")),
        tool_choice=choice,
        top_k=int(e.get("TOP_K", "5")),
        neo4j_uri=e.get("NEO4J_URI", ""),
        neo4j_username=e.get("NEO4J_USERNAME", "neo4j"),
        neo4j_database=e.get("NEO4J_DATABASE", "neo4j"),
        neo4j_password_param=e.get("NEO4J_PASSWORD_PARAM", ""),
        neo4j_max_lifetime_s=float(e.get("NEO4J_MAX_LIFETIME_S", "300")),
        neo4j_liveness_s=float(e.get("NEO4J_LIVENESS_S", "30")),
        neo4j_connect_timeout_s=float(e.get("NEO4J_CONNECT_TIMEOUT_S", "10")),
        neo4j_acquire_timeout_s=float(e.get("NEO4J_ACQUIRE_TIMEOUT_S", "20")),
        neo4j_retry_s=float(e.get("NEO4J_RETRY_S", "15")),
        price_in_per_m=float(e.get("PRICE_IN_PER_M", "0.10")),
        price_out_per_m=float(e.get("PRICE_OUT_PER_M", "0.50")),
        run_max_tokens=int(e.get("RUN_MAX_TOKENS", "40000")),
        run_max_usd=float(e.get("RUN_MAX_USD", "0.05")),
        spend_cap_usd=float(e.get("SPEND_CAP_USD", "5.00")),
        ledger_path=e.get("LEDGER_PATH", ".spend/ledger.json"),
        findings_backend=_findings_backend(e),
        findings_db=e.get("FINDINGS_DB", ".data/findings.db"),
        findings_table=e.get("FINDINGS_TABLE", ""),
        **_hitl(e),
    )


def resolve_neo4j_password(settings: Settings, env: dict | None = None, ssm_client=None) -> str:
    """Local: NEO4J_PASSWORD. AWS: fetch the SecureString parameter named by NEO4J_PASSWORD_PARAM."""
    e = os.environ if env is None else env
    if e.get("NEO4J_PASSWORD"):
        return e["NEO4J_PASSWORD"]
    if not settings.neo4j_password_param:
        raise RuntimeError("set NEO4J_PASSWORD (local) or NEO4J_PASSWORD_PARAM (AWS)")
    if ssm_client is None:
        import boto3

        ssm_client = boto3.client("ssm", region_name=settings.aws_region)
    resp = ssm_client.get_parameter(Name=settings.neo4j_password_param, WithDecryption=True)
    return resp["Parameter"]["Value"]
