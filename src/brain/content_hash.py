"""sha256 over text content. Used for dedup lookups across the brain."""

from __future__ import annotations

import hashlib


def sha256_bytes(text: str) -> bytes:
    return hashlib.sha256(text.encode("utf-8")).digest()
