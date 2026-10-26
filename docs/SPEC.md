# SecureTriage specification

## 1. Goal
Triage cloud security alerts (GuardDuty-style JSON). The agent investigates with read-only tools, cites approved
runbooks retrieved by RAG, and returns a validated verdict: severity, MITRE ATT&CK technique, confidence, summary,
evidence, citations, recommended action. It recommends only. A human approves any disruptive action.

## 2. Non-goals
No action execution. No UI. No always-on servers. No fine-tuning. No real SIEM connector (sample data only).

## 3. Stack
Python 3.12 (>=3.11). src layout, package `securetriage`. Runtime deps: anthropic[bedrock], boto3, neo4j (official Python driver).
Dev deps: pytest, ruff, pip-audit. Deploy with AWS SAM. CI: GitHub Actions. Region: us-east-1.
Graph and vector store: Neo4j Aura Free (managed, outside AWS), reached over TLS with a password.

## 4. Modules (src/securetriage)
config.py        env settings dataclass (section 9)
logging_utils.py JSON event logging, digest() fingerprint, never logs content
guard.py         schema validator, sanitize_alert, fail_closed, verdict policy
chunking.py      front matter parser, heading chunker, injection screen
ingest.py        document -> chunks -> embeddings -> graph
embeddings.py    Titan V2 client with validation
graph.py         Neo4j client: GraphReader (read-mode only) and GraphWriter (ingest only), schema setup
retrieve.py      embed query, vector top-k, graph expand, format cited passages
tools.py         ToolSpec, ToolRegistry gate, tool handlers
llm.py           Claude client factory (bedrock or direct API)
agent.py         bounded tool-use loop
evals.py         retrieval metrics and triage property checks
cli.py           commands: check-data, init-schema, smoke-graph, ingest, seed-assets, triage [--mode ...], eval-retrieval, eval-triage [--mode],
                 spend, mcp-serve, seed-findings, list-findings, dashboard, ask, review-queue, review-show, review-decide, review-authorized,
                 review-metrics, review-export, hold on|off|status
handler.py       AWS Lambda entry point: EventBridge event -> triage -> DynamoDB, SNS when a human is needed
mcp_server.py    optional: the three read-only tools served over MCP through the same gate (pip install "mcp>=2,<3")
prompts/system.md  the system prompt as a versioned file
budget.py        Prices, cost_usd (prices all four usage fields), RunBudget (thread-safe, one per alert), SpendLedger (JSON file, hard cap)
orchestrate.py   multi-agent triage: run_role, run_specialist (runbooks, context), synthesize, critic, apply_review, triage_multi
prompts/orchestration.md  six tagged prompts: runbook_specialist, context_specialist, synthesizer, critic, recorder, analyst
sdk_agent.py     Claude Agent SDK mode: the same tools through the gate, locked down (section 11)
store.py         findings store: SqliteFindingsStore, DynamoFindingsStore, open_store (section 12.4); decisions table (section 15)
findings.py      build_finding, compute_datapoints, record_direct, demo_findings (section 12)
analyst.py       analyst agent over recorded findings (section 12.8)
dashboard.py     one-file HTML dashboard with no scripts (section 12.10)
datapoints_api.py  Lambda Function URL data endpoint for the Streamlit dashboard (section 14)
hitl.py          human-in-the-loop controls: review policy, decisions, approval rules, hold switch, feedback (section 15)
dashboard_app/   Streamlit app (app.py, data.py, requirements.txt) (section 14.3)
infra/           SAM template, build script and IAM policy files (sections 9a, 13.4, 14.2, 15.5)

