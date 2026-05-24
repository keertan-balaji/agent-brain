"""Per-bucket score thresholds + abstain semantics.

Each LangMem bucket has a calibrated minimum score below which retrieval is
considered uncertain enough to refuse to answer rather than ground on weak
evidence. Defaults are spec-derived starting points; per-installation
calibration happens via the tau-rolling-ratio report (Task 24).
"""

from __future__ import annotations

from brain.schemas import Bucket

TAU_DEFAULTS: dict[Bucket, float] = {
    "semantic": 0.75,
    "episodic": 0.65,
    "procedural": 0.70,
    "failure": 0.55,
}

DEFAULT_TAU = 0.65


def default_tau_for(bucket: Bucket | str | None) -> float:
    if bucket is None:
        return DEFAULT_TAU
    return TAU_DEFAULTS.get(bucket, DEFAULT_TAU)  # type: ignore[arg-type]


def should_abstain(*, top_score: float | None, tau: float) -> bool:
    if top_score is None:
        return True
    return top_score < tau
