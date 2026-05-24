"""Brain-rot defense at fusion time.

Two mechanisms keep synthesized (LLM-derived) content from dominating answers:

1. downweight_synthesized: multiplies synthesized chunk scores by
   `0.7 / (1 + generation_depth)`. Depth-1 -> 0.35x. Depth-3 -> 0.175x. Captured
   content (depth=0, kind != 'synthesized') unchanged.

2. apply_diversity_cap: if synthesized share of the final set exceeds the
   target percentage, swap out the lowest-scored synthesized items for the
   highest-scored captured candidates from the expansion pool until the cap
   holds or the pool is exhausted.

Both functions are pure (no DB). Caller (recall()) loads provenance metadata
in one batched query for both the top set and the expansion pool.
"""

from __future__ import annotations


def downweight_synthesized(
    fused: list[tuple[int, float]],
    provenance: dict[int, tuple[str, int]],
) -> list[tuple[int, float]]:
    reweighted: list[tuple[int, float]] = []
    for doc_id, score in fused:
        kind, depth = provenance.get(doc_id, ("captured", 0))
        if kind == "synthesized":
            score *= 0.7 * (1.0 / (1 + depth))
        reweighted.append((doc_id, score))
    reweighted.sort(key=lambda t: t[1], reverse=True)
    return reweighted


def apply_diversity_cap(
    fused: list[tuple[int, float]],
    *,
    provenance: dict[int, tuple[str, int]],
    expansion_pool: list[tuple[int, float]],
    pool_provenance: dict[int, tuple[str, int]],
    target_synthesized_pct: float = 0.6,
) -> list[tuple[int, float]]:
    if not fused:
        return fused

    def is_synth(doc_id: int) -> bool:
        kind, _ = provenance.get(doc_id, pool_provenance.get(doc_id, ("captured", 0)))
        return kind == "synthesized"

    result = list(fused)
    pool_available = [(d, s) for d, s in expansion_pool if not is_synth(d) and d not in {x for x, _ in result}]
    pool_available.sort(key=lambda t: t[1], reverse=True)

    while True:
        synth_count = sum(1 for d, _ in result if is_synth(d))
        if synth_count / len(result) <= target_synthesized_pct + 1e-9:
            break
        if not pool_available:
            break
        synth_indexed = [(i, s) for i, (d, s) in enumerate(result) if is_synth(d)]
        if not synth_indexed:
            break
        synth_indexed.sort(key=lambda t: t[1])
        worst_idx = synth_indexed[0][0]
        result[worst_idx] = pool_available.pop(0)

    result.sort(key=lambda t: t[1], reverse=True)
    return result
