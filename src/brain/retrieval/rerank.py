"""Cross-encoder rerankers (CrossEncoder pipelines via sentence-transformers).

Two reranker options ship today:

  - MxbaiReranker    — mixedbread-ai/mxbai-rerank-large-v2 (~1.5B params, Qwen2-based).
                       Top quality, ~3GB fp16. Requires ≥6GB GPU or expensive CPU.
  - BgeRerankerV2M3  — BAAI/bge-reranker-v2-m3 (~568M params, XLM-RoBERTa-large based).
                       Trained as the canonical pair for BGE-M3 embedder. ~1.1GB fp16.
                       Fits 4GB GPUs alongside BGE-M3 embedder (~2.2GB total).
                       Default on low-VRAM hosts (Option G in vendor analysis).

Both wrap sentence-transformers' CrossEncoder; PyTorch is the runtime dependency.
Both auto-detect device (cuda if free VRAM headroom, else cpu) and honour the
BRAIN_RERANK_DEVICE env var as an override.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from sentence_transformers import CrossEncoder


@dataclass(frozen=True)
class RerankedHit:
    doc_id: int
    score: float


def _auto_device(min_free_gb: float) -> str:
    """Pick cuda iff free VRAM ≥ min_free_gb; else cpu. Env var BRAIN_RERANK_DEVICE
    overrides. Falls back to cpu on any torch/cuda probe error."""
    override = os.environ.get("BRAIN_RERANK_DEVICE")
    if override:
        return override
    try:
        import torch
        if torch.cuda.is_available():
            free, _ = torch.cuda.mem_get_info()
            return "cuda" if free > min_free_gb * 1024**3 else "cpu"
        return "cpu"
    except Exception:
        return "cpu"


class _CrossEncoderReranker:
    """Base class for cross-encoder rerankers."""

    MODEL_ID: str = ""
    MAX_LENGTH: int = 512
    DEFAULT_BATCH: int = 16
    MIN_FREE_GB: float = 6.0  # subclasses override based on model size

    # Per-reranker tau default. Different cross-encoders output different score
    # distributions — mxbai outputs roughly 0-1 with confident matches at 0.4+,
    # bge-v2-m3 outputs sigmoid probabilities with confident matches at 0.9+ and
    # everything else near zero. Empirically calibrated, overridable per-call.
    DEFAULT_TAU: float = 0.3

    def __init__(self, device: str | None = None) -> None:
        if device is None:
            device = _auto_device(self.MIN_FREE_GB)
        self._device = device
        self._model = CrossEncoder(self.MODEL_ID, max_length=self.MAX_LENGTH, device=device)

    @property
    def device(self) -> str:
        return self._device

    def score(self, pairs: list[tuple[str, str]]) -> list[float]:
        if not pairs:
            return []
        raw = self._model.predict(pairs, batch_size=self.DEFAULT_BATCH)
        return [float(x) for x in raw]

    def rerank(
        self,
        query: str,
        candidates: list[tuple[int, str]],
        *,
        top_k: int = 10,
    ) -> list[RerankedHit]:
        if not candidates:
            return []
        pairs = [(query, text) for _, text in candidates]
        scores = self.score(pairs)
        scored = [RerankedHit(doc_id=cid, score=s) for (cid, _), s in zip(candidates, scores)]
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:top_k]


class MxbaiReranker(_CrossEncoderReranker):
    """mxbai-rerank-large-v2 (~1.5B params, Qwen2 base). ~3GB fp16. Needs ≥6GB GPU."""
    MODEL_ID = "mixedbread-ai/mxbai-rerank-large-v2"
    MIN_FREE_GB = 6.0
    # mxbai outputs roughly logits-shaped scores; confident matches around 0.4-0.6.
    DEFAULT_TAU = 0.3


class BgeRerankerV2M3(_CrossEncoderReranker):
    """bge-reranker-v2-m3 (~568M params, XLM-RoBERTa-large base). ~1.1GB fp16.
    Canonical pair for BGE-M3 embedder. Default on low-VRAM (≤4GB) hosts."""
    MODEL_ID = "BAAI/bge-reranker-v2-m3"
    # Needs ~1.5GB free (1.1GB model + batch overhead). Embedder uses ~1.1GB more.
    MIN_FREE_GB = 1.5
    # bge-v2-m3 outputs sigmoid probabilities. Confident match ~0.95, weak match
    # ~0.001, noise ~0.0003. Empirical: 0.01 keeps weak-but-real hits while still
    # abstaining on the noise floor.
    DEFAULT_TAU = 0.01


def default_reranker(device: str | None = None) -> _CrossEncoderReranker:
    """Pick a reranker that fits the current GPU.

    Heuristic:
      - ≥6GB free → mxbai-rerank-large-v2 (top quality)
      - 1.5-6GB free → bge-reranker-v2-m3 (fits alongside BGE-M3 embedder)
      - <1.5GB free → bge-reranker-v2-m3 on CPU (slow but works)
    Override with env BRAIN_RERANKER ∈ {mxbai, bge-v2-m3}.
    """
    forced = os.environ.get("BRAIN_RERANKER")
    if forced == "mxbai":
        return MxbaiReranker(device=device)
    if forced == "bge-v2-m3":
        return BgeRerankerV2M3(device=device)

    try:
        import torch
        if torch.cuda.is_available():
            free, _ = torch.cuda.mem_get_info()
            free_gb = free / 1024**3
            if free_gb >= 6.0:
                return MxbaiReranker(device=device)
            return BgeRerankerV2M3(device=device)
        return BgeRerankerV2M3(device="cpu")
    except Exception:
        return BgeRerankerV2M3(device="cpu")
