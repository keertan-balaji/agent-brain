"""src/brain/retrieval/render.py — origin-aware quoting at retrieval render."""

from __future__ import annotations

from brain.retrieval.render import quote_origin


def test_quote_origin_wraps_tool_call_output() -> None:
    out = quote_origin("tool_call_output", "stdout body")
    assert out == "<tool-output>\nstdout body\n</tool-output>"


def test_quote_origin_wraps_command() -> None:
    out = quote_origin("command", "ls -la")
    assert out == "<tool-output>\nls -la\n</tool-output>"


def test_quote_origin_uses_web_content_tag_for_web_page() -> None:
    out = quote_origin("web_page", "<html>...")
    assert out.startswith("<web-content>")
    assert out.endswith("</web-content>")
    assert "<html>..." in out


def test_quote_origin_passthrough_for_decision_kind() -> None:
    body = "we chose Postgres over a dedicated vector DB"
    assert quote_origin("decision", body) == body


def test_quote_origin_passthrough_for_unknown_kind() -> None:
    assert quote_origin("anything_else", "x") == "x"


def test_quote_origin_handles_empty_content() -> None:
    out = quote_origin("tool_call_output", "")
    assert out == "<tool-output>\n\n</tool-output>"
