import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from arclayer.domain.enums import FaultClass, FeatureVariant, OrchestrationPattern, Precondition
from arclayer.domain.features import FeatureSpec, build_x, dimension, spec_hash
from tests.factories import make_candidate, make_event

SPEC = FeatureSpec(step_cap=20, budget_task_cap=3.0, n_max=2)


def test_full_variant_has_20_dims_with_bias_last():
    x = build_x(make_event(), make_candidate(), cosine=0.3, spec=SPEC, variant=FeatureVariant.FULL)
    assert x.shape == (20,)
    assert x[-1] == 1.0
    assert dimension(SPEC, FeatureVariant.FULL) == 20


def test_no_candidate_variant_keeps_only_cost_ratio_from_g():
    # Ablasi P-D: cosine, class match, dan kelengkapan prasyarat dibuang;
    # rasio biaya dipertahankan karena bukan fitur deskripsi/kapabilitas.
    event = make_event(budget_remaining_cost=1.0)
    cand = make_candidate(max_cost=0.25)
    x = build_x(event, cand, cosine=0.9, spec=SPEC, variant=FeatureVariant.NO_CANDIDATE)
    assert x.shape == (17,)
    assert dimension(SPEC, FeatureVariant.NO_CANDIDATE) == 17
    assert x[15] == pytest.approx(0.25)
    assert x[16] == 1.0


def test_fault_class_one_hot_position():
    x = build_x(make_event(fault_class=FaultClass.PLAN_ERROR), make_candidate(), 0.0, SPEC, FeatureVariant.FULL)
    onehot = x[0:6]
    assert onehot.sum() == 1.0
    assert onehot[list(FaultClass).index(FaultClass.PLAN_ERROR)] == 1.0


def test_unknown_fault_class_gives_all_zero_onehot_and_half_class_match():
    x = build_x(make_event(fault_class=None, fault_confidence=None), make_candidate(supported_classes=(FaultClass.TIMEOUT,)), 0.0, SPEC, FeatureVariant.FULL)
    assert x[0:6].sum() == 0.0
    assert x[16] == 0.5


def test_confidence_defaults_to_one_for_injector_labels():
    x = build_x(make_event(fault_confidence=None), make_candidate(), 0.0, SPEC, FeatureVariant.FULL)
    assert x[6] == 1.0


def test_confidence_used_when_attribution_provides_it():
    from arclayer.domain.enums import LabelSource

    x = build_x(make_event(label_source=LabelSource.ATTRIBUTION, fault_confidence=0.4), make_candidate(), 0.0, SPEC, FeatureVariant.FULL)
    assert x[6] == pytest.approx(0.4)


def test_orchestration_one_hot():
    x = build_x(make_event(orchestration=OrchestrationPattern.CONCURRENT), make_candidate(), 0.0, SPEC, FeatureVariant.FULL)
    assert list(x[7:11]) == [0.0, 0.0, 1.0, 0.0]


def test_relative_step_uses_estimate_then_falls_back_to_cap():
    with_est = build_x(make_event(step_index=5, step_total_estimate=10), make_candidate(), 0.0, SPEC, FeatureVariant.FULL)
    without = build_x(make_event(step_index=5, step_total_estimate=None), make_candidate(), 0.0, SPEC, FeatureVariant.FULL)
    assert with_est[11] == pytest.approx(0.5)
    assert without[11] == pytest.approx(5 / 20)


def test_prior_incidents_and_checkpoint_and_budget():
    x = build_x(make_event(prior_incidents_in_task=1, checkpoint_restorable=False, budget_remaining_cost=1.5), make_candidate(), 0.0, SPEC, FeatureVariant.FULL)
    assert x[12] == pytest.approx(0.5)
    assert x[13] == 0.0
    assert x[14] == pytest.approx(0.5)


def test_cosine_is_mapped_from_minus1_1_to_0_1():
    x = build_x(make_event(), make_candidate(), cosine=-1.0, spec=SPEC, variant=FeatureVariant.FULL)
    assert x[15] == 0.0
    x = build_x(make_event(), make_candidate(), cosine=1.0, spec=SPEC, variant=FeatureVariant.FULL)
    assert x[15] == 1.0


def test_class_match_wildcard_supported_and_unsupported():
    ev = make_event(fault_class=FaultClass.TIMEOUT)
    assert build_x(ev, make_candidate(supported_classes=None), 0, SPEC, FeatureVariant.FULL)[16] == 1.0
    assert build_x(ev, make_candidate(supported_classes=(FaultClass.TIMEOUT,)), 0, SPEC, FeatureVariant.FULL)[16] == 1.0
    assert build_x(ev, make_candidate(supported_classes=(FaultClass.PLAN_ERROR,)), 0, SPEC, FeatureVariant.FULL)[16] == 0.0


def test_cost_ratio_clipped_and_safe_on_zero_budget():
    assert build_x(make_event(budget_remaining_cost=0.1), make_candidate(max_cost=0.4), 0, SPEC, FeatureVariant.FULL)[17] == 1.0
    assert build_x(make_event(budget_remaining_cost=0.0), make_candidate(max_cost=0.4), 0, SPEC, FeatureVariant.FULL)[17] == 1.0


def test_optional_precondition_completeness():
    cand = make_candidate(optional_preconditions=(Precondition.EVIDENCE_ARTIFACT_AVAILABLE, Precondition.CHECKPOINT_AVAILABLE))
    x = build_x(make_event(available_artifacts=(), checkpoint_restorable=True), cand, 0, SPEC, FeatureVariant.FULL)
    assert x[18] == pytest.approx(0.5)
    assert build_x(make_event(), make_candidate(optional_preconditions=()), 0, SPEC, FeatureVariant.FULL)[18] == 1.0


@settings(max_examples=200, deadline=None)
@given(
    step=st.integers(0, 500),
    total=st.one_of(st.none(), st.integers(0, 500)),
    prior=st.integers(0, 50),
    budget=st.floats(0, 100, allow_nan=False),
    cos=st.floats(-1, 1, allow_nan=False),
    max_cost=st.floats(0.001, 10, allow_nan=False),
    conf=st.one_of(st.none(), st.floats(0, 1, allow_nan=False)),
)
def test_all_features_are_in_unit_interval(step, total, prior, budget, cos, max_cost, conf):
    ev = make_event(step_index=step, step_total_estimate=total, prior_incidents_in_task=prior, budget_remaining_cost=budget, fault_confidence=conf)
    x = build_x(ev, make_candidate(max_cost=max_cost), cos, SPEC, FeatureVariant.FULL)
    assert np.all(x >= 0.0) and np.all(x <= 1.0)


def test_spec_hash_changes_with_spec_variant_or_embedding_model():
    h = spec_hash(SPEC, FeatureVariant.FULL, "model-a")
    assert h == spec_hash(SPEC, FeatureVariant.FULL, "model-a")
    assert h != spec_hash(FeatureSpec(step_cap=21, budget_task_cap=3.0, n_max=2), FeatureVariant.FULL, "model-a")
    assert h != spec_hash(SPEC, FeatureVariant.NO_CANDIDATE, "model-a")
    assert h != spec_hash(SPEC, FeatureVariant.FULL, "model-b")
