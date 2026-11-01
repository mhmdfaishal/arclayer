# Runtime errors

All the exception classes below are importable from `arclayer`.

| Symptom | Cause | Fix |
|---|---|---|
| Every command is `safe_stop` and nothing runs | The gate rejected every candidate. Look at `command.excluded`: each entry has a reason code | `PERMISSION_NOT_ALLOWED`: add the permission to `allowed_permissions` or register candidates before `create_policy`. `HOST_CAPABILITY_MISSING`: add the capability to the adapter's `capabilities`. `PRECONDITION_UNMET`: check the event fields behind the failed precondition: `step_repeatable`, `checkpoint_restorable`, `orchestrator_accessible`, `available_artifacts`, `last_messages_summary`, and the tool fields. `OVER_BUDGET`: the candidate's `max_cost` or `max_latency_ms` exceeds what the event says is left. `DISABLED`: the candidate was disabled. `INCIDENT_LIMIT`: `prior_incidents_in_task` reached `n_max`, and the action is `escalate` |
| `PolicyBusy` | The policy is strictly sequential and an earlier incident is still waiting for its result | Report that result. If the process that held it is gone, call `censor_expired(ttl_s=0)`. For concurrent agents use the default `strict_sequential=False` |
| `ValidationError` (pydantic) from an adapter | The event or result has an unknown field, a wrong enum value or a missing field. Contracts reject extra fields | Compare with [contracts.md](../integration/contracts.md) and remove framework-internal fields from the event |
| `HostMisconfigured` | The command names a candidate the adapter has no executor for | Add the executor to `adapter.executors()`. Nothing was reported, so the incident stays waiting until it is censored |
| `Conflict` on a result | The same incident was already reported with a different key or payload, or the result names a candidate other than the one commanded | Use one idempotency key per incident and candidate, and resend the identical payload when retrying |
| `IllegalTransition` on a result | The incident is no longer waiting: it was censored, or already finished | A result that arrives after censoring is rejected by design. Report within `censor_ttl_s` |
| `FeatureMismatch` | The policy was created with a different feature spec or embedding model than the current `ArcLayer` uses | Create a new policy, or restore the original `embedding` argument |
| `NotFound` | Unknown policy, incident or candidate id | Check the id, and the `db_url` you opened |
| `InvalidRewardWeights` | Reward weights break `w_c + w_l < w_s` or `w_v >= w_s` | Adjust the weights |
| An incident from the last run shows `censored` | A new `ArcLayer` closes incidents a previous process left waiting (`censor_orphans_on_start`) | Expected after a crash. If two `ArcLayer` objects share one database in the same process, the second one closes the first one's in-flight incidents: use one object per database, or pass `censor_orphans_on_start=False` |
| A candidate you disabled is still chosen | A policy keeps the candidates that were enabled when it was created | Create a new policy. Disabling affects only policies created afterwards |
| A candidate stops being preferred after host errors | An exception in an executor is reported as `executor_error` and scored as a failed attempt (reward about zero), so the candidate earns no credit and ArcLayer prefers candidates that succeed. A transient host failure is counted the same way | Known behaviour; see [failure handling alignment](../development/research/failure-handling-alignment.md) |
| Learning is lost after a restart | `db_url=None` keeps state in memory, or `db_url` points at a relative path in a different working directory | Pass an absolute SQLite path |
