from __future__ import annotations

import itertools
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest

from arclayer.usecases.policies import CreatePolicyCommand
from arclayer.bootstrap import Services, build_services
from arclayer.domain.enums import FaultClass, PolicyKind
from arclayer.domain.features import FeatureSpec
from arclayer.domain.gate import GateConfig
from arclayer.domain.models import BudgetCaps
from arclayer.domain.reward import RewardWeights
from arclayer.apiclients.embedding.hashing import HashingEmbeddingProvider
from arclayer.infrastructure.persistence.memory import InMemoryStore
from arclayer.infrastructure.persistence.sqlalchemy import SqlAlchemyStore
from tests.factories import ALL_PERMISSIONS, table6_candidates


class FakeClock:
    def __init__(self) -> None:
        self.t = datetime(2026, 10, 14, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self.t

    def advance(self, **kw) -> None:
        self.t += timedelta(**kw)


class SeqIds:
    def __init__(self) -> None:
        self._c = itertools.count(1)

    def new_id(self) -> str:
        return f"id-{next(self._c)}"


@dataclass
class Harness:
    svc: Services
    clock: FakeClock
    store: InMemoryStore | SqlAlchemyStore


# Backend aktif untuk make_harness() yang dipanggil langsung oleh test (tanpa argumen).
# Diisi fixture autouse di bawah, sehingga suite use case yang sama berjalan terhadap
# kedua store tanpa mengubah satu pun assertion di test.
_ACTIVE: dict[str, object] = {"kind": "memory", "dir": None}


def make_harness(censor_ttl_s: int = 3600, store_kind: str | None = None, db_url: str | None = None) -> Harness:
    kind = store_kind or str(_ACTIVE["kind"])
    store: InMemoryStore | SqlAlchemyStore
    if kind == "sqlite":
        if db_url is None:
            # File di tmp_path (bukan :memory:) supaya jalur WAL dan multi-koneksi ikut teruji.
            # Nama unik per harness: satu test boleh membuat beberapa harness (test seed).
            base = Path(str(_ACTIVE["dir"] or tempfile.mkdtemp()))
            db_url = f"sqlite:///{base / (uuid.uuid4().hex + '.db')}"
        store = SqlAlchemyStore(db_url)
        store.create_all()
    else:
        store = InMemoryStore()
    clock = FakeClock()
    svc = build_services(
        uow_factory=store.uow,
        embedder=HashingEmbeddingProvider(dim=64),
        clock=clock,
        ids=SeqIds(),
        censor_ttl=timedelta(seconds=censor_ttl_s),
    )
    for c in table6_candidates():
        svc.register_candidate.execute(c)
    return Harness(svc, clock, store)


def policy_cmd(kind: PolicyKind = PolicyKind.P, **kw) -> CreatePolicyCommand:
    base = dict(
        kind=kind,
        seed=11,
        alpha=0.5,
        lam=0.45,
        feature_spec=FeatureSpec(step_cap=20, budget_task_cap=3.0, n_max=2),
        gate_config=GateConfig(allowed_permissions=ALL_PERMISSIONS, n_max=2),
        reward_weights=RewardWeights(),
        caps=BudgetCaps(incident_cost_cap=1.0, incident_latency_cap_ms=300_000, task_cost_cap=3.0),
        strict_sequential=True,
        retry_candidate_id="h1_retry",
        static_map={FaultClass.TOOL_FAILURE: ("h2_tool_repair",), FaultClass.PLAN_ERROR: ("h3_replanner", "h6_guided_rollback")},
        static_default=("h1_retry",),
        policy_id=None,
        init_state=None,
        experiment_id=None,
    )
    base.update(kw)
    return CreatePolicyCommand(**base)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    # Hanya modul use case yang diparametrisasi; test_services murni tidak perlu dua kali.
    if metafunc.module.__name__.endswith("test_use_cases") and "store_kind" in metafunc.fixturenames:
        metafunc.parametrize("store_kind", ["memory", "sqlite"])


@pytest.fixture
def store_kind() -> str:
    return "memory"


@pytest.fixture(autouse=True)
def _activate_store(store_kind: str, tmp_path: Path):
    _ACTIVE.update(kind=store_kind, dir=tmp_path)
    yield
    _ACTIVE.update(kind="memory", dir=None)


@pytest.fixture
def h() -> Harness:
    return make_harness()
