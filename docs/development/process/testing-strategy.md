# Testing Strategy

> Status note: translated from the original implementation plan (October 2026). The code may have diverged from this plan; see docs/architecture for the current structure.

| Layer | Coverage | Tools |
|---|---|---|
| Unit | Features, gate, reward, LinUCB, baselines, redaction | pytest, hypothesis |
| Property | Invariants: features in [0,1], success reward > 0, violation reward ≤ 0, only the chosen arm changes, seeded determinism | hypothesis |
| Contract | HTTP and in-process contracts are identical; events from every host pass the schema | pytest parametrize |
| Integration | FastAPI + real SQLite, the full Figure 2 flow | httpx `AsyncClient` |
| E2E | Synthetic host, then the reference host with a stub LLM | |
| Security | Oracle does not leak, redaction, oracle router absent in service mode, audit append-only | |
| Numerical regression | Snapshot of `A`, `b` after a fixed stream | snapshot test |

Real LLMs are **not** called in automated tests. All executors are tested with stubs; real calls only happen in the Phase 5 spike and in Phase 7.
