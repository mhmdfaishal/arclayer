# Host adapter and executors

Package `arclayer.host`. It imports only `arclayer.contracts`. Everything here is also importable from `arclayer`.

## Protocols to implement

```python
class HostAdapter(Protocol):
    host_id: str
    capabilities: list[str]          # e.g. ["retry_step", "rollback", "replan"]

    def to_fault_event(self, native_fault: Any, policy_instance_id: str) -> FaultEventIn: ...
    def executors(self) -> Mapping[str, RecoveryExecutor]: ...


class RecoveryExecutor(Protocol):
    candidate_id: str

    def execute(self, command: RecoveryCommandOut, native_context: Any) -> ExecutionResultIn: ...
```

`capabilities` is what the gate compares with each candidate's `required_host_capabilities`. A candidate whose capability the host does not declare is never offered.

## The loop

```python
outcome = layer.handle_fault(native_fault, adapter, policy_id)
```

`handle_fault` does this, in order:

1. `adapter.to_fault_event(...)`, then `post_incident(event)`.
2. If the command is `safe_stop` or `escalate`, it returns without executing or reporting anything. What the host does next is the host's decision.
3. Otherwise it looks up the executor for `command.candidate_id`. If the host has none, it raises `HostMisconfigured` **before** executing and reports nothing; the incident stays waiting until it is censored, so a wiring mistake is not counted as a failure of the candidate.
4. It runs `executor.execute(command, native_context)`. `native_context` defaults to the native fault you passed in. The executor must fill `cost_used`, `tokens_used` and `latency_ms`; measure latency in the host, around the actual execution.
5. If the executor raises, the exception is reported as `terminal="executor_error"` with zero cost, and it goes through normal verification and reward. The result is a failure with a reward of about zero: the candidate earns no credit, even when the cause was the host rather than the candidate. See [failure handling alignment](../development/research/failure-handling-alignment.md).
6. It reports the result with an idempotency key (default `"<incident_id>:<candidate_id>"`) and returns a `FaultOutcome(command, result, ack)`.

## What the executor must report truthfully

- `actions_performed`: every action the candidate took. If an action is not in the candidate's `permissions`, the verifier sets `V = 1` and the reward turns negative.
- `terminal`: `task_completed`, `new_incident` (recovery raised another fault, which you then send as a new incident), `budget_exhausted` or `executor_error`.
- `final_answer`: only needed when the verifier checks answers against ground truth. Ground truth never reaches the host.

ArcLayer cannot check these statements. It computes `S`, `C`, `L` and `V` itself from what the host reports, so a host cannot shape its own reward, but it can still report wrongly.

## Async frameworks

`await layer.handle_fault_async(native_fault, adapter, policy_id)` runs the same loop in a worker thread. Executors stay synchronous functions; if your recovery logic is async, wrap it inside the executor (for example with `asyncio.run` in the worker thread).

## Calling the steps yourself

`post_incident(event)` and `post_result(result, idempotency_key)` are public. Use them when the host cannot run the candidate inside one call, for example when execution happens in another thread or later. The idempotency key makes a repeated report safe: the same key and payload return the stored acknowledgement, and a different payload under the same key raises `Conflict`.
