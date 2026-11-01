# Failure handling: alignment with a practitioner article and the reference papers

Status: analysis dated 2026-10-31, restated on 2026-11-01 for the library-only design. The HTTP endpoints, API keys and SDK HTTP client that the original audit mentioned no longer exist; findings below are in library terms, and items the change closed are marked. No code was changed because of the analysis itself.

## Summary

- The practitioner article that prompted this review ("Launching Fault-Tolerant Multi-Agent Architectures", a GitHub gist) is vendor content. Its author, Prasad Kumkar, also bylines the guides it links under "Further Reading", all from one company (Inferensys). The research helper that opened those links found that none cites verifiable research; the author name and the company domain were also seen directly. It is a useful checklist, not evidence.
- An independent audit of the code found **no pattern fully covered, seven partially covered and two not covered** (health checks and compensating actions). Most gaps fall outside the thesis scope; five small additions fit inside it.
- On "separate retries into clear failure classes" specifically: ArcLayer caps incidents per task and gates candidates, but has no notion of retry classes. The `h1_retry` candidate is allowed for every fault class, and a host-side exception is scored as a failure of the candidate that was running (no credit, reward about zero), even when the cause was the host.
- The reference papers support a narrower claim than the article. None evaluates the five-class scheme (transient, dependency, contract, semantic, policy). The best theoretical basis for stopping on repeated errors is Avizienis et al. (2004): recurrence is how a persistent fault is told apart from a transient one.
- Three decisions are needed before any code changes (section 5).

## 1. The article

Nine patterns: durable workflow model, layered health checks, idempotent side effects, retry classes, compensating actions, state recovery, graceful degradation, a control-plane pattern, and launch-time failure patterns. The retry-class pattern says to classify before retrying (transient, dependency, contract, semantic, policy), auto-retry only the first two, use capped exponential backoff with jitter, cap attempts per task and per workflow, persist attempt history, emit the class to telemetry, and stop when the same deterministic error repeats.

## 2. Coverage of the nine patterns

Evidence comes from a read-only code audit by a separate reviewer. Five of its claims that affect design were re-checked directly in the code: the per-task cap reads the host-supplied counter (`domain/gate.py:45`), candidates are snapshotted into a policy when it is created (`usecases/policies.py:59`), censoring runs only through `POST /v1/maintenance/censor` (`delivery/http/handlers.py:76`), `h1_retry` supports every class (`configs/candidates/default.yaml`), and `executor_error` has no special handling beyond verification.

| Pattern | Status | Main evidence | In thesis scope |
|---|---|---|---|
| Durable workflow model | Partial, weak | Incidents and policies persist. There is no task, attempt, heartbeat or compensation field. The attempt count is `prior_incidents_in_task`, sent by the host | No, host concern (proposal limits 1 and 4) |
| Layered health checks | Not covered | No health check exists of any kind (the former `/healthz` only returned a constant `ok` and is gone with the HTTP layer) | A readiness method on `ArcLayer`, yes. Semantic health, no |
| Idempotent side effects | Partial | Result reports are deduplicated by key plus payload fingerprint and tested (`usecases/incidents.py:214-222`). `post_incident` has no idempotency key. Side effects are only the host's self-reported `actions_performed` | Result deduplication is done. A side-effect registry is out |
| Retry classes | Partial, weak | Per-task cap `n_max` exists but trusts the host counter. No mapping from class to retry, and no retry or backoff logic for recovery. The audit records `fault_class` | Yes |
| Compensating actions | Not covered | `h6` rolls back to a checkpoint, which restores state but does not undo external effects | No (limits 1, 3, 10); record as a limitation |
| State recovery | Partial | The decision is committed before the command is returned, legal transitions are enforced and tested. No lease or heartbeat. Incidents a previous process left waiting are now closed when an `ArcLayer` starts; other censoring is manual (`censor_expired`) | Control-plane side, yes |
| Graceful degradation | Partial, weak | `execute`, `safe_stop` and `escalate` are separated by the gate. No partial results | Mostly host side |
| Control-plane pattern | Partial | The store is authoritative. Policy locks are in-process. `schema_version` exists only on `FaultEventIn` | Versioning and correlation, yes |
| Launch failure patterns | Partial, weak | Per-task cap and per-policy serialisation limit retry storms. No jitter, rate limit or circuit breaker. A strictly sequential policy is blocked by an orphaned incident until it is censored; policies created through `ArcLayer.create_policy` are not strict by default, and orphans are closed at startup | In part |

## 3. Behaviours that contradict the article

| Behaviour | By design? |
|---|---|
| `h1_retry` applies to all fault classes, and baseline B1 retries whatever the class | B1 is a deliberately blind baseline. As a candidate that LinUCB may pick, it is the part that deserves a decision |
| The gate does not filter by fault class | Yes: class is a soft feature so that LinUCB and the static map B2 behave differently |
| An executor exception is reported as `executor_error`, scores `S = 0` with a reward of about zero (no cost, almost no latency), and still updates the candidate's statistics | No: a transient host failure counts as a failed attempt of the candidate, so it earns no credit and its uncertainty bonus shrinks. The host loop avoids this for a missing executor but not for an exception |
| The attempt cap trusts the host's counter | No |
| With `n_max > 1`, a candidate that already failed on the task can be chosen again | No |
| One orphaned incident blocks a strictly sequential policy (`PolicyBusy`) until it is censored | No. Largely addressed on 2026-11-01: orphans are closed when an `ArcLayer` starts and the default policy is not strict |
| Disabling a candidate does not reach policies that already exist | Yes: reproducibility of experiments |

