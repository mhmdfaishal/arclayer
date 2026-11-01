# `ArcLayer` reference

```python
from arclayer import ArcLayer
```

## Constructor

```python
ArcLayer(
    db_url="sqlite:///./arclayer.db",
    *,
    embedding="hashing",
    candidates=None,
    censor_ttl_s=3600,
    censor_orphans_on_start=True,
)
```

| Argument | Meaning |
|---|---|
| `db_url` | SQLite URL. `None` keeps everything in memory and forgets it on exit. A relative path is resolved against the working directory, so use an absolute path for anything lasting |
| `embedding` | `"hashing"` (offline, 384 dimensions, no semantic meaning) or `"st:<sentence-transformers model>"`. Used for the cosine feature and baseline B4. Recorded in every policy: a policy refuses incidents embedded with a different model (`FeatureMismatch`), so do not change it on a database that holds policies. `st:` needs `pip install arclayer[embeddings]` |
| `candidates` | A YAML path or a list of `CandidateSpec`. Registered only while the registry is empty, so reopening a database never duplicates them |
| `censor_ttl_s` | Seconds before an incident without a result counts as abandoned |
| `censor_orphans_on_start` | Close incidents a previous process left waiting. Keep it on when this is the only process using the database |

## Candidates and ground truth

| Method | Purpose |
|---|---|
| `register_candidate(spec)` | Add a `CandidateSpec`; raises `Conflict` if the id exists |
| `candidates()` | List the registered candidates |
| `set_candidate_enabled(candidate_id, enabled)` | Enable or disable a candidate. Affects only policies created afterwards |
| `register_ground_truth(task_id, answer)` | Ground truth for the `benchmark_task_pass` verifier. Never sent to the host or to a candidate |

## Policies

```python
policy_id = layer.create_policy(
    kind="P", seed=0, *,
    n_max=1, step_cap=20, task_cost_cap=3.0,
    incident_cost_cap=1.0, incident_latency_cap_ms=300_000,
    strict_sequential=False, allowed_permissions=None, **options,
)
```

`kind` is `"P"` (LinUCB), `"P_D"` (LinUCB without candidate-description features), `"P_F"` (LinUCB frozen after calibration) or a baseline `"B0"` to `"B4"`. Further options are the remaining `CreatePolicyIn` fields: `alpha`, `lam`, `reward_weights`, `static_map` and `static_default` (used by `"B2"`), `retry_candidate_id`, `init_state`, `policy_id`, `experiment_id`.

| Argument | Meaning |
|---|---|
| `n_max` | Maximum incidents per task. Counted from `prior_incidents_in_task`, which the host sends |
| `step_cap`, `task_cost_cap` | Normalisation constants for the step position and the remaining budget features |
| `incident_cost_cap`, `incident_latency_cap_ms` | Divisors that turn reported cost and latency into `C` and `L` in `[0, 1]`. Use the unit your executors report in `cost_used` |
| `strict_sequential` | `True` raises `PolicyBusy` for a new incident while another waits for its result. Default `False`, so concurrent agents can share a policy |
| `allowed_permissions` | Permissions the gate allows. Defaults to every permission of the enabled candidates |

| Method | Purpose |
|---|---|
| `get_policy(policy_id)` | `PolicyOut`: configuration, candidate ids, `frozen`, `pending_incident_id`, update counts |
| `freeze_policy(policy_id)` | Stop updating the policy |
| `snapshot_policy(policy_id)` | `PolicySnapshotOut` with the selector state (`A`, `b`, `n` per candidate) |

## Incidents

| Method | Purpose |
|---|---|
| `handle_fault(native_fault, adapter, policy_id, native_context=None, idempotency_key=None)` | The whole loop; returns a `FaultOutcome` |
| `handle_fault_async(...)` | The same, in a worker thread |
| `post_incident(event)` | Decide for one `FaultEventIn`; returns a `RecoveryCommandOut` |
| `post_result(result, idempotency_key)` | Score and learn from one `ExecutionResultIn`; returns an `OutcomeAckOut` |
| `incident(incident_id)` | `IncidentOut`: status, action, chosen candidate, eligible candidates, reward |
| `censor_expired(ttl_s=None)` | Close incidents waiting longer than the TTL without updating the policy; returns their ids. `ttl_s=0` closes every waiting incident |

## Errors

All importable from `arclayer`.

| Exception | Raised when |
|---|---|
| `NotFound` | unknown policy, incident or candidate |
| `Conflict` | duplicate candidate or policy id; a result reported again with a different key or payload; a result for a candidate other than the one commanded |
| `PolicyBusy` | a strictly sequential policy still has an incident waiting for its result |
| `FeatureMismatch` | the policy was created with a different feature spec or embedding model than the current one |
| `IllegalTransition` | an incident would move to a status its state machine forbids, for example a result for a censored incident |
| `InvalidRewardWeights` | reward weights break `w_c + w_l < w_s` or `w_v >= w_s` |
| `HostMisconfigured` | the command names a candidate the adapter has no executor for |

`ApplicationError` is the base class of `NotFound`, `Conflict`, `PolicyBusy` and `FeatureMismatch`. `DomainError` is the base class of `IllegalTransition` and `InvalidRewardWeights`. `HostMisconfigured` is a `RuntimeError`. Invalid messages raise pydantic's `ValidationError`.

## Threads and processes

One `ArcLayer` can be shared by several threads. Policy locks are per policy and live in the process, so give each database to one process.
