# Technical Decisions

> Status note: translated from the original implementation plan (October 2026). The code may have diverged from this plan; see docs/architecture for the current structure.

| Layer | Choice | Reason | Rejected alternative |
|---|---|---|---|
| Language | Python 3.12 | LLM/agent and statistics ecosystem | Go: thinner agent and analysis ecosystem |
| API | FastAPI + Uvicorn | User request; Pydantic v2 validation generates an OpenAPI schema automatically for the adapter contract | gRPC: stricter but adds friction when integrating with hosts built on different frameworks |
| Schema | Pydantic v2 | One source of truth for the contract, with JSON Schema export for non-Python adapters | dataclass: no validation |
| Storage | SQLite (WAL) via SQLAlchemy 2.x async + Alembic | Sufficient at experiment scale; a single file is easy to archive as a replication artifact | Postgres: optional if multi-process is needed, not required at the start |
| Numerics | NumPy (float64) | `d = 20`, small matrix operations | PyTorch: excessive |
| Embedding | `sentence-transformers`, model frozen and its version recorded, dimension 384 | Shared by the LinUCB cosine feature and B4 (a proposal requirement) | Paid embedding API: cost and nondeterminism |
| Configuration | YAML + Pydantic Settings | The candidate registry and experiment configuration can be committed and hashed | |
| Testing | pytest, pytest-asyncio, httpx `AsyncClient`, hypothesis (property tests for LinUCB) | | |
| Statistics | SciPy, statsmodels | McNemar, Wilcoxon, Holm correction | |
| Observability | structlog (JSON) + a simple `/metrics` endpoint | Audit logger kept separate from the operational log | |
| Packaging | `uv` + `pyproject.toml`, lock file committed | Reproducibility | |

Note: library versions are pinned in the lock file at the start of Phase 0; this plan deliberately does not name specific version numbers.