## 4. What the reference papers say

Papers below were read by text extraction from the PDFs in `Paper Acuan/`, not re-read page by page by the author of this note. Page numbers are PDF pages. Web sources were opened and their titles and authors checked (see [sources.md](sources.md)).

**Failure classes and retry**
- Babu and Agrawal, *Self-Healing Agentic Orchestrators* (arXiv 2606.01416), Table 3 on p.10 maps eight failure classes to recovery actions under retry, replan, latency and cost budgets, with per-class escalation and stop conditions. This is the closest match to the article. Its benchmark cannot confirm or refute the article: fault seeds depend on the recovery attempt number (p.12), so every fault behaves as transient. "Policy" appears there only as a constraint on allowed actions, as in ArcLayer's gate.
- No paper in the collection uses the five-class scheme, and none tests "stop when the same deterministic error repeats".
- Avizienis et al. (2004), p.15: "error recurrence indicates that the fault is not intermittent". Whether a fault is transient cannot be known in advance; recurrence is how it is found out. This supports a stop-on-repeat rule more than it supports classifying up front.

**Cost of recovery**
- Men et al., FTDI, p.11: tokens per 1 percent of recovery are 197.4 without the cheap repair tier against 83.9 for the full system, which argues against always taking the most expensive repair. p.12 notes that repeated broad repair can drift or time out.

**Idempotency, side effects and replay**
- DoVer, MARS, Magentic-One, AutoGen and the three attribution papers contain no handling of external side effects on replay: no idempotency, mocking, sandboxing or compensation. "Rollback" means truncating the trajectory and restoring agent state.
- DoVer p.21 says no tool state needs a snapshot, but only for its MathChat setting. The Magentic-One and GAIA runs make no such statement.
- Magentic-One pp.19-20 reports an agent that kept retrying a login until the account was suspended, and suggests pausing for human input before irreversible actions, as a future mitigation.
- DoVer's intervention generator receives ground truth (Fig. 8, p.26), which production does not have. MARS replays with temperature 0 (pp.4, 8).

**Compensation (saga)**
- Not covered by the baseline papers. Newer sources do: SagaLLM, Atomix and RAC (see sources.md). Atomix is reported to show that compensation alone is not enough for irreversible effects; read it before relying on that.

**Gaps in the collection**: leases, heartbeats, orphaned tasks and durable workflow engines appear in none of the papers.

## 5. Recommended changes and decisions

None of these has been made. They are ordered by benefit against cost, and all stay within the proposal's limits (one decision per incident, LinUCB unchanged).

1. **Server-side attempt counting and an `ALREADY_TRIED` gate code.** Count incidents per task from the store (the `task_id` column is already indexed) instead of trusting the host, and refuse a candidate that already failed on the same task. Closes two contradictions and gives the stop-on-repeat rule.
2. **An `error_kind` on execution results** (transient, contract, semantic, policy), filled by the SDK from the exception type, with no policy update for transient failures and the kind written to the audit.
3. **Automatic censoring while the process runs, with the command's `deadline_ms` as a lease**, instead of a single global TTL and a manual call. Orphans are already closed when an `ArcLayer` starts.
4. **A readiness method and per-fault-class counts.**
5. **`schema_version` on every message and run correlation on result records.**

Not recommended: a saga or compensation engine, a side-effect registry, semantic health checks and distributed locks. They need a durable workflow component on the host side and fall outside the proposal's limits. They belong in the limitations and future-work text of the thesis.

Decisions needed:

- **Baseline fairness.** The proposal says all policies share candidates, verifier, budget and gate. If the gate starts to refuse retry after a repeated failure or for some classes, baseline B1 either passes through the same gate, which keeps it consistent but changes what "retry only" means, or stays ungated, which breaks the shared-gate rule. Decide before the experiments.
- **Taxonomy.** The existing six fault classes describe symptoms. The article's five classes describe retry behaviour. Extending `FaultClass` changes the feature dimension and the feature hash, which invalidates existing policies. A separate retry-kind field avoids that.
- **Reward semantics.** Skipping the update for transient failures departs from the proposal's rule that the verifier alone defines the reward. It is easy to justify (the same reasoning as censoring) but it is a methodological change to state in the thesis.

## 6. Risks to the thesis text found while reading

- Jiang et al. (MCR and MAGRPO): the 42 percent to 86.7 percent figures appear only in the abstract. The four-page PDF has no results table, its Fig. 1 is captioned "(placeholder)" and the appendix is missing.
- DoVer: the PDFs in the collection are marked "Preprint arXiv:2512.06749v3", while the proposal cites ICLR 2026. Confirm the venue before citing it as published.
- MAST (Cemri et al.): the category percentages differ between Fig. 1, Fig. 2 and Fig. 4, and MAST has no tool-failure or timeout mode. The proposal's tool-failure and timeout classes should be attributed to MCR, not to MAST.
