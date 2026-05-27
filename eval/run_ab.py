"""A/B retrieval eval: FTS-only vs FTS+BGE-M3+RRF (dense leg added).

The mxbai cross-encoder reranker is orthogonal and CPU-expensive (~30s/q);
this script measures the headline question: does adding the dense leg help?
A separate `--with-rerank` flag runs the full pipeline on a subset.

Per question:
  - run both arms
  - check whether expected source IDs (or their children) appear in top-k
  - report hit@1, hit@3, hit@5 + false-positive rate on controls
  - print per-question table for inspection

Run from repo root:
    .venv/bin/python eval/run_ab.py
    .venv/bin/python eval/run_ab.py --with-rerank      # adds full hybrid arm
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import text

from brain.config import load_config
from brain.db import get_engine, session_scope
from brain.read import recall


def _load_questions(path: Path) -> list[dict[str, Any]]:
    return yaml.safe_load(path.read_text())["questions"]


def _expand_ids_to_include_children(engine, ids: list[int]) -> set[int]:
    """Given parent source IDs, return parents + all child source IDs.

    Hybrid retrieval often returns child chunks (created by `brain ingest source`).
    A hit on a child counts the same as a hit on the parent for our purposes.
    """
    if not ids:
        return set()
    expanded = set(ids)
    with session_scope(engine) as s:
        rows = s.execute(
            text("SELECT id FROM sources WHERE parent_id = ANY(:p)"),
            {"p": ids},
        ).fetchall()
    expanded.update(int(r.id) for r in rows)
    return expanded


def _result_ids(hits) -> list[int]:
    """recall() returns RecallHit objects with .id (parent source id)."""
    return [int(h.id) for h in hits]


def _hit_at_k(result_ids: list[int], expected: set[int], k: int) -> bool:
    return any(rid in expected for rid in result_ids[:k])


def run_arm(engine, query: str, *, k: int, mode: str, embedder=None, reranker=None):
    """Returns (result_ids, top1_score, elapsed_ms).
    mode in {'fts', 'hybrid', 'hybrid_rerank'}."""
    t0 = time.time()
    if mode == "fts":
        hits = recall(engine, query, k=k)
    elif mode == "hybrid":
        # FTS + BGE-M3 dense + RRF, no rerank. Pass tau=0 so abstain doesn't
        # fire on raw RRF scores (calibrated tau defaults are for rerank scores).
        hits = recall(engine, query, k=k, embedder=embedder, tau=0.0)
    elif mode == "hybrid_rerank":
        hits = recall(engine, query, k=k, embedder=embedder, reranker=reranker, tau=None)
    elif mode == "hybrid_rerank_notau":
        hits = recall(engine, query, k=k, embedder=embedder, reranker=reranker, tau=0.0)
    else:
        raise ValueError(f"unknown mode: {mode}")
    elapsed = (time.time() - t0) * 1000
    ids = _result_ids(hits)
    top1 = float(hits[0].score) if hits else None
    return ids, top1, elapsed


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reranker",
        choices=["none", "mxbai", "bge-v2-m3", "auto"],
        default="none",
        help="Reranker arm: none = skip, auto = default_reranker() picks for current GPU",
    )
    parser.add_argument(
        "--rerank-device",
        choices=["cuda", "cpu"],
        default=None,
        help="Force reranker device (overrides auto-detect)",
    )
    args = parser.parse_args()

    cfg = load_config()
    engine = get_engine(cfg.db_url)

    questions = _load_questions(Path("eval/questions.yaml"))

    print("loading embedder...", file=sys.stderr)
    t_em0 = time.time()
    from brain.embed.bge_m3 import BgeM3Embedder
    embedder = BgeM3Embedder()
    em_load_ms = (time.time() - t_em0) * 1000

    reranker = None
    rr_load_ms = None
    if args.reranker != "none":
        print(f"loading reranker ({args.reranker})...", file=sys.stderr)
        t_rr0 = time.time()
        if args.reranker == "mxbai":
            from brain.retrieval.rerank import MxbaiReranker
            reranker = MxbaiReranker(device=args.rerank_device)
        elif args.reranker == "bge-v2-m3":
            from brain.retrieval.rerank import BgeRerankerV2M3
            reranker = BgeRerankerV2M3(device=args.rerank_device)
        elif args.reranker == "auto":
            from brain.retrieval.rerank import default_reranker
            reranker = default_reranker(device=args.rerank_device)
        rr_load_ms = (time.time() - t_rr0) * 1000
        print(f"reranker: {type(reranker).__name__} on {reranker.device} "
              f"(load {rr_load_ms:.0f}ms)", file=sys.stderr)
    print(f"embedder load {em_load_ms:.0f}ms\n", file=sys.stderr)

    arms = ["fts", "hybrid"] + (
        ["hybrid_rerank", "hybrid_rerank_notau"] if reranker is not None else []
    )
    rows = []
    arm_stats: dict[str, dict[str, Any]] = {
        a: {"hit@1": 0, "hit@3": 0, "hit@5": 0, "fp_on_control": 0, "ms_total": 0.0}
        for a in arms
    }
    n_eval = 0
    n_control = 0

    for q in questions:
        is_control = q.get("control", False)
        expected = _expand_ids_to_include_children(engine, q["expected_source_ids"])

        results = {}
        for a in arms:
            ids, top1, ms = run_arm(
                engine, q["query"], k=5, mode=a,
                embedder=embedder, reranker=reranker,
            )
            results[a] = {"ids": ids, "top1": top1, "ms": ms}
            arm_stats[a]["ms_total"] += ms

        if is_control:
            n_control += 1
            for a in arms:
                if results[a]["ids"]:
                    arm_stats[a]["fp_on_control"] += 1
        else:
            n_eval += 1
            for a in arms:
                for k in (1, 3, 5):
                    if _hit_at_k(results[a]["ids"], expected, k):
                        arm_stats[a][f"hit@{k}"] += 1

        row = {
            "id": q["id"],
            "tags": ",".join(q.get("tags", [])),
            "query": q["query"][:60],
            "expected": sorted(q["expected_source_ids"]) or "—",
        }
        for a in arms:
            row[f"{a}_ids"] = results[a]["ids"]
            row[f"{a}_hit"] = (
                any(rid in expected for rid in results[a]["ids"][:5])
                if not is_control else None
            )
        rows.append(row)

    # Per-question table
    headers = f"{'id':4} {'tags':22} {'expected':12}"
    for a in arms:
        headers += f" {a + '@5':22}"
    headers += "  query"
    print(headers)
    print("-" * (len(headers) + 60))
    for r in rows:
        line = f"{r['id']:4} {r['tags'][:22]:22} {str(r['expected'])[:12]:12}"
        for a in arms:
            ids = r[f"{a}_ids"]
            hit = r[f"{a}_hit"]
            mark = "✓" if hit else ("✗" if hit is False else "·")
            cell = f"{mark} {str(ids)[:20]}"
            line += f" {cell:22}"
        line += f"  {r['query']}"
        print(line)

    print()
    print(f"=== Summary ({n_eval} non-control questions, {n_control} controls) ===")
    print(f"{'arm':16} {'hit@1':>10} {'hit@3':>10} {'hit@5':>10} {'fp_on_ctrl':>12} {'ms/query':>10}")
    for arm in arms:
        s = arm_stats[arm]
        def fmt(val):
            return f"{val}/{n_eval} ({val*100//n_eval}%)" if n_eval else "—"
        ms = f"{s['ms_total']/(n_eval+n_control):.0f}" if (n_eval + n_control) else "—"
        fp = f"{s['fp_on_control']}/{n_control}" if n_control else "—"
        print(f"{arm:16} {fmt(s['hit@1']):>10} {fmt(s['hit@3']):>10} {fmt(s['hit@5']):>10} {fp:>12} {ms:>10}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
