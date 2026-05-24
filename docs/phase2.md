# Agent Brain v2 — Phase 2 Operations

> **Superseded by Phase 2.5 (agent-driven reasoning).** The original Phase 2 ops doc described an embedded-Haiku flow that no longer ships: `AnthropicClient`, `BudgetExceeded`, the `cost_log` table, and the `--api` pytest flag were all removed. The hybrid retrieval pipeline (BGE-M3 + RRF + mxbai rerank) and the provenance defenses (down-weight + diversity + tau abstain) are unchanged.
>
> See **[`docs/phase2_5.md`](./phase2_5.md)** for current setup, the prepare/finalize CLI shape, and migration notes.
