from __future__ import annotations

from datetime import datetime, timezone

import pytest

import arclayer.contracts as C
from arclayer.host.runtime import FaultOutcome, HostMisconfigured, handle_fault


def _event(pid: str) -> C.FaultEventIn:
    return C.FaultEventIn(
        run_id="r", task_id="t1", step_index=1, occurred_at=datetime(2026, 10, 14, tzinfo=timezone.utc),
        active_agent="a", agent_role="worker", orchestration="sequential", fault_class="tool_failure",
        label_source="injector", fault_description="x", budget_remaining_cost=1.0, time_remaining_ms=1000,
        prior_incidents_in_task=0, host_id="h", policy_instance_id=pid, host_capabilities=["retry_step"],
    )


def _cmd(action="execute", cid="h1_retry") -> C.RecoveryCommandOut:
    return C.RecoveryCommandOut(
        incident_id="i1", action=action, candidate_id=cid if action == "execute" else None, parameters={},
        verification_conditions=[], scores=[], excluded=[], reason="", deadline_ms=10,
    )


class FakeClient:
    def __init__(self, cmd):
        self.cmd = cmd
        self.results: list[tuple[C.ExecutionResultIn, str]] = []

    def post_incident(self, event):
        self.event = event
        return self.cmd

    def post_result(self, result, idempotency_key):
        self.results.append((result, idempotency_key))
        return C.OutcomeAckOut(incident_id=result.incident_id, status="recovered", reward=0.5, policy_updated=True)


class OkExecutor:
    candidate_id = "h1_retry"

    def __init__(self):
        self.ctx = None

    def execute(self, command, native_context):
        self.ctx = native_context
        return C.ExecutionResultIn(
            incident_id=command.incident_id, candidate_id=self.candidate_id, terminal="task_completed",
            final_answer="PASS", cost_used=0.1, tokens_used=0, latency_ms=7,
        )


class BoomExecutor:
    candidate_id = "h1_retry"

    def execute(self, command, native_context):
        raise RuntimeError("kaboom")


class FakeAdapter:
    host_id = "h"
    capabilities = ["retry_step"]

    def __init__(self, executors):
        self._ex = executors

    def to_fault_event(self, native_fault, policy_instance_id):
        return _event(policy_instance_id)

    def executors(self):
        return self._ex


def test_execute_path_reports_result_with_idempotency_key():
    ex = OkExecutor()
    client = FakeClient(_cmd())
    out = handle_fault("native", FakeAdapter({"h1_retry": ex}), client, "pol-1", idempotency_key="K")
    assert isinstance(out, FaultOutcome)
    assert out.result.final_answer == "PASS" and out.ack.status == "recovered"
    assert client.results[0][1] == "K"
    assert client.event.policy_instance_id == "pol-1"
    # tanpa native_context eksplisit, executor menerima insiden native-nya
    assert ex.ctx == "native"


def test_explicit_native_context_is_passed_through():
    ex = OkExecutor()
    handle_fault("native", FakeAdapter({"h1_retry": ex}), FakeClient(_cmd()), "p", native_context="ctx")
    assert ex.ctx == "ctx"


def test_default_idempotency_key_is_derived_from_incident():
    client = FakeClient(_cmd())
    handle_fault("n", FakeAdapter({"h1_retry": OkExecutor()}), client, "p")
    assert client.results[0][1] == "i1:h1_retry"


@pytest.mark.parametrize("action", ["safe_stop", "escalate"])
def test_non_execute_action_skips_execution(action):
    client = FakeClient(_cmd(action))
    out = handle_fault("n", FakeAdapter({}), client, "p")
    assert out.result is None and out.ack is None and out.command.action.value == action
    assert client.results == []


def test_executor_exception_is_reported_as_executor_error():
    client = FakeClient(_cmd())
    out = handle_fault("n", FakeAdapter({"h1_retry": BoomExecutor()}), client, "p")
    r = out.result
    assert r.terminal is C.Terminal.EXECUTOR_ERROR and r.final_answer is None
    assert r.cost_used == 0 and r.latency_ms >= 0 and r.candidate_id == "h1_retry" and r.incident_id == "i1"
    assert client.results and out.ack is not None


def test_unknown_candidate_is_host_misconfiguration():
    client = FakeClient(_cmd(cid="h3_replanner"))
    with pytest.raises(HostMisconfigured, match="h3_replanner"):
        handle_fault("n", FakeAdapter({"h1_retry": OkExecutor()}), client, "p")
    assert client.results == []
