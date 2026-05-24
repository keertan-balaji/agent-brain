"""Reciprocal Rank Fusion: standard formula sum(1 / (k + rank_i))."""

from brain.retrieval.rrf import rrf_fuse


def test_single_list_preserves_order() -> None:
    fused = rrf_fuse([[10, 20, 30]], k=60)
    assert [d for d, _ in fused] == [10, 20, 30]
    assert fused[0][1] > fused[1][1] > fused[2][1]


def test_two_lists_doc_in_both_outranks_singleton() -> None:
    a = [1, 2, 3]
    b = [3, 4, 5]
    fused = dict(rrf_fuse([a, b], k=60))
    # doc 3 appears in both lists; should outscore doc 1 (top of one list only)
    assert fused[3] > fused[1]
    assert fused[3] > fused[4]


def test_rrf_formula_is_standard() -> None:
    fused = dict(rrf_fuse([[100]], k=60))
    assert abs(fused[100] - 1.0 / (60 + 1)) < 1e-9


def test_empty_inputs_return_empty() -> None:
    assert rrf_fuse([]) == []
    assert rrf_fuse([[], []]) == []
