from __future__ import annotations

import arclayer.contracts as C
from tests.support.synthetic_host import SyntheticHostAdapter, SyntheticWorld, synthetic_candidates
from tests.support.synthetic_host.world import CANDIDATE_IDS

TABLE6_CAPS = {"retry_step", "repair_tool", "replan", "resend_handoff", "review_answer", "rollback"}


def _cmd(cid: str, incident_id: str = "i") -> C.RecoveryCommandOut:
    return C.RecoveryCommandOut(
        incident_id=incident_id, action="execute", candidate_id=cid, parameters={}, verification_conditions=[],
        scores=[], excluded=[], reason="", deadline_ms=1,
    )


def test_adapter_metadata_and_event_mapping():
    ad = SyntheticHostAdapter(SyntheticWorld(1, 20))
    assert set(ad.capabilities) == TABLE6_CAPS
    inc = ad.world.incidents[0]
    ev = ad.to_fault_event(inc, "pol-9")
    assert isinstance(ev, C.FaultEventIn)
    assert ev.policy_instance_id == "pol-9" and ev.task_id == inc.task_id and ev.prior_incidents_in_task == 0
    assert ev.host_id == ad.host_id and set(ev.host_capabilities) == TABLE6_CAPS
    assert ev.orchestration.value == inc.orchestration.value
    assert ev.label_source is C.LabelSource.INJECTOR


def test_six_executors_follow_hidden_outcome_model():
    ad = SyntheticHostAdapter(SyntheticWorld(2, 40))
    specs = {s.candidate_id: s for s in synthetic_candidates()}
    exs = ad.executors()
    assert set(exs) == set(CANDIDATE_IDS)
    for inc in ad.world.incidents:
        for cid, ex in exs.items():
            r = ex.execute(_cmd(cid, "inc-1"), inc)
            d = ad.world.draw(inc, cid)
            assert r.incident_id == "inc-1" and r.candidate_id == cid
            assert r.terminal is C.Terminal.TASK_COMPLETED
            assert r.final_answer == ("PASS" if d.success else "FAIL")
            assert 0 < r.cost_used <= specs[cid].max_cost
            assert 0 < r.latency_ms <= specs[cid].max_latency_ms
            assert set(r.actions_performed) <= set(specs[cid].permissions)
            # eksekusi ulang pada insiden yang sama identik (syarat outcome matrix)
            assert ex.execute(_cmd(cid, "inc-1"), inc) == r
