from dataclasses import replace

from arclayer.domain.enums import Action, Precondition, RejectionCode
from arclayer.domain.gate import GateConfig, evaluate_gate
from tests.factories import ALL_PERMISSIONS, make_candidate, make_event, table6_candidates

CFG = GateConfig(allowed_permissions=ALL_PERMISSIONS, n_max=2)


def _codes(result):
    return {r.candidate_id: r.code for r in result.rejections}


def test_healthy_event_passes_candidates_whose_preconditions_hold():
    res = evaluate_gate(make_event(), table6_candidates(), CFG)
    assert {c.candidate_id for c in res.eligible} == {
        "h1_retry", "h2_tool_repair", "h3_replanner", "h4_handoff_completer",
        "h5_verification_reviewer", "h6_guided_rollback",
    }
    assert res.empty_action is None


def test_class_support_is_not_a_hard_filter():
    # Kelas yang didukung adalah fitur lunak (class_match), bukan filter gate.
    # h3 hanya mendukung plan_error tetapi tetap lolos untuk tool_failure.
    res = evaluate_gate(make_event(), table6_candidates(), CFG)
    assert "h3_replanner" in {c.candidate_id for c in res.eligible}


def test_disabled():
    res = evaluate_gate(make_event(), (make_candidate(enabled=False),), CFG)
    assert _codes(res) == {"h1_retry": RejectionCode.DISABLED}


def test_permission_not_allowed():
    res = evaluate_gate(make_event(), (make_candidate(permissions=("rm_rf",)),), CFG)
    assert _codes(res) == {"h1_retry": RejectionCode.PERMISSION_NOT_ALLOWED}


def test_host_capability_missing():
    res = evaluate_gate(make_event(host_capabilities=("replan",)), (make_candidate(),), CFG)
    assert _codes(res) == {"h1_retry": RejectionCode.HOST_CAPABILITY_MISSING}


def test_precondition_unmet_checkpoint():
    cand = make_candidate(required_preconditions=(Precondition.CHECKPOINT_AVAILABLE,))
    res = evaluate_gate(make_event(checkpoint_id=None, checkpoint_restorable=False), (cand,), CFG)
    assert _codes(res) == {"h1_retry": RejectionCode.PRECONDITION_UNMET}


def test_checkpoint_id_present_but_not_restorable_is_unmet():
    cand = make_candidate(required_preconditions=(Precondition.CHECKPOINT_AVAILABLE,))
    res = evaluate_gate(make_event(checkpoint_restorable=False), (cand,), CFG)
    assert _codes(res) == {"h1_retry": RejectionCode.PRECONDITION_UNMET}


def test_over_budget_cost_and_time():
    r1 = evaluate_gate(make_event(budget_remaining_cost=0.1), (make_candidate(max_cost=0.15),), CFG)
    r2 = evaluate_gate(make_event(time_remaining_ms=1000), (make_candidate(max_latency_ms=60_000),), CFG)
    assert _codes(r1) == {"h1_retry": RejectionCode.OVER_BUDGET}
    assert _codes(r2) == {"h1_retry": RejectionCode.OVER_BUDGET}


def test_first_failing_rule_is_reported():
    cand = make_candidate(enabled=False, permissions=("rm_rf",))
    assert _codes(evaluate_gate(make_event(), (cand,), CFG)) == {"h1_retry": RejectionCode.DISABLED}


def test_incident_limit_rejects_all_and_escalates():
    res = evaluate_gate(make_event(prior_incidents_in_task=2), table6_candidates(), CFG)
    assert res.eligible == ()
    assert set(_codes(res).values()) == {RejectionCode.INCIDENT_LIMIT}
    assert res.empty_action is Action.ESCALATE


def test_empty_due_to_budget_escalates():
    res = evaluate_gate(make_event(budget_remaining_cost=0.01), table6_candidates(), CFG)
    assert res.eligible == ()
    assert res.empty_action is Action.ESCALATE


def test_empty_due_to_other_reasons_safe_stops():
    res = evaluate_gate(make_event(host_capabilities=()), table6_candidates(), CFG)
    assert res.eligible == ()
    assert res.empty_action is Action.SAFE_STOP


def test_gate_is_pure():
    ev, cands = make_event(), table6_candidates()
    snapshot = (replace(ev), tuple(replace(c) for c in cands))
    a = evaluate_gate(ev, cands, CFG)
    b = evaluate_gate(ev, cands, CFG)
    assert a == b
    assert (ev, cands) == snapshot
