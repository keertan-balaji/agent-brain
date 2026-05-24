"""Grounding contract for Fast-tier reasoning helpers.

Every helper is a thin wrapper around the LLM that:
  - hashes the input prompt for cache lookup
  - returns the cached output if (helper_name, prompt, model, model_ver, prompt_ver) matches
  - otherwise calls the LLM, validates output against a Pydantic schema, retries
    up to MAX_RETRIES on validation failure
  - persists the parsed output in reasoning_cache for future hits

The cache key is sha256 over null-separated values so collisions are
astronomically unlikely while remaining deterministic and short (32 bytes,
matching the cache_key BYTEA primary key).
"""

from __future__ import annotations

import hashlib
import json
from typing import Callable, Type, TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy import Engine, text

from brain.db import session_scope

MAX_RETRIES = 3

T = TypeVar("T", bound=BaseModel)


def cache_key_for(
    helper_name: str,
    input_hash: bytes,
    llm_model_id: str,
    llm_model_ver: str,
    prompt_ver: str,
) -> bytes:
    h = hashlib.sha256()
    h.update(helper_name.encode("utf-8"))
    h.update(b"\x00")
    h.update(input_hash)
    h.update(b"\x00")
    h.update(llm_model_id.encode("utf-8"))
    h.update(b"\x00")
    h.update(llm_model_ver.encode("utf-8"))
    h.update(b"\x00")
    h.update(prompt_ver.encode("utf-8"))
    return h.digest()


def _hash_prompt(prompt: str) -> bytes:
    return hashlib.sha256(prompt.encode("utf-8")).digest()


class GroundedHelper[T: BaseModel]:
    """Cache + retry-validate wrapper around an LLM call.

    `llm_fn` is the raw call: `str (prompt) -> str (raw model output)`. Helpers
    bind the prompt template + llm_client.haiku into this callable.
    """

    def __init__(
        self,
        *,
        engine: Engine,
        name: str,
        prompt_ver: str,
        output_schema: Type[T],
        llm_fn: Callable[[str], str],
        llm_model_id: str,
        llm_model_ver: str,
        tokens_used: int = 0,
    ) -> None:
        self.engine = engine
        self.name = name
        self.prompt_ver = prompt_ver
        self.output_schema = output_schema
        self.llm_fn = llm_fn
        self.llm_model_id = llm_model_id
        self.llm_model_ver = llm_model_ver
        self.tokens_used = tokens_used

    def run(self, prompt: str) -> T:
        input_hash = _hash_prompt(prompt)
        key = cache_key_for(
            self.name,
            input_hash,
            self.llm_model_id,
            self.llm_model_ver,
            self.prompt_ver,
        )

        # Cache lookup
        with session_scope(self.engine) as s:
            row = s.execute(
                text("SELECT output_json FROM reasoning_cache WHERE cache_key = :k"),
                {"k": key},
            ).fetchone()
        if row is not None:
            cached_json = row[0]
            parsed = self.output_schema.model_validate(cached_json)
            # bump hit_count
            with session_scope(self.engine) as s:
                s.execute(
                    text(
                        "UPDATE reasoning_cache SET hit_count = hit_count + 1 "
                        "WHERE cache_key = :k"
                    ),
                    {"k": key},
                )
            return parsed

        # Miss — call LLM with retry-and-validate
        last_error: Exception | None = None
        parsed: T | None = None
        for _ in range(MAX_RETRIES):
            raw = self.llm_fn(prompt)
            try:
                parsed = self.output_schema.model_validate_json(raw)
                break
            except ValidationError as e:
                last_error = e
                continue
        else:
            raise RuntimeError(
                f"helper {self.name!r} failed to produce valid JSON after "
                f"{MAX_RETRIES} retries: {last_error}"
            )

        assert parsed is not None  # for type checker; break above guarantees this

        # Persist
        with session_scope(self.engine) as s:
            s.execute(
                text(
                    """
                    INSERT INTO reasoning_cache(
                        cache_key, helper_name, input_hash,
                        llm_model_id, llm_model_ver, prompt_ver,
                        output_json, tokens_used
                    ) VALUES (
                        :k, :n, :ih, :mid, :mver, :pv,
                        CAST(:oj AS jsonb), :tu
                    )
                    ON CONFLICT (cache_key) DO UPDATE SET hit_count = reasoning_cache.hit_count + 1
                    """
                ),
                {
                    "k": key,
                    "n": self.name,
                    "ih": input_hash,
                    "mid": self.llm_model_id,
                    "mver": self.llm_model_ver,
                    "pv": self.prompt_ver,
                    "oj": json.dumps(parsed.model_dump(mode="json")),
                    "tu": self.tokens_used,
                },
            )

        return parsed
