import pytest
from hypothesis import given
from hypothesis import strategies as st

from arclayer.domain.enums import Terminal
from arclayer.domain.errors import InvalidRewardWeights
from arclayer.domain.models import BudgetCaps, ExecutionResult, Verification
from arclayer.domain.reward import RewardWeights, compute_reward
from arclayer.domain.verification import compute_verification
from tests.factories import make_candidate

W = RewardWeights(s=1.0, c=0.2, l=0.1, v=1.0)
CAPS = BudgetCaps(incident_cost_cap=1.0, incident_latency_cap_ms=100_000, task_cost_cap=3.0)


def _result(**kw):
    base = dict(
        incident_id="i1", candidate_id="h1_retry", terminal=Terminal.TASK_COMPLETED,
        final_answer="42", cost_used=0.1, tokens_used=100, latency_ms=10_000,
        actions_performed=("rerun_step",), artifacts={},
    )
    base.update(kw)
    return ExecutionResult(**base)


def test_reward_equation_6():
    v = Verification(S=1, C=0.5, L=0.2, V=0, details={})
    assert compute_reward(v, W) == pytest.approx(1 - 0.1 - 0.02)


def test_default_weights_validate():
    W.validate()


@pytest.mark.parametrize("w", [RewardWeights(1, 0.6, 0.5, 1), RewardWeights(1, 0.2, 0.1, 0.5)])
def test_invalid_weights_rejected(w):
    with pytest.raises(InvalidRewardWeights):
        w.validate()


@given(c=st.floats(0, 1), l=st.floats(0, 1))
def test_success_without_violation_always_positive(c, l):
    assert compute_reward(Verification(1, c, l, 0, {}), W) > 0


@given(s=st.sampled_from([0, 1]), c=st.floats(0, 1), l=st.floats(0, 1))
def test_violation_never_positive(s, c, l):
    assert compute_reward(Verification(s, c, l, 1, {}), W) <= 0


def test_verification_success_requires_task_completed():
    cand = make_candidate()
    v = compute_verification(_result(terminal=Terminal.NEW_INCIDENT), cand, CAPS, success=True)
    assert v.S == 0


def test_verification_normalizes_and_clips_cost_and_latency():
    v = compute_verification(_result(cost_used=0.1, latency_ms=250_000), make_candidate(max_latency_ms=10**9), CAPS, success=True)
    assert v.S == 1
    assert v.C == pytest.approx(0.1)
    assert v.L == 1.0


def test_permission_violation_sets_V1():
    v = compute_verification(_result(actions_performed=("rerun_step", "delete_db")), make_candidate(), CAPS, success=True)
    assert v.V == 1
    assert "delete_db" in v.details["violations"]


def test_candidate_cost_or_latency_overrun_sets_V1():
    cand = make_candidate(max_cost=0.15, max_latency_ms=60_000)
    assert compute_verification(_result(cost_used=0.2), cand, CAPS, True).V == 1
    assert compute_verification(_result(latency_ms=70_000), cand, CAPS, True).V == 1
    assert compute_verification(_result(), cand, CAPS, True).V == 0
