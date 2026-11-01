# Quickstart

A complete, runnable example with one recovery candidate (retry) and a host that fakes its own faults. It uses an in-memory store; pass a SQLite URL to `ArcLayer` to keep what the policy learns between runs.

```python
from datetime import datetime, timezone

from arclayer import ArcLayer
from arclayer.contracts import CandidateSpec, ExecutionResultIn, FaultEventIn, Terminal

retry = CandidateSpec(
    candidate_id="retry",
    version="1",
    description="Run the failed step again on the same agent",
    capabilities=["retry_step"],
    supported_classes="*",
    required_preconditions=["STEP_REPEATABLE"],
    optional_preconditions=[],
    required_host_capabilities=["retry_step"],
    max_cost=0.2,
    max_latency_ms=60_000,
    permissions=["rerun_step"],
    verifier_id="task_completed",
)


class RetryExecutor:
    candidate_id = "retry"

    def execute(self, command, native_context):
        recovered = native_context["rerun"]()  # your framework's own retry logic
        return ExecutionResultIn(
            incident_id=command.incident_id,
            candidate_id=self.candidate_id,
            terminal=Terminal.TASK_COMPLETED if recovered else Terminal.NEW_INCIDENT,
            cost_used=0.05,
            tokens_used=800,
            latency_ms=300,
            actions_performed=["rerun_step"],
        )


class MyAdapter:
    host_id = "demo"
    capabilities = ["retry_step"]

    def to_fault_event(self, native_fault, policy_instance_id):
        return FaultEventIn(
            run_id=native_fault["run"],
            task_id=native_fault["task"],
            step_index=native_fault["step"],
            occurred_at=datetime.now(timezone.utc),
            active_agent="researcher",
            agent_role="worker",
            orchestration="sequential",
            fault_class="tool_failure",
            label_source="deterministic",
            fault_description=native_fault["error"],
            budget_remaining_cost=2.0,
            time_remaining_ms=120_000,
            prior_incidents_in_task=0,
            host_id=self.host_id,
            policy_instance_id=policy_instance_id,
            host_capabilities=self.capabilities,
        )

    def executors(self):
        return {"retry": RetryExecutor()}


layer = ArcLayer(None, candidates=[retry])  # None keeps state in memory; pass a SQLite URL to keep learning
policy_id = layer.create_policy("P", seed=1)

fault = {"run": "r1", "task": "t1", "step": 3, "error": "tool timeout", "rerun": lambda: True}
outcome = layer.handle_fault(fault, MyAdapter(), policy_id)
print(outcome.command.action.value, outcome.ack.status, outcome.ack.reward)
```

Output: `execute recovered 0.9899`.

## What happened

1. `handle_fault` called `MyAdapter.to_fault_event` to build the fault context.
2. The gate checked the candidate against the policy's permissions, the host capabilities, the preconditions and the budget. `retry` passed, so LinUCB (the only candidate, so no real choice yet) selected it and returned an `execute` command.
3. `RetryExecutor.execute` ran in your process and reported cost, tokens, latency and what it did.
4. The verifier scored the result (`task_completed` needs no ground truth), the reward was `1 - 0.2 * (0.05 / 1.0) - 0.1 * (300 / 300000) = 0.9899`, and the policy was updated for `retry`.

With several candidates, LinUCB learns from these rewards which one to pick for which kind of fault.

## Next

- Registering more candidates and choosing a policy: [api-reference.md](api-reference.md).
- Executors and what the adapter must report: [host-adapter.md](host-adapter.md).
- A verifier that checks answers against ground truth: `register_ground_truth` and `verifier_id="benchmark_task_pass"`.
