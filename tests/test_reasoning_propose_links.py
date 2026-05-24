"""reasoning.propose_links: FTS + vector + entity-graph fusion (no LLM)."""

from __future__ import annotations

from brain.db import get_engine
from brain.embed.bge_m3 import BgeM3Embedder
from brain.ingest import ingest_source
from brain.reasoning.propose_links import LinkProposalList, Proposal, propose_links
from brain.schemas import SourceInput
from brain.write import write


def test_propose_links_returns_other_sources_ranked(
    pg_url: str, bge_m3_embedder: BgeM3Embedder
) -> None:
    engine = get_engine(pg_url)
    ids = []
    for body in (
        "postgres is a relational database",
        "postgres has full text search support",
        "bananas grow in tropical climates",
    ):
        src = write(engine, SourceInput(kind="note", content=body))
        ingest_source(engine, source_id=src.source_id, embedder=bge_m3_embedder)
        ids.append(src.source_id)

    result = propose_links(engine, source_id=ids[0], embedder=bge_m3_embedder, top_k=10)
    assert isinstance(result, LinkProposalList)

    target_ids = [p.target_source_id for p in result.proposals]
    # source itself is filtered out
    assert ids[0] not in target_ids
    # the other postgres source should be present and rank above the banana source
    assert ids[1] in target_ids
    if ids[2] in target_ids:
        assert target_ids.index(ids[1]) < target_ids.index(ids[2])


def test_propose_links_filters_out_self(pg_url: str, bge_m3_embedder: BgeM3Embedder) -> None:
    engine = get_engine(pg_url)
    src = write(engine, SourceInput(kind="note", content="only source")).source_id
    ingest_source(engine, source_id=src, embedder=bge_m3_embedder)
    result = propose_links(engine, source_id=src, embedder=bge_m3_embedder, top_k=10)
    assert all(p.target_source_id != src for p in result.proposals)


def test_proposal_rationale_kind_is_valid(
    pg_url: str, bge_m3_embedder: BgeM3Embedder
) -> None:
    engine = get_engine(pg_url)
    for body in ("postgres database", "postgres replication"):
        src = write(engine, SourceInput(kind="note", content=body))
        ingest_source(engine, source_id=src.source_id, embedder=bge_m3_embedder)
    first_id = src.source_id  # second source written
    # use the first source as query
    with __import__("contextlib").nullcontext():
        pass
    # Actually we need the FIRST id. Re-fetch via min(id).
    from sqlalchemy import text

    from brain.db import session_scope

    with session_scope(engine) as s:
        first = s.execute(text("SELECT MIN(id) FROM sources WHERE parent_id IS NULL")).scalar()

    result = propose_links(engine, source_id=first, embedder=bge_m3_embedder, top_k=10)
    valid = {"vector_similarity", "fts_overlap", "shared_entity"}
    for p in result.proposals:
        assert p.rationale_kind in valid
