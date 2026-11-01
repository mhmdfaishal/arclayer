# Persistence

ArcLayer keeps its state in a database because a decision and its result arrive in two separate calls, and because what the policy has learned must survive a restart and stay auditable. Without a database every restart would forget all learning and every pending incident. Pass `db_url=None` to `ArcLayer` for an in-memory store that forgets everything on exit, which is what tests and simulations want.

## What is stored

| Table | Holds | Why it must persist |
|---|---|---|
| `policies` | One row per policy instance: LinUCB state (`A`, `b` and the update count per candidate), RNG state, the candidates that were enabled when the policy was created, feature hash, embedding model id, caps, reward weights, `frozen`, and the pending incident id | This is the learning. The selector state is what a restart must not lose |
| `incidents` | One row per incident: status, the fault event, the decision, the result, the verification, the acknowledgement, the idempotency key and timestamps | The result is reported after the decision, so the decision has to be found again. Also needed for duplicate detection, the strictly sequential lock and censoring |
| `candidates` | The registry of recovery candidates and whether each is enabled | Policies snapshot from it when they are created |
| `oracle` | Ground-truth answers per task, written with `register_ground_truth` | The verifier compares the host's final answer with ground truth that the host and the candidates never receive |
| `audit` | Append-only record of every decision and every result | Reproduction and analysis. SQLite triggers abort any `UPDATE` or `DELETE` on it, so a bug or manual SQL cannot rewrite history |

## How it is written

- Each use case runs in one transaction. A decision, the policy change and its audit record are committed together, so a policy state never exists without the audit record that explains it.
- Write transactions start with `BEGIN IMMEDIATE`. Read-only ones use a deferred `BEGIN`, which in WAL mode is never blocked by a writer.
- File databases use WAL with `synchronous=NORMAL`, and a 30 second busy timeout.
- Entities are stored as a JSON payload plus a few indexed columns (`incident_id`, `policy_id`, `task_id`, `status`, `candidate_id`). Policies and incidents are deeply nested, and JSON means adding a domain field does not require a schema migration. The price is that the database is not meant to be queried with SQL for analysis; read it through `ArcLayer` or the audit payloads.
- Tables are created when an `ArcLayer` is built. There are no migrations.

## Why SQLite

Scale is small, a single file is easy to archive as a replication artifact for the thesis, and it needs no extra service. The in-memory store (`infrastructure/persistence/memory.py`) implements the same ports.

## Limits

- One process per database file. Policy locks live in process memory, and an `ArcLayer` that starts up censors incidents another instance left waiting. Several threads in one process are fine.
- Tested with SQLite only. The store accepts other SQLAlchemy URLs, but the append-only triggers, WAL and the locking set-up are SQLite-specific, so on another database the audit table would not be protected.
