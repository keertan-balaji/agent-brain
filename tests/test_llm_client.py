"""Anthropic Haiku client: key loading, cost accumulation, budget enforcement."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from brain.llm.client import (
    HAIKU_INPUT_USD_PER_MTOK,
    HAIKU_MODEL_ID,
    HAIKU_MODEL_VER,
    HAIKU_OUTPUT_USD_PER_MTOK,
    AnthropicClient,
    BudgetExceeded,
    LlmResult,
    load_api_key,
)


def test_load_api_key_brain_env_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("BRAIN_ANTHROPIC_API_KEY", "brain-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "generic-key")
    assert load_api_key() == "brain-key"


def test_load_api_key_falls_back_to_anthropic_env(monkeypatch):
    monkeypatch.delenv("BRAIN_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "generic-key")
    assert load_api_key() == "generic-key"


def test_load_api_key_falls_back_to_config_file(monkeypatch, tmp_path):
    monkeypatch.delenv("BRAIN_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cfg = tmp_path / "anthropic_key"
    cfg.write_text("file-key\n")
    monkeypatch.setattr("brain.llm.client._CONFIG_KEY_PATH", cfg)
    assert load_api_key() == "file-key"


def test_load_api_key_returns_none_when_no_source(monkeypatch, tmp_path):
    monkeypatch.delenv("BRAIN_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("brain.llm.client._CONFIG_KEY_PATH", tmp_path / "nonexistent")
    assert load_api_key() is None


def _make_mock_anthropic(input_tokens: int, output_tokens: int, text: str = "ok"):
    mock_sdk = MagicMock()
    response = MagicMock()
    response.content = [MagicMock(text=text)]
    response.usage = MagicMock(input_tokens=input_tokens, output_tokens=output_tokens)
    mock_sdk.messages.create.return_value = response
    return mock_sdk


def test_haiku_returns_llmresult():
    with patch("brain.llm.client.Anthropic") as mock_cls:
        mock_cls.return_value = _make_mock_anthropic(100, 50)
        client = AnthropicClient(api_key="x", session_budget_usd=1.0)
        result = client.haiku(system="sys", messages=[{"role": "user", "content": "hi"}])
        assert isinstance(result, LlmResult)
        assert result.text == "ok"
        assert result.tokens_in == 100
        assert result.tokens_out == 50
        assert result.model_id == HAIKU_MODEL_ID
        assert result.model_ver == HAIKU_MODEL_VER
        expected_usd = (100 / 1_000_000) * HAIKU_INPUT_USD_PER_MTOK + (
            50 / 1_000_000
        ) * HAIKU_OUTPUT_USD_PER_MTOK
        assert abs(result.usd - expected_usd) < 1e-9


def test_client_accumulates_total_usd():
    with patch("brain.llm.client.Anthropic") as mock_cls:
        mock_cls.return_value = _make_mock_anthropic(1000, 500)
        client = AnthropicClient(api_key="x", session_budget_usd=10.0)
        client.haiku(system="s", messages=[{"role": "user", "content": "a"}])
        client.haiku(system="s", messages=[{"role": "user", "content": "b"}])
        per_call_usd = (1000 / 1_000_000) * HAIKU_INPUT_USD_PER_MTOK + (
            500 / 1_000_000
        ) * HAIKU_OUTPUT_USD_PER_MTOK
        assert abs(client.total_usd - 2 * per_call_usd) < 1e-9


def test_budget_exceeded_raises():
    with patch("brain.llm.client.Anthropic") as mock_cls:
        mock_cls.return_value = _make_mock_anthropic(1_000_000, 1_000_000)
        client = AnthropicClient(api_key="x", session_budget_usd=0.01)
        with pytest.raises(BudgetExceeded):
            client.haiku(system="s", messages=[{"role": "user", "content": "x"}])
