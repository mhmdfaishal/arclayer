# Data Contracts (Pydantic)

> Status note: translated from the original implementation plan (October 2026). The code may have diverged from this plan; see docs/architecture for the current structure.

All models use `model_config = ConfigDict(extra="forbid", frozen=True)` unless stated otherwise. `extra="forbid"` prevents adapters from silently slipping in framework-internal fields, which would violate the framework-agnostic claim.

## 5.1 Enums

```python
class FaultClass(StrEnum):
    TOOL_FAILURE = "tool_failure"
    TIMEOUT = "timeout"
    TOOL_OUTPUT_UNUSED = "tool_output_unused"
    HANDOFF_INCOMPLETE = "handoff_incomplete"
    PLAN_ERROR = "plan_error"
    INSUFFICIENT_VERIFICATION = "insufficient_verification"

class OrchestrationPattern(StrEnum):
    CENTRALIZED = "centralized"
    SEQUENTIAL = "sequential"
    CONCURRENT = "concurrent"
    DECENTRALIZED = "decentralized"

class LabelSource(StrEnum):
    DETERMINISTIC = "deterministic"   # timeout, tool exception
    INJECTOR = "injector"
    ATTRIBUTION = "attribution"       # frozen attribution procedure

class Action(StrEnum):
    EXECUTE = "execute"
    SAFE_STOP = "safe_stop"
    ESCALATE = "escalate"
```

The final list of classes is derived from the data (Problem Limitation 2 of the proposal). These enums are locked per `features/vN.yaml` version; adding a class means a new feature version and a new policy.

## 5.2 `FaultEvent` (Table 4)

```python
class FaultEvent(BaseModel):
    schema_version: Literal["1.0"]
    # execution and step identity
    run_id: str
    task_id: str
    step_index: int = Field(ge=0)
    step_total_estimate: int | None = None   # for the relative step position
    occurred_at: datetime
    # agent and pattern
    active_agent: str
    agent_role: str
    orchestration: OrchestrationPattern
    # fault class
    fault_class: FaultClass | None           # None = unknown
    fault_confidence: float | None = Field(default=None, ge=0, le=1)
    label_source: LabelSource
    fault_description: str = Field(max_length=4000)  # for the cosine embedding
    # state and checkpoint
    last_messages_summary: str = Field(max_length=4000)
    checkpoint_id: str | None
    checkpoint_restorable: bool
    available_artifacts: list[str] = []      # names of evidence artifacts, not their contents
    # tool
    tool_name: str | None = None
    tool_error_code: str | None = None
    tool_duration_ms: int | None = None
    # budget
    budget_remaining_cost: float = Field(ge=0)
    budget_remaining_tokens: int | None = None
    time_remaining_ms: int = Field(ge=0)
    prior_incidents_in_task: int = Field(ge=0)
    # integration
    host_id: str
    policy_instance_id: str
    host_capabilities: list[str]             # e.g. ["rollback", "replan", "retry_step"]
```

The "Candidates and metadata" group in Table 4 is **not** resent with every incident; the host only sends `host_capabilities`, while candidate metadata lives in the registry. This reduces duplication and the risk of inconsistency.

## 5.3 `CandidateSpec` (registry, Table 6)

```python
class CandidateSpec(BaseModel):
    candidate_id: str                         # "h1_retry"
    version: str
    description: str                          # embedded for g(t,h)
    capabilities: list[str]
    supported_classes: list[FaultClass] | Literal["*"]
    required_preconditions: list[Precondition]   # hard filter
    optional_preconditions: list[Precondition] = []  # soft feature
    required_host_capabilities: list[str]
    max_cost: float = Field(gt=0)             # in normalized cost units
    max_latency_ms: int = Field(gt=0)
    permissions: list[str]                    # must be a subset of the gate allowlist
    verifier_id: str                          # reference to a registered verifier
    enabled: bool = True
```

`Precondition` is a closed enum (`STEP_REPEATABLE`, `TOOL_STATUS_AVAILABLE`, `ORCHESTRATOR_MESSAGE_ACCESS`, `STATE_SUMMARY_AVAILABLE`, `EVIDENCE_ARTIFACT_AVAILABLE`, `CHECKPOINT_AVAILABLE`), each with a pure evaluation function over `FaultContext`. The candidate's execution function is **not** defined here, because execution belongs to the host (see 7.1).

Example `configs/candidates/default.yaml`:

```yaml
- candidate_id: h1_retry
  version: "1"
  description: Re-runs the failed step on the same agent
  capabilities: [retry_step]
  supported_classes: "*"
  required_preconditions: [STEP_REPEATABLE]
  required_host_capabilities: [retry_step]
  max_cost: 0.15
  max_latency_ms: 60000
  permissions: [rerun_step]
  verifier_id: benchmark_task_pass
- candidate_id: h6_guided_rollback
  version: "1"
  description: Returns to the checkpoint before the fault with one-step repair guidance
  capabilities: [rollback, guided_repair]
  supported_classes: [plan_error, handoff_incomplete]
  required_preconditions: [CHECKPOINT_AVAILABLE]
  required_host_capabilities: [rollback]
  max_cost: 0.40
  max_latency_ms: 180000
  permissions: [load_checkpoint, inject_guidance]
  verifier_id: benchmark_task_pass
# h2..h5 follow Table 6
```

## 5.4 `RecoveryCommand`

```python
class ScoreBreakdown(BaseModel):
    candidate_id: str
    estimate: float        # theta_h' x
    bonus: float           # alpha * sqrt(x' A^-1 x)
    score: float
    features: list[float]  # x_t,h, for audit

class RecoveryCommand(BaseModel):
    incident_id: UUID
    action: Action
    candidate_id: str | None
    parameters: dict[str, JsonScalar]     # e.g. target checkpoint_id, guidance_template_id
    verification_conditions: list[str]
    scores: list[ScoreBreakdown]          # empty for non-score baselines
    excluded: list[GateRejection]         # candidates rejected by the gate + reason
    reason: str
    deadline_ms: int
```

## 5.5 `ExecutionResult`, `VerificationResult`, `OutcomeAck`

```python
class ExecutionResult(BaseModel):
    incident_id: UUID
    candidate_id: str
    terminal: Literal["task_completed", "new_incident", "budget_exhausted", "executor_error"]
    final_answer: str | None              # for the benchmark verifier
    cost_used: float = Field(ge=0)
    tokens_used: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    actions_performed: list[str]          # for permission violation checks
    artifacts: dict[str, str] = {}
    next_incident_hint: bool = False

class VerificationResult(BaseModel):
    S: Literal[0, 1]
    C: float = Field(ge=0, le=1)          # min(cost/cap, 1)
    L: float = Field(ge=0, le=1)          # min(latency/cap, 1)
    V: Literal[0, 1]
    details: dict[str, str]

class OutcomeAck(BaseModel):
    incident_id: UUID
    status: Literal["recovered", "failed", "escalate"]
    reward: float
    policy_updated: bool
```

`V = 1` when `actions_performed` contains actions outside the candidate's `permissions`, or when the candidate's cost/latency limits are exceeded. This is the second safeguard described in the proposal; the first safeguard is the gate.

All schemas are exported to `contracts/schema/*.json` (JSON Schema) so that non-Python adapters can validate against them.
