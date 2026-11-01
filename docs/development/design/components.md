# Component Design

> Status note: translated from the original implementation plan (October 2026). The code may have diverged from this plan; see docs/architecture for the current structure.

## 7.1 Adapter SDK (host side)

```python
class RecoveryExecutor(Protocol):
    candidate_id: str
    async def execute(self, cmd: RecoveryCommand, ctx: HostContext) -> ExecutionResult: ...

class HostAdapter(Protocol):
    host_id: str
    capabilities: list[str]
    def to_fault_event(self, native: Any) -> FaultEvent: ...
    def executors(self) -> dict[str, RecoveryExecutor]: ...
```

`runtime.py` provides a single function that the host calls when a fault is detected:

```python
async def handle_fault(native_event, adapter, client) -> OutcomeAck:
    event = adapter.to_fault_event(native_event)
    cmd = await client.post_incident(event)
    if cmd.action is not Action.EXECUTE:
        return await client.report_stop(cmd)
    executor = adapter.executors()[cmd.candidate_id]
    result = await executor.execute(cmd, HostContext.current())
    return await client.post_result(cmd.incident_id, result)
```

Two transports with the same interface:
- `HttpClient`: production and cross-process integration.
- `InProcessClient`: calls `Orchestrator` directly without HTTP. Used for unit tests and the outcome matrix so that HTTP overhead does not enter the latency metrics.

Gotcha: the latency `L_t` must be measured **on the host side** (from the start of candidate execution until the rollout stops), not in the control plane, because the control plane does not see the execution time.

## 7.2 Event normalizer and redaction

- Validate `FaultEvent` (Pydantic).
- Redaction: patterns for API keys, bearer tokens, emails, home paths, and URLs with `token=`/`key=` queries; replaced with `[REDACTED:<type>]`. Applied to `fault_description`, `last_messages_summary`, and `artifacts`.
- Deterministic truncation (not random) to the length limit.
- Redaction happens **before** embedding and before audit, so that the embedding result is consistent between the audit record and the decision.

## 7.3 Fault context builder and features (`features/v1.yaml`)

`f_t` (15 dimensions):

| Index | Feature | Transformation |
|---|---|---|
| 0-5 | One-hot fault class | All zeros when `fault_class=None` |
| 6 | Class confidence | `confidence`, or 1.0 for `DETERMINISTIC`/`INJECTOR`, 0 when absent |
| 7-10 | One-hot orchestration pattern | |
| 11 | Relative step position | `step_index / max(step_total_estimate, 1)`, clipped to 0..1; if the estimate is absent, `min(step_index / step_cap, 1)` with `step_cap` from calibration |
| 12 | Prior incidents | `min(prior / N_max, 1)` |
| 13 | Checkpoint available | `checkpoint_restorable` |
| 14 | Remaining budget | `budget_remaining_cost / budget_task_cap` |

`g(t,h)` (4 dimensions, after resolving Gotcha 1.1):

| Index | Feature | Transformation |
|---|---|---|
| 15 | Cosine(embed(fault_description), embed(candidate.description)) | `(cos + 1) / 2` |
| 16 | Class match | 1 if class ∈ supported or supported = "*", 0 otherwise, 0.5 if the class is unknown |
| 17 | Cost ratio | `min(max_cost / budget_remaining_cost, 1)` |
| 18 | Optional precondition completeness | ratio satisfied; 1 if there are no optional preconditions |

Index 19: bias = 1. Total `d = 20`.

P-D variant (H2 ablation): drop indices 15-18 (candidate description and capabilities), `d = 16`. Definition question: does the cost ratio count as a "candidate capability"? The proposal describes P-D as "without description and capability features"; the cost ratio is neither a description nor a capability. Recommendation: P-D drops 15, 16, and 18 and keeps 17, so that the ablation tests only description/capability (see Q3).

Freezing: `features/v1.yaml` is hashed (SHA-256) and the hash is stored in every policy instance and audit record. The policy rejects incidents with a different `feature_version`.

Embedding: the candidate description embeddings are cached when the registry is loaded; fault embeddings are cached by text hash. The model is loaded once in `lifespan`.

## 7.4 Registry

- Source: YAML at startup + API. Stored in the DB with `(candidate_id, version)` unique.
- A policy instance stores a snapshot of the candidate list at creation time. Adding a candidate in the middle of an experiment does not affect instances that are already running (Problem Limitation 4 of the proposal: candidates are fixed before the experiment).

## 7.5 Eligibility and safety gate

Pure function: `gate(ctx, candidates, gate_cfg) -> (eligible, rejections)`. Rules are applied in order, and every rejection carries a reason code:

1. `DISABLED`: `enabled=false`.
2. `PERMISSION_NOT_ALLOWED`: `permissions` is not a subset of the host/gate allowlist.
3. `HOST_CAPABILITY_MISSING`: `required_host_capabilities` is not a subset of `host_capabilities`.
4. `PRECONDITION_UNMET`: one of the `required_preconditions` fails.
5. `OVER_BUDGET`: `max_cost > budget_remaining_cost` or `max_latency_ms > time_remaining_ms`.
6. `INCIDENT_LIMIT`: `prior_incidents_in_task >= N_max` (all candidates rejected, action `ESCALATE`).

Empty `H_t`: `ESCALATE` if the reason is `INCIDENT_LIMIT` or budget, `SAFE_STOP` otherwise. This rule is set in `gate/default.yaml`.

