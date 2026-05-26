"""Origin-aware quoting for retrieval results (Phase 3a-2).

When an agent consumes retrieval output, content sourced from tool calls,
commands, and web pages must be wrapped in a delimiter so the consuming LLM
treats it as data, not instructions. This is the render-time half of the
sanitization defense; the ingest-time half is brain.sanitize.
"""

from __future__ import annotations

_TOOL_KINDS: frozenset[str] = frozenset({"tool_call_output", "command"})
_WEB_KINDS: frozenset[str] = frozenset({"web_page"})


def quote_origin(kind: str, content: str) -> str:
    """Wrap retrieval content with origin-aware delimiters.

    Args:
        kind: Origin type (tool_call_output, command, web_page, decision, etc).
        content: The content to optionally wrap.

    Returns:
        Content wrapped in delimiters for tool/web origins, or passthrough otherwise.
    """
    if kind in _TOOL_KINDS:
        return f"<tool-output>\n{content}\n</tool-output>"
    if kind in _WEB_KINDS:
        return f"<web-content>\n{content}\n</web-content>"
    return content
