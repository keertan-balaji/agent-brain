"""Anthropic Haiku client.

Loads API key from env or config file. Accumulates per-session USD cost across
calls; raises BudgetExceeded if the projected cost of a call would push the
session over session_budget_usd.

Pricing constants are for claude-haiku-4-5-20251001 as of 2025-10-01.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from anthropic import Anthropic

HAIKU_MODEL_ID = "claude-haiku-4-5-20251001"
HAIKU_MODEL_VER = "2025-10-01"
HAIKU_INPUT_USD_PER_MTOK = 0.25
HAIKU_OUTPUT_USD_PER_MTOK = 1.25

_CONFIG_KEY_PATH = Path.home() / ".config" / "brain" / "anthropic_key"


class BudgetExceeded(RuntimeError):
    """Raised when an LLM call would push session cost over session_budget_usd."""


@dataclass
class LlmResult:
    text: str
    tokens_in: int
    tokens_out: int
    usd: float
    model_id: str
    model_ver: str


def load_api_key() -> str | None:
    if k := os.environ.get("BRAIN_ANTHROPIC_API_KEY"):
        return k
    if k := os.environ.get("ANTHROPIC_API_KEY"):
        return k
    if _CONFIG_KEY_PATH.exists():
        return _CONFIG_KEY_PATH.read_text().strip() or None
    return None


def _cost_usd(tokens_in: int, tokens_out: int) -> float:
    return (tokens_in / 1_000_000) * HAIKU_INPUT_USD_PER_MTOK + (
        tokens_out / 1_000_000
    ) * HAIKU_OUTPUT_USD_PER_MTOK


class AnthropicClient:
    """Wraps the official Anthropic SDK with cost accumulation + budget enforcement."""

    def __init__(self, *, api_key: str, session_budget_usd: float) -> None:
        if not api_key:
            raise ValueError("api_key required")
        self._client = Anthropic(api_key=api_key)
        self.session_budget_usd = session_budget_usd
        self.total_usd = 0.0

    def haiku(
        self,
        *,
        system: str,
        messages: list[dict],
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> LlmResult:
        response = self._client.messages.create(
            model=HAIKU_MODEL_ID,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        tokens_in = response.usage.input_tokens
        tokens_out = response.usage.output_tokens
        usd = _cost_usd(tokens_in, tokens_out)
        if self.total_usd + usd > self.session_budget_usd:
            raise BudgetExceeded(
                f"would exceed budget: cumulative ${self.total_usd:.4f} + ${usd:.4f} > ${self.session_budget_usd:.4f}"
            )
        self.total_usd += usd
        text = response.content[0].text if response.content else ""
        return LlmResult(
            text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            usd=usd,
            model_id=HAIKU_MODEL_ID,
            model_ver=HAIKU_MODEL_VER,
        )
