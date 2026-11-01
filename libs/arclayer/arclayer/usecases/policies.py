from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from arclayer.usecases.errors import Conflict, NotFound
from arclayer.usecases.ports import Clock, EmbeddingProvider, IdGenerator, UnitOfWorkFactory
from arclayer.usecases.services import rng as rng_svc
from arclayer.domain.entities import PolicyInstance
from arclayer.domain.enums import FaultClass, FeatureVariant, PolicyKind
from arclayer.domain.features import FeatureSpec, dimension, spec_hash
from arclayer.domain.gate import GateConfig
from arclayer.domain.models import BudgetCaps
from arclayer.domain.policies.factory import LINUCB_KINDS
from arclayer.domain.policies.linucb import DisjointLinUCB
from arclayer.domain.reward import RewardWeights


@dataclass(frozen=True)
class CreatePolicyCommand:
    kind: PolicyKind
    seed: int
    alpha: float
    lam: float
    feature_spec: FeatureSpec
    gate_config: GateConfig
    reward_weights: RewardWeights
    caps: BudgetCaps
    strict_sequential: bool = True
    retry_candidate_id: str = "h1_retry"
    static_map: dict[FaultClass, tuple[str, ...]] | None = None
    static_default: tuple[str, ...] = ("h1_retry",)
    policy_id: str | None = None
    # State LinUCB hasil kalibrasi (snapshot). P dan P-D melanjutkan belajar darinya,
    # P-F membekukannya, sehingga perbandingan P vs P-F murni menguji pembelajaran daring.
    init_state: dict[str, Any] | None = None
    experiment_id: str | None = None


class CreatePolicy:
    def __init__(self, uow_factory: UnitOfWorkFactory, embedder: EmbeddingProvider, clock: Clock, ids: IdGenerator) -> None:
        self.uow_factory = uow_factory
        self.embedder = embedder
        self.clock = clock
        self.ids = ids

    def execute(self, cmd: CreatePolicyCommand) -> PolicyInstance:
        cmd.reward_weights.validate()
        variant = FeatureVariant.NO_CANDIDATE if cmd.kind is PolicyKind.P_D else FeatureVariant.FULL
        frozen = cmd.kind is PolicyKind.P_F
        d = dimension(cmd.feature_spec, variant)

        with self.uow_factory() as uow:
            # Cek di use case, bukan mengandalkan store: store in-memory menimpa diam-diam,
            # yang akan menghapus state LinUCB eksperimen yang sedang berjalan.
            if cmd.policy_id is not None and uow.policies.get(cmd.policy_id) is not None:
                raise Conflict(f"policy {cmd.policy_id} sudah ada")
            candidates = tuple(c for c in uow.candidates.list() if c.enabled)
            ids = [c.candidate_id for c in candidates]

            selector_state: dict[str, Any] | None = None
            if cmd.kind in LINUCB_KINDS:
                if cmd.init_state is not None:
                    if sorted(cmd.init_state["A"].keys()) != sorted(ids):
                        raise ValueError("init_state memuat kandidat berbeda dari registri saat ini")
                    sel = DisjointLinUCB.from_state(copy.deepcopy(cmd.init_state), expected_d=d)
                    sel.frozen = frozen
                else:
                    sel = DisjointLinUCB(ids, d=d, alpha=cmd.alpha, lam=cmd.lam, frozen=frozen)
                selector_state = sel.export_state()

            policy = PolicyInstance(
                policy_id=cmd.policy_id or self.ids.new_id(),
                kind=cmd.kind,
                seed=cmd.seed,
                alpha=cmd.alpha,
                lam=cmd.lam,
                variant=variant,
                feature_spec=cmd.feature_spec,
                feature_hash=spec_hash(cmd.feature_spec, variant, self.embedder.model_id),
                embedding_model_id=self.embedder.model_id,
                candidates=candidates,
                gate_config=cmd.gate_config,
                reward_weights=cmd.reward_weights,
                caps=cmd.caps,
                strict_sequential=cmd.strict_sequential,
                frozen=frozen,
                retry_candidate_id=cmd.retry_candidate_id,
                static_map=dict(cmd.static_map or {}),
                static_default=cmd.static_default,
                selector_state=selector_state,
                rng_state=rng_svc.new_rng_state(cmd.seed),
                created_at=self.clock.now(),
                experiment_id=cmd.experiment_id,
            )
            uow.policies.add(policy)
            uow.audit.append({
                "event": "policy_created",
                "policy_id": policy.policy_id,
                "kind": policy.kind.value,
                "seed": policy.seed,
                "feature_hash": policy.feature_hash,
                "candidates": ids,
                "at": policy.created_at.isoformat(),
            })
            uow.commit()
        return policy


class GetPolicy:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self.uow_factory = uow_factory

    def execute(self, policy_id: str) -> PolicyInstance:
        with self.uow_factory() as uow:
            p = uow.policies.get(policy_id)
        if p is None:
            raise NotFound(f"policy {policy_id}")
        return p


class FreezePolicy:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self.uow_factory = uow_factory

    def execute(self, policy_id: str) -> PolicyInstance:
        with self.uow_factory() as uow:
            p = uow.policies.get(policy_id)
            if p is None:
                raise NotFound(f"policy {policy_id}")
            p.frozen = True
            if p.selector_state is not None:
                p.selector_state = {**p.selector_state, "frozen": True}
            uow.policies.save(p)
            uow.audit.append({"event": "policy_frozen", "policy_id": policy_id})
            uow.commit()
        return p


class SnapshotPolicy:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self.uow_factory = uow_factory

    def execute(self, policy_id: str) -> dict[str, Any]:
        with self.uow_factory() as uow:
            p = uow.policies.get(policy_id)
        if p is None:
            raise NotFound(f"policy {policy_id}")
        return {
            "policy_id": p.policy_id,
            "kind": p.kind.value,
            "feature_hash": p.feature_hash,
            "frozen": p.frozen,
            "selector_state": copy.deepcopy(p.selector_state),
        }