The gate is used identically by **all** policies, including B1-B4 (a requirement of the proposal: same candidates, verifier, and budget). B0 does not call the gate and always returns `SAFE_STOP` without execution.

Note on B1: "retry on the same agent" means always `h1_retry`. If `h1` does not pass the gate (the step is not repeatable), B1 yields `SAFE_STOP`. This is recorded as part of B1's results, not excluded.

## 7.6 Selector

```python
class Selector(Protocol):
    kind: str
    def select(self, ctx: FaultContext, eligible: list[CandidateFeatures], rng: Generator) -> Selection: ...
    def update(self, candidate_id: str, x: np.ndarray, reward: float) -> None: ...
    def state(self) -> PolicyState: ...
```

| Code | Implementation |
|---|---|
| B0 | Does not select; the orchestrator returns `SAFE_STOP` |
| B1 | Always `h1_retry` if eligible |
| B2 | Static class -> candidate mapping from Table 6 (`configs/baselines/static_map.yaml`), frozen before the experiment; if several candidates match, a fixed priority order in the same file; unknown class -> `h1_retry` |
| B3 | Uniform random from `H_t` with a seeded RNG |
| B4 | `argmax` cosine (feature 15) with the same embedding model |
| P | Disjoint LinUCB, `d = 20` |
| P-D | Disjoint LinUCB, candidate features dropped |
| P-F | P initialized from the calibration snapshot, then `freeze` |

`update` on baselines is a no-op, but it is still called so that the code path is the same.

## 7.7 LinUCB (`policy/linucb.py`)

```python
class DisjointLinUCB:
    def __init__(self, candidate_ids, d, alpha, lam, rng):
        self.A = {h: lam * np.eye(d) for h in candidate_ids}   # A_h = lambda I
        self.b = {h: np.zeros(d) for h in candidate_ids}        # b_h = 0

    def score(self, h, x):
        # Use solve, not an explicit inverse: more numerically stable, and d=20
        # makes the cost negligible. Sherman-Morrison is unnecessary at this scale.
        A_inv_x = np.linalg.solve(self.A[h], x)
        theta = np.linalg.solve(self.A[h], self.b[h])           # Equation (1)
        est = float(theta @ x)
        bonus = self.alpha * float(np.sqrt(max(x @ A_inv_x, 0.0)))
        return est, bonus, est + bonus                          # Equation (2)

    def select(self, eligible):
        scored = [(h, *self.score(h, x)) for h, x in eligible]
        best = max(s for *_, s in scored)
        ties = [h for h, _, _, s in scored if np.isclose(s, best, rtol=0, atol=1e-12)]
        return self.rng.choice(ties), scored                    # Equation (3), seeded tie-break

    def update(self, h, x, r):
        if self.frozen:
            return
        self.A[h] += np.outer(x, x)                             # Equation (4)
        self.b[h] += r * x                                      # Equation (5)
```

Parameters: initial `λ` of 0.45 and initial `α` of 0.675 (the values from Poon et al., per the proposal), then the final `α` is chosen from {0.1, 0.25, 0.5, 1} on the calibration data (Section 9.3). Question: is `λ` also calibrated? The proposal only mentions `α`. This plan follows the proposal: `λ` stays fixed at 0.45 (Q4).

Persistence: `A` and `b` are stored as JSON lists of float64 per `(policy_instance_id, candidate_id)` plus an `n_updates` counter. Every update happens in a single transaction together with the audit record write, so there is no policy state that goes unrecorded.

Candidates added to the registry after the policy was created are not included (snapshot, 7.4).

## 7.8 Verifier

Verifier registry keyed by `verifier_id`:

- `benchmark_task_pass`: compares `final_answer` with the ground truth from `VerifierOracle` using GAIA answer normalization (quasi exact match). `S=1` only if `terminal == "task_completed"`.
- `step_check`: local verification without ground truth (e.g. the tool was called successfully, JSON is valid). For the synthetic host and integration tests.
- `llm_judge`: **only** for sensitivity analysis (III.3.4), never the reward source on the main path.

The computation of `C`, `L`, and `V` lives in the verifier, not in the host, so that the host cannot manipulate the reward.

## 7.9 Reward builder

```python
def reward(v: VerificationResult, w: RewardWeights) -> float:
    return w.s * v.S - w.c * v.C - w.l * v.L - w.v * v.V   # Equation (6)
```

Weights come from `reward/default.yaml` (1, 0.2, 0.1, 1). The config validator checks the proposal's invariants: `w_c + w_l < w_s` and `w_v >= w_s`. For sensitivity analysis, `w_c, w_l ∈ {0, 0.1, 0.2, 0.4}`. Note: the combination `w_c = 0.4, w_l = 0.4` still satisfies `0.8 < 1`, so all 16 combinations are valid.

## 7.10 Audit logger

One record per incident, append-only (table without UPDATE/DELETE; tested):

```
incident_id, policy_instance_id, policy_kind, seed, feature_version_hash,
registry_snapshot_hash, fault_context (redacted), eligible[], rejections[],
scores[] (estimate, bonus, score, x), chosen, action, reason,
execution_result, S, C, L, V, reward, A_b_checksum_before, A_b_checksum_after,
timestamps (received, decided, result_received, updated)
```

The `A`/`b` checksums before and after allow an audit replay to prove the update order.
