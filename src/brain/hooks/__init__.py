"""Claude Code hook integration for Phase 3a-1.

Plugin-shipped hooks invoke `brain hook <event>`, which dispatches into the
modules here. Stdin = JSON event payload. Stdout (for SessionStart + PreCompact)
flows back into Claude Code via additionalContext / compact instructions.
"""
