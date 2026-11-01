from __future__ import annotations

import itertools

import pytest

from tests.support.synthetic_host import SyntheticHostAdapter, SyntheticWorld, synthetic_candidates
from tests.support.synthetic_host.world import CANDIDATE_IDS, success_probability_for
from arclayer.contracts import FaultClass, OrchestrationPattern
from arclayer.domain.gate import GateConfig, evaluate_gate
from arclayer.delivery.mappers import candidate_from_spec, event_from_in
from tests.factories import ALL_PERMISSIONS, table6_candidates

CLASSES = list(FaultClass)
ORCHS = list(OrchestrationPattern)


def test_candidates_equal_table6():
    assert tuple(candidate_from_spec(s) for s in synthetic_candidates()) == table6_candidates()


def test_world_is_deterministic_per_seed():
    a, b, c = SyntheticWorld(3, 50), SyntheticWorld(3, 50), SyntheticWorld(4, 50)
    assert a.incidents == b.incidents
    assert a.incidents != c.incidents


def test_one_incident_per_unique_task():
    w = SyntheticWorld(1, 200)
    ids = [i.task_id for i in w.incidents]
    assert len(ids) == len(set(ids)) == 200
    assert set(w.oracle) == set(ids) and set(w.oracle.values()) == {"PASS"}


def test_incident_fields_are_diverse_and_tool_fields_consistent():
    w = SyntheticWorld(1, 600)
    assert {i.fault_class for i in w.incidents} == set(CLASSES)
    assert {i.orchestration for i in w.incidents} == set(ORCHS)
    for i in w.incidents:
        if i.fault_class in (FaultClass.TOOL_FAILURE, FaultClass.TIMEOUT):
            assert i.tool_name and i.tool_error_code
        if i.fault_class is FaultClass.TOOL_OUTPUT_UNUSED:
            assert i.tool_name and i.tool_error_code is None
        assert 1.0 <= i.budget_remaining_cost <= 3.0 and i.time_remaining_ms >= 200_000
    assert any(i.checkpoint_restorable for i in w.incidents) and not all(i.checkpoint_restorable for i in w.incidents)


def test_fault_description_mentions_class_in_words():
    keywords = {
        FaultClass.TOOL_FAILURE: "tool", FaultClass.TIMEOUT: "timeout", FaultClass.TOOL_OUTPUT_UNUSED: "keluaran",
        FaultClass.HANDOFF_INCOMPLETE: "serah", FaultClass.PLAN_ERROR: "rencana",
        FaultClass.INSUFFICIENT_VERIFICATION: "bukti",
    }
    for i in SyntheticWorld(2, 300).incidents:
        assert keywords[i.fault_class] in i.fault_description.lower()


def test_every_incident_has_an_eligible_candidate_under_gate():
    cands = table6_candidates()
    cfg = GateConfig(allowed_permissions=ALL_PERMISSIONS, n_max=1)
    ad = SyntheticHostAdapter(SyntheticWorld(5, 300))
    for inc in ad.world.incidents:
        res = evaluate_gate(event_from_in(ad.to_fault_event(inc, "p")), cands, cfg)
        assert res.eligible


def test_outcome_is_deterministic_and_seeded():
    w = SyntheticWorld(9, 100)
    inc = w.incidents[0]
    first = [w.draw(inc, h) for h in CANDIDATE_IDS]
    assert first == [w.draw(inc, h) for h in CANDIDATE_IDS]
    other = SyntheticWorld(10, 100)
    inc2 = other.incidents[0]
    # task_id sama ("task-0000") tetapi seed dunia berbeda harus menggeser hasil di suatu tempat
    draws_a = [SyntheticWorld(9, 100).draw(inc, h) for h in CANDIDATE_IDS for inc in SyntheticWorld(9, 100).incidents[:30]]
    draws_b = [other.draw(i, h) for h in CANDIDATE_IDS for i in other.incidents[:30]]
    assert draws_a != draws_b
    assert inc.task_id == inc2.task_id


def test_empirical_success_rate_matches_probability():
    w = SyntheticWorld(11, 3000)
    pairs = [(i, h) for i in w.incidents[:1500] for h in ("h1_retry", "h2_tool_repair")]
    mean_p = sum(w.success_prob(i, h) for i, h in pairs) / len(pairs)
    mean_s = sum(w.draw(i, h).success for i, h in pairs) / len(pairs)
    assert abs(mean_p - mean_s) < 0.03


@pytest.mark.parametrize("cls,orch,ckpt", list(itertools.product(CLASSES, ORCHS, (True, False))))
def test_best_arm_probability_is_realistic(cls, orch, ckpt):
    best = max(success_probability_for(cls, orch, ckpt, h) for h in CANDIDATE_IDS)
    assert 0.4 <= best <= 0.85


def _p(cls, orch, ckpt, h):
    return success_probability_for(cls, orch, ckpt, h)


def test_plan_error_best_arm_depends_on_orchestration():
    P, S, C = FaultClass.PLAN_ERROR, OrchestrationPattern.SEQUENTIAL, OrchestrationPattern.CENTRALIZED
    assert _p(P, S, True, "h6_guided_rollback") > _p(P, S, True, "h3_replanner") + 0.2
    assert _p(P, C, True, "h3_replanner") > _p(P, C, True, "h6_guided_rollback") + 0.1


def test_tool_output_unused_prefers_rollback_with_checkpoint():
    T = FaultClass.TOOL_OUTPUT_UNUSED
    wins = [o for o in ORCHS if _p(T, o, True, "h6_guided_rollback") > _p(T, o, True, "h4_handoff_completer")]
    assert len(wins) >= 3


def test_static_map_is_clearly_suboptimal_in_expectation():
    mapping = {
        FaultClass.TOOL_FAILURE: ("h2_tool_repair",), FaultClass.TIMEOUT: ("h2_tool_repair",),
        FaultClass.TOOL_OUTPUT_UNUSED: ("h4_handoff_completer",),
        FaultClass.HANDOFF_INCOMPLETE: ("h4_handoff_completer", "h6_guided_rollback"),
        FaultClass.PLAN_ERROR: ("h3_replanner", "h6_guided_rollback"),
        FaultClass.INSUFFICIENT_VERIFICATION: ("h5_verification_reviewer",),
    }
    cands = table6_candidates()
    cfg = GateConfig(allowed_permissions=ALL_PERMISSIONS, n_max=1)
    ad = SyntheticHostAdapter(SyntheticWorld(21, 2000))
    best_sum = b2_sum = 0.0
    for inc in ad.world.incidents:
        elig = {c.candidate_id for c in evaluate_gate(event_from_in(ad.to_fault_event(inc, "p")), cands, cfg).eligible}
        probs = {h: ad.world.success_prob(inc, h) for h in elig}
        best_sum += max(probs.values())
        pick = next((h for h in mapping[inc.fault_class] if h in elig), None)
        b2_sum += probs[pick] if pick else 0.0
    n = len(ad.world.incidents)
    assert best_sum / n - b2_sum / n > 0.07
