#!/bin/bash
# PreToolUse hook for Write, Edit and MultiEdit. Exit code 2 blocks the call and sends stderr back to Claude.
# This is the hard backstop behind the "deny" rules in settings.json: a rule can be mis-written, a script cannot be argued with.
input=$(cat)
path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty')
[ -z "$path" ] && exit 0
case "$path" in
  */tests/*|*/tests_live/*|*/data/*|*/evals/*|*/answer_key/*|*/docs/SPEC.md|*/PHASE|*/.github/*|*/.claude/*|*/CLAUDE.md|*/.env|*/.env.*|*/scripts/generate_data.py|*/scripts/scenarios_*)
    echo "Blocked: $path is protected (tests, data, evals, SPEC, PHASE, CLAUDE.md, .claude, .github, answer_key, secrets). Tell the human what you want changed and why; do not work around this." >&2
    exit 2
    ;;
esac
exit 0
