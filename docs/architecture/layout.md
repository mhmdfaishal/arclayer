# Repository layout

ArcLayer is a recovery control layer for LLM multi-agent (agentic) systems, shipped as a Python library. The host imports it and keeps running its own agents; when the host detects a fault, it asks ArcLayer which registered recovery candidate to run. ArcLayer never executes anything inside the host and never calls an LLM.

One host process owns one `ArcLayer` instance, which keeps its state in one SQLite file (or in memory).

## Top level

```
README.md
docs/              this documentation
cookbook/          runnable recipes, one concept per file
libs/
  arclayer/        the library
```

## Inside `libs/arclayer`

```
arclayer/
  api.py            ArcLayer, the class a host imports
  contracts/        public message types (FaultEventIn, RecoveryCommandOut, ExecutionResultIn, ...)
  host/             what a host implements (HostAdapter, RecoveryExecutor) and the loop it calls (handle_fault)
  domain/           feature vectors, gate, LinUCB, baselines, reward, verification, state machine
  usecases/         HandleIncident, ReportResult, CensorExpired, candidate and policy use cases
    ports.py        Protocols the use cases depend on (storage, embeddings, clock, ids, locks)
    services/       redaction, verifier registry, serialization, seeded RNG
  delivery/         inprocess.py (client used by ArcLayer), mappers.py (contracts <-> domain objects)
  infrastructure/   implementations of the ports
    persistence/    SQLite through SQLAlchemy (append-only audit via triggers), in-memory store
    config/         YAML loaders for candidates, features, reward, gate, static map
    runtime/        system clock, id generator, policy locks
  apiclients/       every call that leaves the process
    embedding/      hashing (offline) and sentence-transformers
  bootstrap.py      composition root: chooses the store and embedder, builds the services
configs/            default candidates, features, reward weights, gate and static map
tests/              unit/, system/, support/
```

## Components of the proposal and where they live

| Component (Table 4 of the proposal) | Location |
|---|---|
| Event adapter | host side, implemented against `arclayer.host.HostAdapter` |
| Event normalizer | `usecases/services/redaction.py`, schema validation in `contracts/` |
| Fault context builder | `domain/features.py` |
| Candidate registry | `usecases/candidates.py`, `ArcLayer.register_candidate` and `candidates` |
| Feasibility and safety gate | `domain/gate.py` |
| LinUCB selector | `domain/policies/linucb.py` |
| Recovery executor | host side, implemented against `arclayer.host.RecoveryExecutor` |
| Verifier | `usecases/services/verifiers.py`, `domain/verification.py` |
| Reward builder | `domain/reward.py` |
| Policy store | `infrastructure/persistence/` |
| Audit logger | append-only `audit` table, enforced by SQLite triggers |

Nine of the eleven components run inside ArcLayer. The adapter and the executor stay in the host because ArcLayer only decides; the host acts.

"External" in the proposal means external to the host's orchestrator: ArcLayer is a separate component that the host reaches only through the adapter contract, and it never imports an agent framework. It is not a separate process.

## What is not in this repository

Test hosts (LangGraph and Agno systems with LLM agents), the LLM clients they use, the experiment harness and the statistical analysis live in the sibling project `projects/evaluation`, which imports ArcLayer from `libs/arclayer`. A synthetic incident generator used by the system tests lives in `libs/arclayer/tests/support/synthetic_host/`.
