"""mxbai cross-encoder reranker (mixedbread-ai/mxbai-rerank-large-v2).

Runs after RRF fusion to finalize the top-k. The cross-encoder sees full
(query, candidate) pairs and produces a single relevance score, materially
better than the lexical+dense fusion alone on most benchmarks.

Wraps sentence-transformers' CrossEncoder; PyTorch is the runtime dependency.
"""

from __future__ import annotations

from dataclasses import dataclass

from sentence_transformers import CrossEncoder


@dataclass(frozen=True)
class RerankedHit:
    doc_id: int
    score: float


class MxbaiReranker:
    MODEL_ID = "mixedbread-ai/mxbai-rerank-large-v2"
    MAX_LENGTH = 512
    DEFAULT_BATCH = 16

    def __init__(self) -> None:
        self._model = CrossEncoder(self.MODEL_ID, max_length=self.MAX_LENGTH)

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
