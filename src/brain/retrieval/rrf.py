"""Reciprocal Rank Fusion.

Standard formula: score(d) = sum_i(1 / (k + rank_i(d))) where rank is 1-indexed
across all input ranked lists. Documents missing from a list contribute 0.

k=60 is the Cormack/Clarke/Buettcher default; pgvector/MS MARCO papers use it
unchanged.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Sequence


def rrf_fuse(
    ranked_lists: Sequence[Iterable[int]],
    *,
    k: int = 60,
) -> list[tuple[int, float]]:
    scores: dict[int, float] = defaultdict(float)
    for lst in ranked_lists:
        for rank, doc_id in enumerate(lst, start=1):
            scores[doc_id] += 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
