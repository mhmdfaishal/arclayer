"""Round-trip codec: objek domain hasil use case nyata harus kembali identik persis."""

from __future__ import annotations

import json

import numpy as np
import pytest

from arclayer.domain.entities import Incident, PolicyInstance
from arclayer.domain.enums import FaultClass, IncidentStatus, PolicyKind, Terminal
from arclayer.domain.models import ExecutionResult
from arclayer.infrastructure.persistence.codec import decode, encode
from tests.factories import make_event, table6_candidates
from tests.unit.usecases.conftest import make_harness, policy_cmd


def _roundtrip(obj, tp):
    # lewat string JSON sungguhan supaya tuple/frozenset/float benar-benar diuji
    return decode(tp, json.loads(json.dumps(encode(obj))))


def _run_cycle(kind=PolicyKind.P, n=3):
    h = make_harness()
    pol = h.svc.create_policy.execute(policy_cmd(kind, alpha=0.37))
    h.svc.register_oracle_answer.execute("task-1", "42")
    last = None
    for i in range(n):
        cmd = h.svc.handle_incident.execute(make_event(policy_instance_id=pol.policy_id, run_id=f"r{i}"))
        if cmd.candidate_id is None:  # B0 / safe stop: tidak ada hasil untuk dilaporkan
            last = cmd.incident_id
            continue
        res = ExecutionResult(
            incident_id=cmd.incident_id, candidate_id=cmd.candidate_id, terminal=Terminal.TASK_COMPLETED,
            final_answer="42", cost_used=0.1234567891234, tokens_used=10, latency_ms=33_333,
            actions_performed=("a", "b"), artifacts={"k": "v"},
        )
        h.svc.report_result.execute(res, f"k{i}")
        last = cmd.incident_id
    return h, pol.policy_id, last


@pytest.mark.parametrize("kind", [PolicyKind.P, PolicyKind.P_D, PolicyKind.B2, PolicyKind.B3, PolicyKind.B0])
def test_policy_roundtrip_exact(kind):
    h, pid, _ = _run_cycle(kind)
    p = h.svc.get_policy.execute(pid)
    q = _roundtrip(p, PolicyInstance)
    assert q == p
    assert isinstance(q.candidates, tuple)
    assert isinstance(q.gate_config.allowed_permissions, frozenset)
    assert all(isinstance(k, FaultClass) for k in q.static_map)
    assert all(isinstance(v, tuple) for v in q.static_map.values())
    assert q.created_at.tzinfo is not None


def test_selector_state_floats_are_bit_exact():
    h, pid, _ = _run_cycle(PolicyKind.P, n=5)
    p = h.svc.get_policy.execute(pid)
    q = _roundtrip(p, PolicyInstance)
    for arm, a in p.selector_state["A"].items():
        assert np.array_equal(np.array(a), np.array(q.selector_state["A"][arm]))
    assert q.selector_state == p.selector_state


def test_rng_state_big_ints_roundtrip():
    h, pid, _ = _run_cycle(PolicyKind.B3, n=2)
    p = h.svc.get_policy.execute(pid)
    assert p.rng_state["state"]["state"] > 2**64  # PCG64 memakai bilangan 128 bit
    q = _roundtrip(p, PolicyInstance)
    assert q.rng_state == p.rng_state


def test_incident_roundtrip_exact_including_nested_optionals():
    h, _, iid = _run_cycle()
    i = h.svc.get_incident.execute(iid)
    assert i.status is IncidentStatus.RECOVERED and i.result and i.ack and i.verification
    j = _roundtrip(i, Incident)
    assert j == i
    assert isinstance(j.arms, tuple) and isinstance(j.event.available_artifacts, tuple)
    assert isinstance(j.command.scores, tuple)


def test_incident_without_command_roundtrip():
    h, pid, _ = _run_cycle(PolicyKind.B0, n=1)
    with h.store.uow() as uow:
        incs = uow.incidents.list_by_policy(pid)
    assert incs
    for inc in incs:
        assert _roundtrip(inc, Incident) == inc


def test_candidates_roundtrip_including_wildcard_classes():
    from dataclasses import replace
    from arclayer.domain.models import Candidate

    cands = [*table6_candidates(), replace(table6_candidates()[0], candidate_id="star", supported_classes=None)]
    for c in cands:
        assert _roundtrip(c, Candidate) == c
