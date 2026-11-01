from __future__ import annotations

import json

import numpy as np
import pytest

from arclayer.usecases.errors import Conflict, FeatureMismatch, NotFound, PolicyBusy
from arclayer.usecases.services.serialization import to_jsonable
from arclayer.domain.enums import Action, FeatureVariant, IncidentStatus, PolicyKind, Terminal
from arclayer.domain.errors import IllegalTransition, InvalidRewardWeights
from arclayer.domain.models import ExecutionResult
from arclayer.domain.reward import RewardWeights
from arclayer.apiclients.embedding.hashing import HashingEmbeddingProvider
from tests.factories import make_event
from tests.unit.usecases.conftest import make_harness, policy_cmd


def _result(cmd, **kw):
    base = dict(
        incident_id=cmd.incident_id, candidate_id=cmd.candidate_id, terminal=Terminal.TASK_COMPLETED,
        final_answer="42", cost_used=0.1, tokens_used=10, latency_ms=30_000,
        actions_performed=(), artifacts={},
    )
    base.update(kw)
    return ExecutionResult(**base)


def _new_policy(h, kind=PolicyKind.P, **kw):
    return h.svc.create_policy.execute(policy_cmd(kind, **kw))


# ---------- CreatePolicy ----------

def test_create_policy_snapshots_enabled_candidates_only(h):
    h.svc.set_candidate_enabled.execute("h5_verification_reviewer", False)
    pol = _new_policy(h)
    assert "h5_verification_reviewer" not in {c.candidate_id for c in pol.candidates}


def test_pd_uses_no_candidate_variant_and_pf_is_frozen(h):
    pd = _new_policy(h, PolicyKind.P_D)
    pf = _new_policy(h, PolicyKind.P_F)
    assert pd.variant is FeatureVariant.NO_CANDIDATE and pd.selector_state["d"] == 17
    assert pf.frozen is True and pf.selector_state["frozen"] is True


def test_create_policy_rejects_invalid_reward_weights(h):
    with pytest.raises(InvalidRewardWeights):
        _new_policy(h, reward_weights=RewardWeights(1, 0.8, 0.5, 1))


def test_init_state_from_snapshot_with_other_candidates_rejected(h):
    pol = _new_policy(h)
    snap = h.svc.snapshot_policy.execute(pol.policy_id)
    snap["selector_state"]["A"].pop("h1_retry")
    with pytest.raises(ValueError):
        _new_policy(h, init_state=snap["selector_state"])


def test_create_policy_with_existing_id_conflicts_instead_of_overwriting(h):
    pol = _new_policy(h, policy_id="fixed")
    with pytest.raises(Conflict):
        _new_policy(h, PolicyKind.B3, policy_id="fixed")
    assert h.svc.get_policy.execute(pol.policy_id).kind is PolicyKind.P


def test_registry_change_after_creation_does_not_affect_policy(h):
    pol = _new_policy(h)
    h.svc.set_candidate_enabled.execute("h1_retry", False)
    again = h.svc.get_policy.execute(pol.policy_id)
    assert next(c for c in again.candidates if c.candidate_id == "h1_retry").enabled is True


# ---------- HandleIncident ----------

def test_unknown_policy_is_not_found(h):
    with pytest.raises(NotFound):
        h.svc.handle_incident.execute(make_event(policy_instance_id="nope"))


def test_b0_safe_stops_without_gate_or_pending(h):
    pol = _new_policy(h, PolicyKind.B0)
    cmd = h.svc.handle_incident.execute(make_event(policy_instance_id=pol.policy_id))
    assert cmd.action is Action.SAFE_STOP and cmd.candidate_id is None
    assert h.svc.get_incident.execute(cmd.incident_id).status is IncidentStatus.SAFE_STOPPED
    assert h.svc.get_policy.execute(pol.policy_id).pending_incident_id is None


def test_p_executes_eligible_candidate_with_score_breakdown(h):
    pol = _new_policy(h)
    cmd = h.svc.handle_incident.execute(make_event(policy_instance_id=pol.policy_id))
    inc = h.svc.get_incident.execute(cmd.incident_id)
    assert cmd.action is Action.EXECUTE
    assert cmd.candidate_id in {a.candidate_id for a in inc.arms}
    assert len(cmd.scores) == len(inc.arms) == 6
    assert all(len(a.x) == 20 for a in inc.arms)
    assert inc.status is IncidentStatus.AWAITING_RESULT
    assert h.svc.get_policy.execute(pol.policy_id).pending_incident_id == cmd.incident_id


def test_rollback_command_carries_checkpoint_parameter(h):
    pol = _new_policy(h, PolicyKind.B2)
    from arclayer.domain.enums import FaultClass

    cmd = h.svc.handle_incident.execute(
        make_event(policy_instance_id=pol.policy_id, fault_class=FaultClass.PLAN_ERROR, orchestrator_accessible=False)
    )
    assert cmd.candidate_id == "h6_guided_rollback"
    assert cmd.parameters["checkpoint_id"] == "ckpt-3"


