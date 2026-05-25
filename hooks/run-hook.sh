#!/usr/bin/env bash
# Plugin hook dispatcher for agent-brain.
#
# Claude Code invokes this via:
#   "command": "${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh <event>"
#
# We pipe stdin to `brain hook <event>`. Errors are non-fatal — the hook
# emits an empty hookSpecificOutput so the session can proceed.

set -uo pipefail

EVENT="${1:-unknown}"

if ! command -v brain >/dev/null 2>&1; then
  # brain CLI not on PATH — emit empty additionalContext so SessionStart
  # doesn't error. Other events ignore stdout, so the empty JSON is fine.
  cat <<EOF
{"hookSpecificOutput":{"hookEventName":"${EVENT}","additionalContext":""}}
EOF
  exit 0
fi

exec brain hook "$EVENT"
