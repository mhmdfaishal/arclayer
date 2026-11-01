# Contracts

Package `arclayer.contracts`. All models are Pydantic v2 with `extra="forbid"` and `frozen=True`, so an adapter cannot slip framework-internal fields into a message. A JSON Schema can be generated with `FaultEventIn.model_json_schema()`.

## Messages

| Model | Direction | Purpose |
|---|---|---|
| `FaultEventIn` | host to ArcLayer | The fault context for one incident |
| `RecoveryCommandOut` | ArcLayer to host | The decision: action, candidate, parameters, scores, rejected candidates, deadline |
| `ExecutionResultIn` | host to ArcLayer | What happened when the candidate ran |
| `OutcomeAckOut` | ArcLayer to host | `recovered`, `failed` or `escalate`, the reward, and whether the policy was updated |
| `CandidateSpec` | both | A recovery candidate and its attributes |
| `CreatePolicyIn`, `PolicyOut`, `PolicySnapshotOut` | both | Create and inspect a policy |
| `IncidentOut`, `VerificationOut` | ArcLayer to host | Read an incident back |
| `OracleIn` | host to ArcLayer | Ground truth for the benchmark verifier |

## Enums

`FaultClass`: `tool_failure`, `timeout`, `tool_output_unused`, `handoff_incomplete`, `plan_error`, `insufficient_verification`.
`OrchestrationPattern`: `centralized`, `sequential`, `concurrent`, `decentralized`.
`LabelSource`: `deterministic`, `injector`, `attribution`.
`Action`: `execute`, `safe_stop`, `escalate`.
`Terminal`: `task_completed`, `new_incident`, `budget_exhausted`, `executor_error`.
`PolicyKind`: the selection policies, including LinUCB and the baselines B0 to B4.

## `FaultEventIn`

| Group | Fields |
|---|---|
| Identity | `schema_version` (only `"1.0"` is accepted), `run_id`, `task_id`, `step_index`, `step_total_estimate`, `occurred_at` |
| Agent and pattern | `active_agent`, `agent_role`, `orchestration` |
| Fault | `fault_class` (may be `null`), `fault_confidence`, `label_source`, `fault_description` (max 4000 chars) |
| State | `last_messages_summary`, `checkpoint_id`, `checkpoint_restorable`, `step_repeatable`, `orchestrator_accessible`, `available_artifacts` |
| Tool | `tool_name`, `tool_error_code`, `tool_duration_ms` |
| Budget | `budget_remaining_cost`, `budget_remaining_tokens`, `time_remaining_ms`, `prior_incidents_in_task` |
| Integration | `host_id`, `policy_instance_id`, `host_capabilities` |

Notes that matter in practice:

- `prior_incidents_in_task` is counted by the host. ArcLayer trusts it when it applies the per-task incident cap (`n_max`).
- `step_repeatable` and `orchestrator_accessible` exist because two candidate preconditions cannot be evaluated without them.
- `fault_description` is embedded for the cosine feature. Text is redacted (API keys, bearer tokens, secrets in URL query strings, emails, home paths) before it is embedded or stored.

## `ExecutionResultIn`

`incident_id`, `candidate_id`, `terminal`, `final_answer`, `cost_used`, `tokens_used`, `latency_ms`, `actions_performed`, `artifacts`.

The host reports raw values. ArcLayer computes the verification itself, so a host cannot shape its own reward: `S = 1` only when the verifier says success and `terminal` is `task_completed`; `C` and `L` are cost and latency divided by the policy's per-incident caps and clipped to 1; `V = 1` when the candidate performed an action outside its `permissions` or exceeded its own `max_cost` or `max_latency_ms`.
