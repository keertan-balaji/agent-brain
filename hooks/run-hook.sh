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
  # brain CLI not on PATH — emit a schema-valid fallback envelope per event.
  # Only SessionStart and UserPromptSubmit accept additionalContext in
  # hookSpecificOutput; Stop / SessionEnd / PreCompact must not include it.
  case "$EVENT" in
    session-start)
      echo '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":""}}'
      ;;
    user-prompt-submit)
      echo '{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":""}}'
      ;;
    *)
      echo '{}'
      ;;
  esac
  exit 0
fi

exec brain hook "$EVENT"
