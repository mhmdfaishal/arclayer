from __future__ import annotations

from datetime import datetime, timezone

import pytest

import arclayer.contracts as C
from arclayer.domain import enums as D
from arclayer.delivery.inprocess import InProcessControlPlaneClient
from arclayer.delivery.mappers import candidate_from_spec, candidate_to_spec, create_policy_cmd, event_from_in
from tests.factories import table6_candidates
from tests.unit.usecases.conftest import make_harness


@pytest.mark.parametrize(
    "contract,domain",
    [
        (C.FaultClass, D.FaultClass), (C.OrchestrationPattern, D.OrchestrationPattern),
        (C.LabelSource, D.LabelSource), (C.Action, D.Action), (C.Precondition, D.Precondition),
        (C.Terminal, D.Terminal), (C.PolicyKind, D.PolicyKind),
    ],
)
def test_contract_enums_mirror_domain_enums_in_order(contract, domain):
    assert [m.value for m in contract] == [m.value for m in domain]


def test_candidate_roundtrip():
    for c in table6_candidates():
        assert candidate_from_spec(candidate_to_spec(c)) == c


def test_wildcard_supported_classes_maps_to_none():
    spec = candidate_to_spec(table6_candidates()[0])
    assert spec.supported_classes == "*"


def _event_in(policy_id: str, **kw) -> C.FaultEventIn:
    base = dict(
        run_id="r1", task_id="task-1", step_index=2, occurred_at=datetime(2026, 10, 14, tzinfo=timezone.utc),
        active_agent="coder", agent_role="worker", orchestration="sequential", fault_class="tool_failure",
        label_source="injector", fault_description="tool crashed", last_messages_summary="x",
        checkpoint_id="c1", checkpoint_restorable=True, tool_name="python", budget_remaining_cost=2.0,
        time_remaining_ms=600_000, prior_incidents_in_task=0, host_id="h", policy_instance_id=policy_id,
        host_capabilities=["retry_step", "repair_tool", "rollback"],
    )
    base.update(kw)
    return C.FaultEventIn(**base)


def test_event_mapping_produces_domain_types():
    ev = event_from_in(_event_in("p"))
    assert ev.orchestration is D.OrchestrationPattern.SEQUENTIAL
    assert isinstance(ev.host_capabilities, tuple)


def test_fault_event_rejects_extra_fields():
    with pytest.raises(Exception):
        _event_in("p", langgraph_state={"x": 1})


def test_inprocess_client_full_cycle():
    h = make_harness()
    pol_in = C.CreatePolicyIn(
        kind="P", seed=1, feature_spec=C.FeatureSpecIn(step_cap=20, budget_task_cap=3.0, n_max=1),
        allowed_permissions=sorted({p for c in table6_candidates() for p in c.permissions}), n_max=1,
        caps=C.BudgetCapsIn(incident_cost_cap=1.0, incident_latency_cap_ms=300_000, task_cost_cap=3.0),
    )
    pol = h.svc.create_policy.execute(create_policy_cmd(pol_in))
    client = InProcessControlPlaneClient(h.svc)
    h.svc.register_oracle_answer.execute("task-1", "ok")

    cmd = client.post_incident(_event_in(pol.policy_id))
    assert cmd.action is C.Action.EXECUTE
    ack = client.post_result(
        C.ExecutionResultIn(
            incident_id=cmd.incident_id, candidate_id=cmd.candidate_id, terminal="task_completed",
            final_answer="ok", cost_used=0.05, tokens_used=1, latency_ms=1000,
        ),
        idempotency_key="k",
    )
    assert ack.status == "recovered" and ack.policy_updated
