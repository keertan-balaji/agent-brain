"""Grounding contract for agent-driven Fast-tier reasoning helpers.

The brain prepares the prompt + JSON schema + cache key; the calling agent
synthesizes inline; the brain validates against the schema and persists.

There is no embedded LLM call. cache_key = sha256(name + input + prompt_ver),
so the same prompt yields the same cache row regardless of which agent runs it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Type, TypeVar

from pydantic import BaseModel
from sqlalchemy import Engine, text

from brain.db import session_scope

T = TypeVar("T", bound=BaseModel)


def cache_key_for(helper_name: str, input_hash: bytes, prompt_ver: str) -> bytes:
    h = hashlib.sha256()
    h.update(helper_name.encode("utf-8"))
    h.update(b"\x00")
    h.update(input_hash)
    h.update(b"\x00")
    h.update(prompt_ver.encode("utf-8"))
    return h.digest()


def _hash_prompt(prompt: str) -> bytes:
    return hashlib.sha256(prompt.encode("utf-8")).digest()


@dataclass
class PromptBundle[T: BaseModel]:
    cache_key: bytes
    cache_key_hex: str
    schema_json: dict[str, object]
    prompt: str
    cached: T | None


class GroundedHelper[T: BaseModel]:
    def __init__(
        self,
        *,
        engine: Engine,
        name: str,
        prompt_ver: str,
        output_schema: Type[T],
    ) -> None:
        self.engine = engine
        self.name = name
        self.prompt_ver = prompt_ver
        self.output_schema = output_schema

    def prepare(self, prompt: str) -> PromptBundle[T]:
        input_hash = _hash_prompt(prompt)
        key = cache_key_for(self.name, input_hash, self.prompt_ver)
        cached: T | None = None
        with session_scope(self.engine) as s:
            row = s.execute(
                text("SELECT output_json FROM reasoning_cache WHERE cache_key = :k"),
                {"k": key},
            ).fetchone()
            if row is not None:
                cached = self.output_schema.model_validate(row[0])
                s.execute(
                    text(
                        "UPDATE reasoning_cache SET hit_count = hit_count + 1 "
                        "WHERE cache_key = :k"
                    ),
                    {"k": key},
                )
        return PromptBundle[T](
            cache_key=key,
            cache_key_hex=key.hex(),
            schema_json=self.output_schema.model_json_schema(),
            prompt=prompt,
            cached=cached,
        )

    def finalize(self, *, cache_key: bytes, raw_output: str) -> T:
        parsed = self.output_schema.model_validate_json(raw_output)
        with session_scope(self.engine) as s:
            s.execute(
                text(
                    """
                    INSERT INTO reasoning_cache(
                        cache_key, helper_name, input_hash, prompt_ver, output_json
                    ) VALUES (
                        :k, :n, :ih, :pv, CAST(:oj AS jsonb)
                    )
                    ON CONFLICT (cache_key) DO UPDATE SET hit_count = reasoning_cache.hit_count + 1
                    """
                ),
                {
                    "k": cache_key,
                    "n": self.name,
                    "ih": b"",  # input_hash retained at column level for future analytics; not strictly needed at finalize
                    "pv": self.prompt_ver,
                    "oj": json.dumps(parsed.model_dump(mode="json")),
                },
            )
        return parsed
