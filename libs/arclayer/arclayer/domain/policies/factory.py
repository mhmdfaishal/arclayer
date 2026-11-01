from __future__ import annotations

from arclayer.domain.entities import PolicyInstance
from arclayer.domain.enums import PolicyKind
from arclayer.domain.features import dimension
from arclayer.domain.policies.base import Selector
from arclayer.domain.policies.baselines import (
    NoRecoverySelector,
    RandomSelector,
    RetrySelector,
    SemanticSimilaritySelector,
    StaticMapSelector,
)
from arclayer.domain.policies.linucb import DisjointLinUCB

LINUCB_KINDS = frozenset({PolicyKind.P, PolicyKind.P_D, PolicyKind.P_F})


def build_selector(p: PolicyInstance) -> Selector:
    match p.kind:
        case PolicyKind.B0:
            return NoRecoverySelector()
        case PolicyKind.B1:
            return RetrySelector(p.retry_candidate_id)
        case PolicyKind.B2:
            return StaticMapSelector(p.static_map, p.static_default)
        case PolicyKind.B3:
            return RandomSelector()
        case PolicyKind.B4:
            return SemanticSimilaritySelector()
        case PolicyKind.P | PolicyKind.P_D | PolicyKind.P_F:
            assert p.selector_state is not None
            sel = DisjointLinUCB.from_state(p.selector_state, expected_d=dimension(p.feature_spec, p.variant))
            sel.frozen = p.frozen
            return sel
    raise ValueError(f"kind tidak dikenal: {p.kind}")