def test_empty_gate_returns_escalate_and_records_rejections(h):
    pol = _new_policy(h)
    cmd = h.svc.handle_incident.execute(make_event(policy_instance_id=pol.policy_id, prior_incidents_in_task=2))
    assert cmd.action is Action.ESCALATE
    assert len(cmd.excluded) == 6
    assert h.svc.get_incident.execute(cmd.incident_id).status is IncidentStatus.ESCALATED


def test_b1_safe_stops_when_retry_not_eligible(h):
    pol = _new_policy(h, PolicyKind.B1)
    cmd = h.svc.handle_incident.execute(make_event(policy_instance_id=pol.policy_id, step_repeatable=False))
    assert cmd.action is Action.SAFE_STOP


def test_strict_sequential_rejects_second_incident_while_pending(h):
    pol = _new_policy(h)
    h.svc.handle_incident.execute(make_event(policy_instance_id=pol.policy_id))
    with pytest.raises(PolicyBusy):
        h.svc.handle_incident.execute(make_event(policy_instance_id=pol.policy_id, run_id="run-2"))


def test_non_strict_allows_concurrent_incidents(h):
    pol = _new_policy(h, strict_sequential=False)
    h.svc.handle_incident.execute(make_event(policy_instance_id=pol.policy_id))
    h.svc.handle_incident.execute(make_event(policy_instance_id=pol.policy_id, run_id="run-2"))


def test_embedding_model_mismatch_rejected(h):
    pol = _new_policy(h)
    h.svc.handle_incident.embedder = HashingEmbeddingProvider(dim=32)
    with pytest.raises(FeatureMismatch):
        h.svc.handle_incident.execute(make_event(policy_instance_id=pol.policy_id))


def test_secrets_are_redacted_before_storage_and_audit(h):
    pol = _new_policy(h)
    cmd = h.svc.handle_incident.execute(make_event(
        policy_instance_id=pol.policy_id,
        fault_description="call failed with Authorization: Bearer sk-ant-abcdef1234567890XYZ",
    ))
    inc = h.svc.get_incident.execute(cmd.incident_id)
    dump = json.dumps(to_jsonable(inc)) + json.dumps(h.store.audit_records)
    assert "sk-ant-abcdef1234567890XYZ" not in dump
    assert "[REDACTED" in inc.event.fault_description


def test_oracle_answer_never_leaks_into_command_or_incident(h):
    pol = _new_policy(h)
    h.svc.register_oracle_answer.execute("task-1", "SECRET-ANSWER-123")
    cmd = h.svc.handle_incident.execute(make_event(policy_instance_id=pol.policy_id))
    inc = h.svc.get_incident.execute(cmd.incident_id)
    assert "SECRET-ANSWER-123" not in json.dumps(to_jsonable(cmd))
    assert "SECRET-ANSWER-123" not in json.dumps(to_jsonable(inc.event))


def test_same_seed_gives_same_decision_sequence():
    def run():
        h = make_harness()
        pol = _new_policy(h, PolicyKind.B3)
        out = []
        for i in range(10):
            cmd = h.svc.handle_incident.execute(make_event(policy_instance_id=pol.policy_id, run_id=f"r{i}"))
            h.svc.report_result.execute(_result(cmd), idempotency_key=f"k{i}")
            out.append(cmd.candidate_id)
        return out

    assert run() == run()


# ---------- ReportResult ----------

def test_success_recovers_updates_only_chosen_arm_and_clears_pending(h):
    pol = _new_policy(h)
    h.svc.register_oracle_answer.execute("task-1", "42")
    before = h.svc.snapshot_policy.execute(pol.policy_id)["selector_state"]
    cmd = h.svc.handle_incident.execute(make_event(policy_instance_id=pol.policy_id))
    ack = h.svc.report_result.execute(_result(cmd), idempotency_key="k1")
    after = h.svc.snapshot_policy.execute(pol.policy_id)["selector_state"]

    assert ack.status == "recovered" and ack.policy_updated is True
    assert ack.reward == pytest.approx(1 - 0.2 * 0.1 - 0.1 * 0.1)
    changed = {cid for cid in after["A"] if after["A"][cid] != before["A"][cid]}
    assert changed == {cmd.candidate_id}
    assert h.svc.get_policy.execute(pol.policy_id).pending_incident_id is None
    rec = h.store.audit_records[-1]
    assert rec["event"] == "result" and rec["checksum_before"] != rec["checksum_after"]


def test_wrong_answer_is_not_recovered(h):
    pol = _new_policy(h)
    h.svc.register_oracle_answer.execute("task-1", "41")
    cmd = h.svc.handle_incident.execute(make_event(policy_instance_id=pol.policy_id))
    ack = h.svc.report_result.execute(_result(cmd), idempotency_key="k1")
    assert ack.status != "recovered" and ack.reward < 0


