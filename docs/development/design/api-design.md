# API Design

> Status note: translated from the original implementation plan (October 2026). The code may have diverged from this plan; see docs/architecture for the current structure.
>
> Superseded on 2026-11-01: ArcLayer is a library and has no HTTP API. The same operations are methods on `ArcLayer`; see [integration/api-reference.md](../../integration/api-reference.md).

Prefix `/v1`. Authentication: `X-API-Key` header per host (stored hashed). `ARCLAYER_MODE` is `service` or `experiment`.

| Method | Path | Purpose | Notes |
|---|---|---|---|
| POST | `/v1/incidents` | Receive a `FaultEvent`, return a `RecoveryCommand` | Steps 1-8 of Algorithm 1 |
| POST | `/v1/incidents/{id}/result` | Receive an `ExecutionResult`, return an `OutcomeAck` | `Idempotency-Key` required; steps 9-16 |
| GET | `/v1/incidents/{id}` | Incident detail + audit | |
| GET | `/v1/candidates` | List the registry | |
| POST | `/v1/candidates` | Register a new candidate | Rejected while the active policy instance has `frozen_registry=true` |
| PATCH | `/v1/candidates/{id}` | Change `enabled` | A version change = a new candidate |
| POST | `/v1/policies` | Create a policy instance (`kind`, `params`, `seed`, `feature_version`) | `kind` ∈ B0..B4, P, P_D, P_F |
| GET | `/v1/policies/{id}` | Compact state (n per candidate, θ norm) | |
| POST | `/v1/policies/{id}/freeze` | Freeze updates (for P-F) | |
| POST | `/v1/policies/{id}/snapshot` | Save a copy of A, b | Replication artifact |
| POST | `/v1/oracle/{task_id}` | Register ground truth | **Only** `ARCLAYER_MODE=experiment`; the router is not mounted in service mode |
| GET | `/healthz`, `/metrics` | Liveness, counters | |

Error codes: `409` illegal state transition, or duplicate result with a different payload; `422` schema validation; `423` policy locked (strict sequential mode, an incident is still pending); `404` unknown incident.

`app.py` sketch:

```python
def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="Recovery Control Layer", version="0.1.0", lifespan=lifespan)
    app.include_router(incidents.router, prefix="/v1")
    app.include_router(candidates.router, prefix="/v1")
    app.include_router(policies.router, prefix="/v1")
    if settings.mode == "experiment":
        # The oracle router is deliberately mounted only in experiment mode so that
        # ground truth can never be injected into a regular service.
        app.include_router(oracle.router, prefix="/v1")
    app.include_router(health.router)
    return app
```
