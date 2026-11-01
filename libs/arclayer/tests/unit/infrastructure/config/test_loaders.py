from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from arclayer.domain.enums import FaultClass
from arclayer.domain.features import FeatureSpec
from arclayer.domain.gate import GateConfig
from arclayer.domain.reward import RewardWeights
from arclayer.infrastructure.config import (
    load_candidates,
    load_feature_spec,
    load_gate_config,
    load_reward_weights,
    load_static_map,
)
from tests.factories import ALL_PERMISSIONS, table6_candidates

CONFIGS = Path(__file__).resolve().parents[4] / "configs"


def test_default_candidates_equal_table6_exactly():
    assert tuple(load_candidates(CONFIGS / "candidates" / "default.yaml")) == table6_candidates()


def test_default_feature_spec():
    assert load_feature_spec(CONFIGS / "features" / "v1.yaml") == FeatureSpec(step_cap=20, budget_task_cap=3.0, n_max=1)


def test_default_reward_weights_valid():
    w = load_reward_weights(CONFIGS / "reward" / "default.yaml")
    assert w == RewardWeights(1, 0.2, 0.1, 1)
    w.validate()


def test_default_gate_config_is_union_of_table6_permissions():
    g = load_gate_config(CONFIGS / "gate" / "default.yaml")
    assert g == GateConfig(allowed_permissions=ALL_PERMISSIONS, n_max=1)
    assert isinstance(g.allowed_permissions, frozenset)


def test_default_static_map():
    m, default = load_static_map(CONFIGS / "baselines" / "static_map.yaml")
    assert m == {
        FaultClass.TOOL_FAILURE: ("h2_tool_repair",),
        FaultClass.TIMEOUT: ("h2_tool_repair",),
        FaultClass.TOOL_OUTPUT_UNUSED: ("h4_handoff_completer",),
        FaultClass.HANDOFF_INCOMPLETE: ("h4_handoff_completer", "h6_guided_rollback"),
        FaultClass.PLAN_ERROR: ("h3_replanner", "h6_guided_rollback"),
        FaultClass.INSUFFICIENT_VERIFICATION: ("h5_verification_reviewer",),
    }
    assert default == ("h1_retry",)
    assert all(isinstance(v, tuple) for v in m.values())


def test_static_map_only_references_table6_candidates_and_supported_classes():
    m, default = load_static_map(CONFIGS / "baselines" / "static_map.yaml")
    by_id = {c.candidate_id: c for c in table6_candidates()}
    for fc, ids in m.items():
        for cid in ids:
            sc = by_id[cid].supported_classes
            assert sc is None or fc in sc
    assert set(default) <= set(by_id)


def test_wildcard_supported_classes(tmp_path):
    f = tmp_path / "c.yaml"
    f.write_text(
        "candidates:\n- {candidate_id: x, version: '1', description: d, capabilities: [a], supported_classes: '*',"
        " max_cost: 0.1, max_latency_ms: 10, permissions: [p], verifier_id: v}\n"
    )
    (c,) = load_candidates(f)
    assert c.supported_classes is None and c.required_preconditions == ()


def test_invalid_candidate_rejected(tmp_path):
    f = tmp_path / "c.yaml"
    f.write_text("candidates:\n- {candidate_id: x, bogus: 1}\n")
    with pytest.raises(ValidationError):
        load_candidates(f)


def test_unknown_key_in_feature_spec_rejected(tmp_path):
    f = tmp_path / "f.yaml"
    f.write_text("step_cap: 20\nbudget_task_cap: 3.0\nn_max: 1\nextra: 1\n")
    with pytest.raises(ValidationError):
        load_feature_spec(f)


def test_unknown_fault_class_in_static_map_rejected(tmp_path):
    f = tmp_path / "s.yaml"
    f.write_text("static_map: {nope: [a]}\nstatic_default: [h1_retry]\n")
    with pytest.raises(ValidationError):
        load_static_map(f)


def test_non_mapping_yaml_rejected(tmp_path):
    f = tmp_path / "g.yaml"
    f.write_text("- 1\n- 2\n")
    with pytest.raises(ValueError):
        load_gate_config(f)
