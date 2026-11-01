# One incident, end to end

1. The host detects a fault and calls `ArcLayer.handle_fault(native_fault, adapter, policy_id)`. The host adapter turns its native fault into a `FaultEventIn`.
2. `post_incident` validates the event against the contract and maps it to a domain event.
3. `HandleIncident.execute` (`usecases/incidents.py`) does the following inside one transaction:
   - redacts sensitive text (`redact_event`);
   - raises `PolicyBusy` if the policy is strictly sequential and another incident is still waiting for its result;
   - runs the gate (`evaluate_gate`) over the candidates snapshotted into the policy;
   - builds one feature vector per eligible candidate;
   - asks the selector (`LinUCB` or a baseline) to choose one candidate;
   - stores the decision and the audit record, and sets the status to `awaiting_result`.
4. The result is a `RecoveryCommandOut` with action `execute`, `safe_stop` or `escalate`, the chosen `candidate_id`, its parameters, the score breakdown and the candidates the gate rejected with a reason code.
5. For `execute`, the host runs the candidate with its own executor and measures cost, tokens and latency itself. For `safe_stop` and `escalate` nothing is executed and nothing is reported.
6. The result goes back through `post_result` with an idempotency key. `ReportResult.execute`:
   - returns the stored acknowledgement if the same key and the same payload arrive again, and raises `Conflict` if the key is reused with a different payload;
   - verifies the result (`S`, `C`, `L`, `V`) and computes the reward `r = w_s*S - w_c*C - w_l*L - w_v*V`;
   - updates the selector **only for the chosen candidate** (`A += x x^T`, `b += r x`), unless the policy is frozen;
   - moves the incident to `recovered`, `failed` or `escalated` and returns an `OutcomeAckOut`.

`handle_fault` runs steps 1 to 6 for you. `post_incident` and `post_result` are public too, for hosts that need to separate the steps.

## Incident status

`received`, `awaiting_result`, `recovered`, `failed`, `safe_stopped`, `escalated`, `censored`. Transitions are table-driven in `domain/state_machine.py`; an illegal transition raises `IllegalTransition`. The statuses between receiving an event and returning a command happen inside one transaction and are not visible from outside.

## Incidents that never get a result

If the host never reports a result, the incident stays `awaiting_result`. Censoring closes it as `censored` without updating the policy, because treating a missing result as a failure would bias the estimates. It happens in two places:

- when an `ArcLayer` is created, every incident a previous process left waiting is censored (`censor_orphans_on_start`, on by default), since a process that is gone can never report;
- when you call `censor_expired(ttl_s)`, for incidents waiting longer than the TTL (`censor_ttl_s`, default 3600 seconds).

A result that arrives after censoring is rejected.

## Concurrency

Policies created through `ArcLayer.create_policy` accept overlapping incidents by default (`strict_sequential=False`), so agents running in parallel can share one policy. Each policy has a lock inside the process, and the decision and the update are separate transactions. With `strict_sequential=True` a second incident raises `PolicyBusy` until the first reports; experiments use that for reproducibility.

`handle_fault_async` runs the same loop in a worker thread so an async framework's event loop is not blocked.

## What is persisted

Incidents, policy instances (candidate snapshot, selector state `A` and `b`, RNG state, feature hash, embedding model id) and the append-only audit table. Each policy keeps the candidates that were enabled when it was created, so registering or disabling a candidate later does not change a running policy.
