#!/bin/bash
# PreToolUse hook for Bash. Exit code 2 blocks the call and sends stderr back to Claude.
# It catches what prefix rules in settings.json miss (full paths, chained commands, secrets paths).
# It is a seatbelt, not a sandbox: "python -c" or "bash -c" can still do anything. Review what you approve.
input=$(cat)
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty')
[ -z "$cmd" ] && exit 0
block() { echo "Blocked: $1. A human runs this step (see the guide)." >&2; exit 2; }

printf '%s' "$cmd" | grep -Eq '(^|[;&|(`[:space:]])(/[^[:space:];&|]*/)?(aws|sam|curl|wget|ssh|scp|nc)([[:space:]]|$)' \
  && block "cloud and network commands spend money or move data"
printf '%s' "$cmd" | grep -Eq 'git[[:space:]]+(push|remote|reset[[:space:]]+--hard|clean)' \
  && block "this git command publishes or destroys work"
printf '%s' "$cmd" | grep -Eq '(answer_key|\.env|/secrets|\.aws|\.ssh|\.pem)' \
  && block "this path is off limits (answer key or secrets)"
printf '%s' "$cmd" | grep -Eq 'securetriage[[:space:]]+(init-schema|smoke-graph|ingest|seed-assets|triage|eval-triage|eval-retrieval|ask|mcp-serve)' \
  && block "live commands call Neo4j or a model and cost money"
printf '%s' "$cmd" | grep -Eq 'rm[[:space:]]+-[a-zA-Z]*[rf]' \
  && block "recursive or forced delete"
exit 0
