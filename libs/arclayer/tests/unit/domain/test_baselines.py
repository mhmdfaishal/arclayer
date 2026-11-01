import numpy as np

from arclayer.domain.enums import FaultClass
from arclayer.domain.models import ArmFeatures
from arclayer.domain.policies.baselines import (
    NoRecoverySelector,
    RandomSelector,
    RetrySelector,
    SemanticSimilaritySelector,
    StaticMapSelector,
)
from tests.factories import make_event


def _arms(*ids, cos=None):
    cos = cos or {}
    return tuple(ArmFeatures(candidate_id=i, x=(1.0,), cosine=cos.get(i, 0.0)) for i in ids)


RNG = lambda s=0: np.random.default_rng(s)  # noqa: E731


def test_b0_never_selects():
    assert NoRecoverySelector().select(_arms("h1_retry"), make_event(), RNG()).candidate_id is None


def test_b1_selects_retry_when_eligible_else_none():
    sel = RetrySelector("h1_retry")
    assert sel.select(_arms("h1_retry", "h2"), make_event(), RNG()).candidate_id == "h1_retry"
    assert sel.select(_arms("h2"), make_event(), RNG()).candidate_id is None


def test_b2_static_map_first_eligible_in_priority_order():
    sel = StaticMapSelector(
        mapping={FaultClass.PLAN_ERROR: ("h3_replanner", "h6_guided_rollback")},
        default=("h1_retry",),
    )
    ev = make_event(fault_class=FaultClass.PLAN_ERROR)
    assert sel.select(_arms("h1_retry", "h3_replanner", "h6_guided_rollback"), ev, RNG()).candidate_id == "h3_replanner"
    assert sel.select(_arms("h1_retry", "h6_guided_rollback"), ev, RNG()).candidate_id == "h6_guided_rollback"


def test_b2_unknown_class_uses_default():
    sel = StaticMapSelector(mapping={}, default=("h1_retry",))
    assert sel.select(_arms("h1_retry"), make_event(fault_class=None), RNG()).candidate_id == "h1_retry"


def test_b2_none_eligible_returns_none():
    sel = StaticMapSelector(mapping={FaultClass.TIMEOUT: ("h2",)}, default=())
    assert sel.select(_arms("h1_retry"), make_event(fault_class=FaultClass.TIMEOUT), RNG()).candidate_id is None


def test_b3_random_is_uniformish_and_seeded():
    arms = _arms("a", "b", "c")
    picks = [RandomSelector().select(arms, make_event(), RNG(s)).candidate_id for s in range(300)]
    assert set(picks) == {"a", "b", "c"}
    assert RandomSelector().select(arms, make_event(), RNG(5)).candidate_id == RandomSelector().select(arms, make_event(), RNG(5)).candidate_id


def test_b4_picks_highest_cosine():
    arms = _arms("a", "b", "c", cos={"a": 0.1, "b": 0.9, "c": 0.5})
    assert SemanticSimilaritySelector().select(arms, make_event(), RNG()).candidate_id == "b"


def test_baselines_update_is_noop():
    for sel in (NoRecoverySelector(), RetrySelector("h1"), RandomSelector(), SemanticSimilaritySelector()):
        assert sel.update("a", np.array([1.0]), 1.0) is False
