"""Synthesized down-weight + diversity cap (brain-rot defense)."""

from brain.retrieval.provenance import apply_diversity_cap, downweight_synthesized


def test_captured_unchanged() -> None:
    fused = [(1, 1.0), (2, 0.5)]
    prov = {1: ("captured", 0), 2: ("captured", 0)}
    result = downweight_synthesized(fused, prov)
    assert result == [(1, 1.0), (2, 0.5)]


def test_synthesized_depth1_weight_factor() -> None:
    # 0.7 * (1.0 / (1 + 1)) = 0.35
    fused = [(1, 1.0)]
    prov = {1: ("synthesized", 1)}
    result = downweight_synthesized(fused, prov)
    assert abs(result[0][1] - 0.35) < 1e-9


def test_synthesized_depth3_weight_factor() -> None:
    # 0.7 * (1.0 / (1 + 3)) = 0.175
    fused = [(1, 1.0)]
    prov = {1: ("synthesized", 3)}
    result = downweight_synthesized(fused, prov)
    assert abs(result[0][1] - 0.175) < 1e-9


def test_downweight_resorts_by_score() -> None:
    # Original synthesized rank 1 falls below captured rank 2 after downweight
    fused = [(1, 1.0), (2, 0.5)]
    prov = {1: ("synthesized", 1), 2: ("captured", 0)}
    result = downweight_synthesized(fused, prov)
    # synthesized: 1.0 -> 0.35; captured: 0.5 unchanged
    assert result[0] == (2, 0.5)
    assert result[1][0] == 1


def test_diversity_cap_swaps_when_over_threshold() -> None:
    # 3/3 synthesized -> exceeds 0.6; pool has captured candidates to swap in.
    fused = [(1, 0.9), (2, 0.8), (3, 0.7)]
    prov = {1: ("synthesized", 1), 2: ("synthesized", 1), 3: ("synthesized", 1)}
    pool = [(4, 0.6), (5, 0.5)]
    pool_prov = {4: ("captured", 0), 5: ("captured", 0)}
    result = apply_diversity_cap(
        fused, provenance=prov, expansion_pool=pool, pool_provenance=pool_prov, target_synthesized_pct=0.6
    )
    synth_in_result = sum(1 for d, _ in result if prov.get(d, pool_prov.get(d))[0] == "synthesized")
    assert synth_in_result / len(result) <= 0.6 + 1e-9


def test_diversity_cap_noop_when_under_threshold() -> None:
    # 1/3 synthesized -> under 0.6; no swap needed.
    fused = [(1, 0.9), (2, 0.8), (3, 0.7)]
    prov = {1: ("synthesized", 1), 2: ("captured", 0), 3: ("captured", 0)}
    pool: list[tuple[int, float]] = []
    pool_prov: dict[int, tuple[str, int]] = {}
    result = apply_diversity_cap(
        fused, provenance=prov, expansion_pool=pool, pool_provenance=pool_prov, target_synthesized_pct=0.6
    )
    assert result == fused
