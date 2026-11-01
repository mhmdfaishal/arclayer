"""Loader konfigurasi YAML. Setiap berkas divalidasi dengan model Pydantic
(arclayer.contracts bila ada; model privat untuk gate dan peta statis yang tidak punya
kontrak publik) sebelum dipetakan ke objek domain, supaya salah ketik atau field
asing gagal di startup dan bukan di tengah eksperimen."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

import arclayer.contracts as C
from arclayer.domain import enums as D
from arclayer.domain.features import FeatureSpec
from arclayer.domain.gate import GateConfig
from arclayer.domain.models import Candidate
from arclayer.domain.reward import RewardWeights

PathLike = str | Path


class _Gate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed_permissions: list[str]
    n_max: int = Field(gt=0)


class _StaticMap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    static_map: dict[C.FaultClass, list[str]]
    static_default: list[str] = Field(min_length=1)


class _Candidates(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidates: list[C.CandidateSpec]


def _read(path: PathLike) -> dict[str, Any]:
    # safe_load: berkas konfigurasi tidak boleh bisa membangun objek Python arbitrer.
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: isi harus berupa mapping YAML")
    return data


def _candidate_from_spec(s: C.CandidateSpec) -> Candidate:
    # Pemetaan lokal, bukan arclayer.delivery.mappers: infrastructure dilarang bergantung
    # ke delivery (aturan arsitektur). Kesamaan dengan Tabel 6 dijaga oleh test.
    return Candidate(
        candidate_id=s.candidate_id,
        version=s.version,
        description=s.description,
        capabilities=tuple(s.capabilities),
        supported_classes=None if s.supported_classes == "*" else tuple(D.FaultClass(c.value) for c in s.supported_classes),
        required_preconditions=tuple(D.Precondition(p.value) for p in s.required_preconditions),
        optional_preconditions=tuple(D.Precondition(p.value) for p in s.optional_preconditions),
        required_host_capabilities=tuple(s.required_host_capabilities),
        max_cost=s.max_cost,
        max_latency_ms=s.max_latency_ms,
        permissions=tuple(s.permissions),
        verifier_id=s.verifier_id,
        enabled=s.enabled,
    )


def load_candidates(path: PathLike) -> list[Candidate]:
    return [_candidate_from_spec(s) for s in _Candidates.model_validate(_read(path)).candidates]


def load_feature_spec(path: PathLike) -> FeatureSpec:
    m = C.FeatureSpecIn.model_validate(_read(path))
    return FeatureSpec(step_cap=m.step_cap, budget_task_cap=m.budget_task_cap, n_max=m.n_max)


def load_reward_weights(path: PathLike) -> RewardWeights:
    m = C.RewardWeightsIn.model_validate(_read(path))
    w = RewardWeights(s=m.s, c=m.c, l=m.l, v=m.v)
    w.validate()  # invarian reward diperiksa saat load, bukan saat policy dibuat
    return w


def load_gate_config(path: PathLike) -> GateConfig:
    m = _Gate.model_validate(_read(path))
    return GateConfig(allowed_permissions=frozenset(m.allowed_permissions), n_max=m.n_max)


def load_static_map(path: PathLike) -> tuple[dict[D.FaultClass, tuple[str, ...]], tuple[str, ...]]:
    """Kembalikan (static_map, static_default) siap dipakai CreatePolicyCommand."""
    m = _StaticMap.model_validate(_read(path))
    return (
        {D.FaultClass(k.value): tuple(v) for k, v in m.static_map.items()},
        tuple(m.static_default),
    )