def test_new_incident_terminal_fails_or_escalates_by_incident_limit(h):
    pol = _new_policy(h)
    cmd = h.svc.handle_incident.execute(make_event(policy_instance_id=pol.policy_id, prior_incidents_in_task=0))
    assert h.svc.report_result.execute(_result(cmd, terminal=Terminal.NEW_INCIDENT), "k1").status == "failed"
    cmd = h.svc.handle_incident.execute(make_event(policy_instance_id=pol.policy_id, prior_incidents_in_task=1))
    assert h.svc.report_result.execute(_result(cmd, terminal=Terminal.NEW_INCIDENT), "k2").status == "escalate"


def test_duplicate_result_same_key_is_idempotent(h):
    pol = _new_policy(h)
    cmd = h.svc.handle_incident.execute(make_event(policy_instance_id=pol.policy_id))
    a1 = h.svc.report_result.execute(_result(cmd), "k1")
    a2 = h.svc.report_result.execute(_result(cmd), "k1")
    assert a1 == a2
    assert h.svc.snapshot_policy.execute(pol.policy_id)["selector_state"]["n"][cmd.candidate_id] == 1


def test_duplicate_result_different_payload_conflicts(h):
    pol = _new_policy(h)
    cmd = h.svc.handle_incident.execute(make_event(policy_instance_id=pol.policy_id))
    h.svc.report_result.execute(_result(cmd), "k1")
    with pytest.raises(Conflict):
        h.svc.report_result.execute(_result(cmd, cost_used=0.2), "k1")
    with pytest.raises(Conflict):
        h.svc.report_result.execute(_result(cmd), "k2")


def test_result_for_other_candidate_conflicts(h):
    pol = _new_policy(h)
    cmd = h.svc.handle_incident.execute(make_event(policy_instance_id=pol.policy_id))
    other = next(s.candidate_id for s in cmd.scores if s.candidate_id != cmd.candidate_id)
    with pytest.raises(Conflict):
        h.svc.report_result.execute(_result(cmd, candidate_id=other), "k1")


def test_result_on_safe_stopped_incident_is_illegal(h):
    pol = _new_policy(h, PolicyKind.B0)
    cmd = h.svc.handle_incident.execute(make_event(policy_instance_id=pol.policy_id))
    from dataclasses import replace

    with pytest.raises(IllegalTransition):
        h.svc.report_result.execute(_result(replace(cmd, candidate_id="h1_retry")), "k1")


def test_frozen_policy_does_not_learn(h):
    pol = _new_policy(h, PolicyKind.P_F)
    before = h.svc.snapshot_policy.execute(pol.policy_id)["selector_state"]
    cmd = h.svc.handle_incident.execute(make_event(policy_instance_id=pol.policy_id))
    ack = h.svc.report_result.execute(_result(cmd), "k1")
    assert ack.policy_updated is False
    assert h.svc.snapshot_policy.execute(pol.policy_id)["selector_state"] == before


def test_freeze_policy_use_case(h):
    pol = _new_policy(h)
    h.svc.freeze_policy.execute(pol.policy_id)
    cmd = h.svc.handle_incident.execute(make_event(policy_instance_id=pol.policy_id))
    assert h.svc.report_result.execute(_result(cmd), "k1").policy_updated is False


def test_violation_produces_nonpositive_reward(h):
    pol = _new_policy(h)
    h.svc.register_oracle_answer.execute("task-1", "42")
    cmd = h.svc.handle_incident.execute(make_event(policy_instance_id=pol.policy_id))
    ack = h.svc.report_result.execute(_result(cmd, actions_performed=("drop_table",)), "k1")
    assert ack.reward <= 0


# ---------- CensorExpired ----------

def test_censor_expired_incident_without_update():
    h = make_harness(censor_ttl_s=60)
    pol = _new_policy(h)
    before = h.svc.snapshot_policy.execute(pol.policy_id)["selector_state"]
    cmd = h.svc.handle_incident.execute(make_event(policy_instance_id=pol.policy_id))
    h.clock.advance(seconds=30)
    assert h.svc.censor_expired.execute() == []
    h.clock.advance(seconds=31)
    assert h.svc.censor_expired.execute() == [cmd.incident_id]
    assert h.svc.get_incident.execute(cmd.incident_id).status is IncidentStatus.CENSORED
    assert h.svc.get_policy.execute(pol.policy_id).pending_incident_id is None
    assert h.svc.snapshot_policy.execute(pol.policy_id)["selector_state"] == before
    with pytest.raises(IllegalTransition):
        h.svc.report_result.execute(_result(cmd), "k1")


# ---------- learning sanity at use-case level ----------

def test_linucb_prefers_candidate_that_keeps_succeeding(h):
    pol = _new_policy(h, alpha=0.1)
    h.svc.register_oracle_answer.execute("task-1", "42")
    picks = []
    for i in range(60):
        cmd = h.svc.handle_incident.execute(make_event(policy_instance_id=pol.policy_id, run_id=f"r{i}"))
        good = cmd.candidate_id == "h2_tool_repair"
        h.svc.report_result.execute(_result(cmd, final_answer="42" if good else "no"), f"k{i}")
        picks.append(cmd.candidate_id)
    assert np.mean([p == "h2_tool_repair" for p in picks[-20:]]) > 0.8