## 5. Behavior
5.1 Sanitize: alert must be a JSON object. Serialize with sorted keys, strip control characters, cap at 8000 chars.
5.2 Agent loop (v2). Limits: max 6 turns, max 20000 total tokens, max 2 violations, max_tokens 1024 per call,
    timeout 30s, 3 SDK retries. Tokens used per call = input_tokens + cache_creation_input_tokens +
    cache_read_input_tokens + output_tokens (all four usage fields). The system prompt is read from
    src/securetriage/prompts/system.md at import, sent as a list of text blocks, with cache_control ephemeral on the block
    (caching only applies if the cached prefix meets the model's minimum length; on Haiku 5.5 that is 512 tokens).
    The version of the prompt file (its sha256 prefix) is logged on every run. The alert is wrapped in <alert_data>
    tags in the user message. The alert and passages are never placed in the system prompt.
    Tool choice: setting TOOL_CHOICE=any sends {"type":"any"}; TOOL_CHOICE=auto sends {"type":"auto"}, sets strict:true
    on every tool, and the system prompt says to answer only by calling tools. The default is whichever the live smoke
    test proved works on the configured model. The loop never depends on the model's free text.
    Stop reasons after every call:
      tool_use                      run every tool_use block through the gate, in order.
      end_turn with no tool_use     violation, fail closed (reason: no_tool_use). Do not nudge or retry.
      max_tokens                    fail closed (reason: truncated). A truncated tool call is never executed.
      refusal                       fail closed (reason: refusal); log stop_details category only.
      anything else (stop_sequence, pause_turn, model_context_window_exceeded, unknown)   fail closed (reason: stop_reason).
    Reply format: one user message containing ONLY tool_result blocks, one for every tool_use block in the previous
    assistant message, each echoing tool_use_id, is_error true when refused or failed, appended immediately after the
    assistant message. No text blocks in that message.
    If submit_verdict arrives in the same response as other tool_use blocks, it is a violation: the verdict is not accepted.
    Exceptions: catch the anthropic SDK error family (APITimeoutError, APIConnectionError, RateLimitError, APIStatusError and
    its subclasses, other APIError) and fail closed with the exception class name only as the reason.
5.3 Tools (all read-only except the terminal one):
    search_knowledge(query<=300 chars)  RAG search, returns passages with ids
    lookup_asset(asset_id)              owner, criticality, env, connected assets from the graph
    recent_events(subject)              newest 10 events for a principal or asset id from data/events.jsonl (JSON Lines;
                                        stand-in for a SIEM). Indexed in memory by lower-cased principal and asset. The
                                        join key alert_ref is removed before results reach the model.
    submit_verdict(...)                 terminal; never executed, only validated
    ids match ^[A-Za-z0-9_.:\-]{1,64}$
5.4 Gate: tool must be in the agent's allow-list and registry, args must pass the JSON schema, tool must be
    read-only. Refusals return an error tool_result and count as violations. 2 violations fail closed.
5.5 Verdict schema (additionalProperties false): severity in [informational, low, medium, high, critical, unknown];
    technique ^T\d{4}(\.\d{3})?$; confidence in [low, medium, high]; summary<=600; evidence<=6 items of <=300;
    citations<=6 passage ids; recommended_action in [none, monitor, open_ticket, escalate_to_human,
    request_credential_reset, request_isolation].
5.6 Verdict policy after schema: at least one successful tool call; every citation must be a passage id retrieved in
    this run; request_credential_reset and request_isolation need a citation, otherwise downgrade to
    escalate_to_human; those two set requires_approval=true.
5.7 fail_closed(reason): severity unknown, technique T0000, escalate_to_human, degraded=true.
5.8 Logging: one JSON object per line with rid, event, ts. Log an alert sha256 prefix, never alert text.

## 6. Data and ingestion
Runbook = markdown with front matter: id, title, owner, version, techniques (list of T#### ids).
Chunk by headings (#, ##, ###), pack paragraphs to about 1200 characters, about 150 characters overlap.
Contextual header: the text sent to the embedding model is "<document title>\n<chunk text>"; the stored chunk text is not changed.
Expansion: after vector search, the chunk that follows the best hit (via NEXT) is appended as a passage with via="next".
Injection screen (case-insensitive) quarantines a chunk matching: ignore/disregard previous or prior instructions,
"you are now", "system prompt", tags like <system>, "do not tell the analyst", and the verb exfiltrate used against the
assistant's own context (for example "exfiltrate the system prompt"). The bare word "exfiltration" is allowed: runbooks use it
legitimately. Quarantined chunks are logged and never embedded or stored. This screen is a heuristic with known gaps
(data/redteam/expected.json lists one paraphrase it misses); human review of runbook changes is the real control.
Graph schema: (:Document {uid,title,owner,version,sha}) -[:HAS_CHUNK]-> (:Chunk {uid,text,ord,embed_model,embedding}),
(:Chunk)-[:NEXT]->(:Chunk), (:Chunk)-[:COVERS]->(:Technique {tid}), (:Asset {uid,owner,criticality,env})
-[:CONNECTED_TO]-> (:Asset). Chunk uid = "<doc id>#<ordinal>". All writes are MERGE (idempotent).
Constraints: unique Document.uid, Chunk.uid, Technique.tid, Asset.uid. Vector index chunk_embedding on Chunk.embedding.
Each document (nodes, edges and embeddings) is written in ONE write transaction, so a failed ingest leaves no half-written document.
`init-schema` creates the constraints and the vector index and is safe to run repeatedly.

## 7. Verified integration facts (use these; do not guess; confirm the starred items in the live smoke test)
Titan V2: bedrock-runtime invoke_model, modelId amazon.titan-embed-text-v2:0, body JSON
  {"inputText": str, "dimensions": 256|512|1024, "normalize": true}; response body JSON {"embedding": [floats]}.
  Max input 8192 tokens. Use 1024 dimensions.
Neo4j Aura Free: managed Neo4j. Limits: 200,000 nodes, 400,000 relationships, 1 GB, one database, one user (no custom
  roles), no IP filtering. It auto-pauses after 72 hours of inactivity (resume with the Play button in the Aura console;
  an instance paused for more than 30 days is deleted). Connection details come from the credentials file downloaded
  at creation: NEO4J_URI (neo4j+s://<id>.databases.neo4j.io), NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE.
Driver: pip install neo4j. Create ONE driver per process: GraphDatabase.driver(uri, auth=(user, password)). Run queries
  with driver.execute_query(query, parameters, database_=db, routing_=RoutingControl.READ or WRITE) or with session
  execute_read / execute_write. (*) Confirm the exact keyword names against the installed driver version.
  ALWAYS pass user-controlled values as query parameters. Never build query text from data.
  Runtime code uses READ only. (*) The smoke test must try a write in read mode and report whether the server rejects it.
Vector index (created by init-schema; dimension must equal EMBED_DIMS):
  CREATE VECTOR INDEX chunk_embedding IF NOT EXISTS FOR (c:Chunk) ON (c.embedding)
  OPTIONS {indexConfig: {`vector.dimensions`: 1024, `vector.similarity_function`: 'cosine'}}
  Wait for it with CALL db.awaitIndexes(60) or SHOW VECTOR INDEXES (state ONLINE) before searching.
  Set an embedding: MATCH (c:Chunk {uid: $uid}) CALL db.create.setNodeVectorProperty(c, 'embedding', $embedding)
  Search: CALL db.index.vector.queryNodes('chunk_embedding', $k, $embedding) YIELD node, score
  Higher score means more similar. (*) The smoke test prints the score of an identical vector (expect about 1.0) so the
  scale is known; do not assume a formula. Search is approximate (nearest-neighbor). The newer Cypher 25 SEARCH clause is
  an alternative; use the procedure unless the smoke test shows it is missing or deprecated.
  Embeddings must be a list of exactly EMBED_DIMS finite floats; validate before sending.
Claude on Bedrock: pip install "anthropic[bedrock]"; from anthropic import AnthropicBedrockMantle;
  client = AnthropicBedrockMantle(aws_region="us-east-1", max_retries=3, timeout=30.0); client.messages.create(...)
  same arguments as the direct API. Model ids: anthropic.claude-haiku-5-5 (fallback anthropic.claude-haiku-4-5).
  IAM action: bedrock-mantle:CreateInference. Global endpoint has no premium over the base price.
Claude direct API: anthropic.Anthropic(), model claude-haiku-5-5, ANTHROPIC_API_KEY from the environment.
Tool use loop: assistant content with tool_use blocks -> reply with a user message of tool_result blocks that echo
  tool_use_id and set is_error when refused. Append the assistant content to messages before the results.
SSM Parameter Store: boto3 client "ssm"; get_parameter(Name=..., WithDecryption=True)["Parameter"]["Value"]. IAM action
  ssm:GetParameter on the parameter ARN. A SecureString using the AWS-managed key needs no extra key permission in most
  accounts; if decryption is denied, add kms:Decrypt for that key.
Tool choice and stop reasons (Anthropic docs). tool_choice types: auto (default when tools are given), any (must call a tool),
  tool (must call the named tool), none. any and tool return a 400 on some models (Opus 5.5, Sonnet 5.5, Fable 5.1, Mythos 5.1 are
  listed); (*) the smoke test must prove which choice the configured model accepts. Forced tool use skips extended thinking and
  produces no text before the tool call. strict:true on a tool makes calls match the schema; (*) the smoke test must prove the
  API accepts our tool schemas in strict mode. stop_reason values: end_turn, max_tokens, stop_sequence, tool_use, pause_turn,
  refusal (HTTP 200, details in stop_details), model_context_window_exceeded.
  tool_result rules: the user message with results must immediately follow the assistant message with the tool_use blocks;
  tool_result blocks first; every tool_use id gets a result; errors use is_error true with an instructive message.
  Usage fields: input_tokens (uncached part), cache_creation_input_tokens, cache_read_input_tokens, output_tokens.

## 8. Evals
Retrieval: evals/retrieval_golden.json = [{query, expect_doc, tier}] with tier in paraphrase | indicator | hard. Report hit@k and MRR and the
list of misses; compare runs with regressions(). scripts/lexical_baseline.py gives a no-cloud TF-IDF floor.
Triage: evals/triage_golden.json = [{name, class, scenario, alert, forbid_actions, forbid_severity, allow_actions, expect_technique,
expect_technique_in, must_cite}]. Property checks only, never exact wording. Classes: malicious, injection, benign, ambiguous.
The report shows pass counts per class and how many verdicts were degraded (fail closed).

## 9. Config (environment)
AWS_REGION=us-east-1, LLM_BACKEND=bedrock|anthropic, TRIAGE_MODEL (default per backend), EMBED_MODEL_ID, EMBED_DIMS=1024,
TOP_K=5, TOOL_CHOICE=any|auto (set by the live smoke test), NEO4J_URI, NEO4J_USERNAME, NEO4J_DATABASE (default neo4j), and the password: NEO4J_PASSWORD locally, or in AWS
NEO4J_PASSWORD_PARAM (the SSM parameter name; the password is fetched at cold start and never logged).
No secrets in code or git.

## 9a. Production on AWS (Lambda, EventBridge, DynamoDB, SNS)
Lambda (python3.12, 60s timeout, 512 MB, reserved concurrency 2) triggered by EventBridge rule on custom events
(source securetriage.alerts). The function is NOT in a VPC (Aura Free is reached over the internet with TLS). At cold start
it reads the Neo4j password from SSM Parameter Store (SecureString), builds one Neo4j driver, and reuses both across invocations.
Verdicts and approval requests go to a DynamoDB on-demand table with TTL. SNS email on requires_approval or degraded.
CloudWatch alarms on errors, throttles and degraded verdict rate. 14-day log retention. Async failures go to an SQS
dead-letter queue. Least-privilege role: Titan invoke, bedrock-mantle:CreateInference, ssm:GetParameter on the one
parameter, DynamoDB put on the table, SNS publish, SQS send to the DLQ, logs. The Lambda never writes to the graph: its Neo4j use is read-only (see 13). Findings go to DynamoDB (see 12.4).
Kill switch: set reserved concurrency to 0 or disable the rule. Infrastructure as code with AWS SAM. The password is never
placed in the template, the environment variables or the logs.


## 10. Multi-agent mode and cost controls (added after section 9)
10.1 Pipeline: runbook specialist (tool search_knowledge) and context specialist (lookup_asset, recent_events) run in
    parallel, each with its own RunContext and tool allow-list; each ends with submit_report (summary, key_facts,
    passage_ids). Passage ids not retrieved by that specialist are dropped. A failed specialist yields a MISSING report.
10.2 Synthesizer: no read tools; receives the sanitized alert and the reports inside <specialist_report> tags with "<"
    escaped in the JSON; ends with submit_verdict, validated by finalize_verdict against the UNION of retrieved ids.
10.3 Critic: no read tools; ends with submit_review {agree, concerns}. Disagreement, critic failure, or any failed
    specialist changes the verdict to escalate_to_human (requires_approval false) and nothing else. A reviewer can
    only make the outcome safer. The final verdict gains review.status: agreed | disagreed | unavailable | incomplete_evidence.
10.4 Failure: no specialist report -> degraded verdict, reason no_reports. Synthesis failure -> degraded.
    A bad alert makes no model call.
10.5 Budget: one RunBudget per alert shared by all agents (default 40000 tokens and 0.05 USD, env RUN_MAX_TOKENS,
    RUN_MAX_USD); exceeding it ends that agent with reason "budget". Cost uses PRICE_IN_PER_M and PRICE_OUT_PER_M,
    cache writes at 1.25x and cache reads at 0.1x the input price.
10.6 Ledger: SpendLedger(.spend/ledger.json, SPEND_CAP_USD default 5.00). make_runner checks it before and records after
    every run. Single mode records an upper bound (all tokens at the higher rate); multi mode records the estimate.
    run_triage_eval stops with report.stopped when the cap is reached; the CLI then exits 3.


## 11. Claude Agent SDK mode (guide B8, Pathway A)
11.1 Modes agent-sdk, agent-sdk-team and agent-sdk-stdio run the triage through claude-agent-sdk. Same result shape as
    triage(): {"verdict", "meta", "reason"}. Needs the optional extra agent-sdk.
11.2 Lock-down: tools=[] (no built-in tools), disallowed_tools lists the built-ins again, allowed_tools names only
    mcp__triage__* tools, permission_mode "dontAsk", setting_sources [], strict_mcp_config true, max_budget_usd set.
11.3 Every tool call goes through registry.execute. submit_verdict is accepted once and validated by finalize_verdict.
11.4 Fail closed with a reason: sdk_error (any exception or an is_error result, even if a verdict was submitted),
    no_result, budget, turn_limit, no_verdict, verdict_rejected, bad_alert.
11.5 Stdio mode takes the verdict from structured_output and rebuilds retrieved ids and evidence from the transcript.

## 12. Findings database, tools and analyst (guide A7 phases 14 to 17, B9)
12.1 Tool classes: READ, WRITE, TERMINAL. A WRITE tool runs only if its grant is in RunContext.grants; grants are set
    by harness code only. Refusal text: "write not permitted in this run".
12.2 record_finding {finding_id}: grant "record". Needs ctx.verdict, ctx.alert, ctx.finding_id; the id must equal
    ctx.finding_id; one write per run. The stored record is build_finding(...) from validated data, never model text.
12.3 build_finding keeps alert-derived fields only if they match an id pattern (else "unknown"); summary max 600.
12.4 Store interface: put (True only for the first writer), get, query(severity, action, since_day, degraded, limit),
    all_since, related(finding_id, limit), by_assets(assets, exclude, limit), save_snapshot, get_snapshot. Backends:
    SQLite (FINDINGS_DB) and DynamoDB (FINDINGS_TABLE). FINDINGS_BACKEND is sqlite or dynamodb. There is NO Neo4j
    findings store: Aura Free has no second user or role, so a findings writer would run with owner credentials, and the
    only tests for it used a fake driver. SQL uses constants and bound values only; DynamoDB puts are conditional.
12.5 query_findings and related_findings (READ) return structured fields only, never the summary. create_datapoints {days 1..90} (WRITE,
    grant "publish") computes compute_datapoints and saves snapshot "datapoints-<days>".
12.6 The findings tools are not evidence: only search_knowledge, lookup_asset, recent_events count for finalize_verdict.
12.7 Recording: --record none|direct|agent. direct = record_direct through the gate; agent = recorder role, multi mode
    only. The outcome is meta.record; it never changes the verdict. Bad alerts are not recorded; degraded results are.
    The recorder's receipt is ignored: the store decides whether the finding exists.
12.8 Analyst: tools query_findings, related_findings and create_datapoints; the question is data inside <question>; fails closed with a
    reason (empty_question, no_store, budget, api_error, no_tool_use, turn_limit, unexpected_error); numbers in the
    answer that appear in no tool result are returned in unverified_numbers.
12.9 Lambda: after the verdict is saved, record_direct with the event id; a recording error is logged and does not
    undo or retry the triage. The role may PutItem on the findings table only.
12.10 Dashboard: one HTML file, no scripts, no external files, CSP default-src 'none', all values escaped.

## 13. Neo4j on Aura Free, read-only and production-hardened (guide B9.4 and B9.6)
13.1 Role: knowledge graph for RAG (Document, Chunk, Technique, Asset) and for related_findings (assets up to one
    CONNECTED_TO hop from the finding's asset). Read through GraphReader only (READ-mode sessions, execute_read). GraphWriter
    is used by ingest, init-schema and seed-assets, run by a human. Aura Free has no second user, so the read-only
    guarantee is code (read sessions, no write methods on the reader, a startup probe), not database permissions.
13.2 Connection: driver options max_connection_lifetime, liveness_check_timeout, connection_timeout,
    connection_acquisition_timeout, max_transaction_retry_time, from Settings (NEO4J_*_S). connect(..., verify=True) calls
    verify_connectivity and closes the driver on failure. Errors are translated to GraphError messages that never contain
    the password or the URI credentials; a ServiceUnavailable explains that a paused instance must be resumed.
13.3 Health: GraphReader.health() reports index_found, index_state, index_dims, chunks, nodes, relationships,
    free_tier_used_pct and ready (index ONLINE and dims equal EMBED_DIMS). smoke-graph prints it and exits 2 if not ready.
13.4 Keep-alive: an EventBridge schedule (rate(1 day)) sends {"source": "securetriage.keepalive"} to the triage Lambda,
    which runs health(); not ready raises, which trips the Errors alarm. Whether this counts as use for Aura's pause rule
    is not confirmed: check your own instance after three days.
13.5 related_findings degrades visibly: graph_hops is used, unavailable (reader raised), not_configured, or no_such_finding.
13.6 Live integration tests: tests_live/, skipped unless RUN_LIVE_NEO4J=1 and NEO4J_URI and NEO4J_PASSWORD are set; every
    test works under a random "it<hex>" uid prefix and deletes only that prefix afterwards. Manual workflow
    neo4j-integration.yml runs them in a protected environment.

## 14. Dashboard and data endpoint (guide A10)
14.1 datapoints_api.lambda_handler (Lambda Function URL, AuthType NONE): GET only; bearer token compared with
    hmac.compare_digest against the SSM SecureString named by TOKEN_PARAM; an unset or unreadable token returns 503 and
    never opens the endpoint; 401 with WWW-Authenticate for a missing or wrong token (checked before the cache or store);
    ?days= must be a whole number 1 to 90 (default 14), else 400; the body is compute_datapoints output (aggregates only:
    no finding ids, principals, assets or summaries); cache-control no-store; a 60 second in-memory cache per window;
    a store failure is a generic 502 data_unavailable. The token is never logged.
14.2 The Function URL is public by design (AuthType NONE); the token is the lock. Reserved concurrency 2 bounds cost and abuse.
14.3 dashboard_app/ (Streamlit): app.py pulls with data.fetch_points (https only, plain http only for 127.0.0.1 and localhost, 10 s timeout, Authorization header,
    response shape checked, errors mapped to fixed safe messages that contain neither the URL nor the token). It holds no
    AWS credentials. DATA_URL and DATA_TOKEN come from Streamlit secrets or the environment. Results are cached 60 s.


## 15. Human-in-the-loop controls (hitl.py)
15.1 Purpose: the service recommends; a person decides, and the system can prove who, when and why. Five controls: review policy,
    decisions, approval rules, hold switch, feedback. No model tool can reach any of them.
15.2 Review policy: HITL_MODE is recommend | review_all | sample. recommend reviews what already needs a human (approval-tier action,
    degraded, escalate_to_human). review_all adds every finding. sample adds REVIEW_SAMPLE_PCT percent, chosen deterministically by
    sha256 of the finding id. The mode only adds reviews; it never removes one. Settings: HITL_MODE, REVIEW_SAMPLE_PCT (default 10, 0..100),
    REVIEW_SLA_HOURS (4), APPROVAL_TTL_HOURS (24), REVIEWERS (comma list; empty = any well-formed id). Bad values fail in load_settings.
15.3 Decisions: approve | reject | override (override carries new_action). Each has decision_id, finding_id, decider, ts, reason. A reason of at
    least 10 characters is required to reject or override. Stored in an append-only table: SQLite `decisions`, DynamoDB items pk=dec#<id>,
    kind "decision", conditional put, no ttl. There is no update or delete method, on purpose. Reads are ordered by (ts, decision_id); a
    new decision is stamped just after the last one if its clock is earlier.
15.4 Approval rules, applied by the pure function derive_status(finding, decisions, now, ttl_hours) over the decisions oldest first:
    request_isolation needs 2 distinct approvers; request_credential_reset needs 1; routine (auto-tier) items need an acknowledgement and never lapse.
    Approvals of approval-tier actions older than APPROVAL_TTL_HOURS do not count (status expired when all lapsed). An override resets
    approvals, replaces the action, and its author cannot approve it. A rejection is final: later decisions are refused and ignored.
    The same decider cannot approve twice. The function re-checks every rule; it never trusts the writer. The clock is a parameter.
    Statuses: pending, partially_approved, approved, expired, acknowledged, overridden, rejected. `overdue` is a flag (open longer than REVIEW_SLA_HOURS).
15.5 Hold: snapshot key `hold` plus history events `hold-event-<ts>-<id>`. While on, make_runner (cli) and process (handler) make no model call and
    spend nothing; the alert is recorded as a degraded finding and routed to the queue (and SNS in Lambda). If the switch cannot be read, the run
    fails closed (raises) rather than resuming. IAM: the triage role's PutItem excludes keys dec#* and snap#hold* (dynamodb:LeadingKeys) and its
    GetItem reaches only the hold item; iam-reviewer-policy.json lets a reviewer PutItem only on dec#* and snap#hold*, never Delete or Update.
15.6 Feedback: ReviewDesk.metrics (open, overdue, decided, disagreement_rate = (reject+override)/decisions, median hours to decision) and
    export_feedback (human corrections as candidate evaluation cases, JSONL; a person reads them before they enter evals/).
15.7 Queue order: overdue first, then priority (critical, unknown, high, medium, low, informational), then oldest.
15.8 Commands (all offline, no model): review-queue, review-show ID, review-decide ID --decision approve|reject|override --by NAME --reason TEXT
    [--action A], review-authorized, review-metrics, review-export, hold on|off|status --by NAME --reason TEXT. Exit code 4 means refused.
15.9 Identity: --by is self-asserted on the command line. Real assurance is IAM identity (one SSO identity per person), not the CLI.
15.10 A person's typed reason is never returned by any tool to a model.
