# Deviations from the plan and from the current proposal

## Library only (decision of 2026-11-01)

ArcLayer is now a Python library that a host imports and calls directly. One host owns one `ArcLayer`, which keeps its state in one SQLite file. This replaces the plan's design of a separate FastAPI service.

| Topic | Plan | Now |
|---|---|---|
| Integration | HTTP API (`/v1/...`) served by FastAPI and Uvicorn | `ArcLayer` methods called in process |
| Authentication | `X-API-Key` per host | none: there is no network surface |
| Configuration | environment variables and a settings class | constructor and `create_policy` arguments |
| Packages | server, contracts and SDK as separate libraries | one library, `arclayer`, with `arclayer.contracts` and `arclayer.host` inside it |
| Ground truth | `/v1/oracle` mounted only in experiment mode | `ArcLayer.register_ground_truth` |
| Concurrency | policies strictly sequential by default | `create_policy` defaults to `strict_sequential=False`; strict mode is opt-in for experiments |
| Orphaned incidents | censored by a manual endpoint | also censored when an `ArcLayer` starts |

The plan's HTTP-specific parts (`design/api-design.md`, the FastAPI row in `technical-decisions.md`, API keys in `process/security-and-ethics.md`) describe the old design and are kept as a record.

What this narrows: the framework-agnostic claim now covers Python agent frameworks, and a deployment as a separate service for non-Python hosts or learning shared across processes becomes future work. The proposal's text does not mention HTTP, so its claims are unchanged apart from that reach.

## Where the implementation departs from the plan

| Topic | Plan or proposal | Implementation | Reason |
|---|---|---|---|
| `FaultEvent` fields | not present | `step_repeatable`, `orchestrator_accessible` | The preconditions `STEP_REPEATABLE` and `ORCHESTRATOR_MESSAGE_ACCESS` cannot be evaluated without host internals |
| Fault class in the gate | undecided (Q1) | soft feature, not a filter | The class indicator would be constant if the gate filtered on it (risk 1.1) |
| P-D dimension | 16 | 17 | The cost ratio is kept (Q3) |
| Incident statuses | 11 | 7 | The intermediate statuses happen inside one transaction |
| Initial state of P, P-D, P-F in evaluation | not explicit | all start from the calibration snapshot, P-F is then frozen (Q5) | The comparison P versus P-F then tests online learning only |
| `N_max` | undecided (Q7) | default 1; the outcome matrix is allowed only for 1 | Validity of the outcome matrix (risk 1.5) |
| Verifiers | `benchmark_task_pass`, `step_check`, `llm_judge` | `benchmark_task_pass`, `task_completed` | `llm_judge` is a sensitivity-analysis option only and is not implemented |
| Packaging | `uv`, one `pyproject.toml`, Alembic migrations, JSON Schema export | one `pyproject.toml` per library; no Alembic; no exported JSON Schema | Not done yet. Schemas can be generated from the models |

## Differences between the plan and the current proposal

Checked on 2026-10-31 against the proposal backup `Usulan_Tesis_..._BACKUP_2026-10-15_sebelum-mendeley-cite.docx`. The plan appears to have been written against the 13 October version.

- The plan numbers its tables 4 to 8 (adapter information, components, candidates, conditions, metrics). The proposal has tables 4 to 7 (components, candidates, conditions, metrics).
- The plan refers to a Subsection III.3.4 (security and ethics, statistics). The proposal has no such subsection.
- The code implements policy **P-F** (frozen after calibration) and an analysis package with McNemar, Wilcoxon, cluster bootstrap and Holm correction. Neither appears in the proposal; its conditions are B0 to B4, P and P-D. The analysis code lives in `projects/evaluation`.
- Equations are not visible to the text extraction used for this check, so Equations 1 to 6 were not compared.
