"""Composition root: satu-satunya tempat yang memilih adapter konkret untuk penyimpanan
(SQLite atau memori), embedding, dan jam. Delivery, host, dan eksperimen menerima Services
dari builder di sini dan tidak membuat store atau embedder sendiri. Pembacaan YAML kandidat
(`arclayer.infrastructure.config`) dikecualikan: itu parsing berkas, bukan pemilihan adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from arclayer.apiclients.embedding.hashing import HashingEmbeddingProvider
from arclayer.infrastructure.persistence.memory import InMemoryStore
from arclayer.infrastructure.runtime.system import SystemClock, ThreadPolicyLocks, UuidGenerator
from arclayer.usecases.candidates import (
    ListCandidates,
    RegisterCandidate,
    RegisterOracleAnswer,
    SetCandidateEnabled,
)
from arclayer.usecases.incidents import CensorExpired, GetIncident, HandleIncident, ReportResult
from arclayer.usecases.policies import CreatePolicy, FreezePolicy, GetPolicy, SnapshotPolicy
from arclayer.usecases.ports import Clock, EmbeddingProvider, IdGenerator, PolicyLocks, UnitOfWorkFactory
from arclayer.usecases.services.verifiers import DEFAULT_VERIFIERS, SuccessVerifier

EMBEDDING_DIM = 384  # dimensi model all-MiniLM-L6-v2; hashing dibuat sama agar interchangeable


@dataclass
class Services:
    handle_incident: HandleIncident
    report_result: ReportResult
    censor_expired: CensorExpired
    get_incident: GetIncident
    create_policy: CreatePolicy
    get_policy: GetPolicy
    freeze_policy: FreezePolicy
    snapshot_policy: SnapshotPolicy
    register_candidate: RegisterCandidate
    list_candidates: ListCandidates
    set_candidate_enabled: SetCandidateEnabled
    register_oracle_answer: RegisterOracleAnswer
    uow_factory: UnitOfWorkFactory


def build_services(
    uow_factory: UnitOfWorkFactory,
    embedder: EmbeddingProvider,
    clock: Clock | None = None,
    ids: IdGenerator | None = None,
    locks: PolicyLocks | None = None,
    verifiers: dict[str, SuccessVerifier] | None = None,
    censor_ttl: timedelta = timedelta(hours=1),
) -> Services:
    clock = clock or SystemClock()
    ids = ids or UuidGenerator()
    locks = locks or ThreadPolicyLocks()
    verifiers = verifiers or dict(DEFAULT_VERIFIERS)
    return Services(
        handle_incident=HandleIncident(uow_factory, embedder, clock, ids, locks),
        report_result=ReportResult(uow_factory, verifiers, clock, locks),
        censor_expired=CensorExpired(uow_factory, clock, locks, censor_ttl),
        get_incident=GetIncident(uow_factory),
        create_policy=CreatePolicy(uow_factory, embedder, clock, ids),
        get_policy=GetPolicy(uow_factory),
        freeze_policy=FreezePolicy(uow_factory),
        snapshot_policy=SnapshotPolicy(uow_factory),
        register_candidate=RegisterCandidate(uow_factory),
        list_candidates=ListCandidates(uow_factory),
        set_candidate_enabled=SetCandidateEnabled(uow_factory),
        register_oracle_answer=RegisterOracleAnswer(uow_factory),
        uow_factory=uow_factory,
    )


def make_embedder(spec: str) -> EmbeddingProvider:
    """`hashing` (deterministik, offline) atau `st:<model>` (sentence-transformers)."""
    if spec == "hashing":
        return HashingEmbeddingProvider(EMBEDDING_DIM)
    if spec.startswith("st:") and len(spec) > 3:
        # Import malas: service ber-embedding hashing tidak perlu menarik torch.
        from arclayer.apiclients.embedding.sentence_transformer import SentenceTransformerEmbeddingProvider

        return SentenceTransformerEmbeddingProvider(spec[3:])
    raise ValueError(f"embedding tidak dikenal: {spec!r} (gunakan 'hashing' atau 'st:<model>')")


def build_sql_services(db_url: str, embedding: str, censor_ttl_s: float) -> Services:
    """Layanan produksi: penyimpanan SQLite lewat SQLAlchemy. Embedder dibuat lebih dulu agar
    spesifikasi yang salah gagal sebelum berkas database tersentuh."""
    # Impor malas: host dan harness yang hanya memakai store memori tidak perlu menarik
    # SQLAlchemy, yaml, dan pydantic hanya untuk mengimpor modul ini.
    from arclayer.infrastructure.persistence.sqlalchemy import SqlAlchemyStore

    embedder = make_embedder(embedding)
    store = SqlAlchemyStore(db_url)
    store.create_all()
    return build_services(uow_factory=store.uow, embedder=embedder, censor_ttl=timedelta(seconds=censor_ttl_s))


def build_default_services(db_url: str | None, embedding: str, censor_ttl_s: float) -> Services:
    """SQLite at `db_url`, or an in-memory store (nothing persists) when `db_url` is None."""
    if db_url is not None:
        return build_sql_services(db_url, embedding, censor_ttl_s)
    return build_services(InMemoryStore().uow, make_embedder(embedding), censor_ttl=timedelta(seconds=censor_ttl_s))


def seed_candidates(svc: Services, path: str | Path) -> None:
    # Hanya saat registri kosong: restart pada DB yang sudah terisi tidak boleh
    # menimpa atau menggandakan kandidat (register_candidate menolak duplikat).
    if svc.list_candidates.execute():
        return
    from arclayer.infrastructure.config import load_candidates  # impor malas: menarik yaml dan pydantic

    for c in load_candidates(path):
        svc.register_candidate.execute(c)


@dataclass
class InMemoryControlPlane:
    """Control plane in-process tanpa HTTP dan tanpa DB. `store` dibuka karena harness
    eksperimen membaca `store.audit_records` langsung."""

    services: Services
    store: InMemoryStore


def build_inmemory_control_plane(
    embedding_dim: int = EMBEDDING_DIM,
    clock: Clock | None = None,
    ids: IdGenerator | None = None,
) -> InMemoryControlPlane:
    """Untuk host demo, test, dan simulasi. `clock`/`ids` deterministik membuat audit identik antar run."""
    store = InMemoryStore()
    services = build_services(store.uow, HashingEmbeddingProvider(embedding_dim), clock=clock, ids=ids)
    return InMemoryControlPlane(services=services, store=store)
