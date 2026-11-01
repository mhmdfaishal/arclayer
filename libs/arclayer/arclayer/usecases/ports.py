"""Port (antarmuka) yang dibutuhkan use case. Implementasinya ada di infrastructure
(penyimpanan, jam, id, lock) dan apiclients (embedding); use case hanya bergantung pada
Protocol di sini (Dependency Inversion)."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime
from typing import Any, Protocol, Sequence

import numpy as np

from arclayer.domain.entities import Incident, PolicyInstance
from arclayer.domain.enums import IncidentStatus
from arclayer.domain.models import Candidate


class CandidateRepository(Protocol):
    def add(self, c: Candidate) -> None: ...
    def get(self, candidate_id: str) -> Candidate | None: ...
    def update(self, c: Candidate) -> None: ...
    def list(self) -> list[Candidate]: ...


class PolicyRepository(Protocol):
    def add(self, p: PolicyInstance) -> None: ...
    def get(self, policy_id: str) -> PolicyInstance | None: ...
    def save(self, p: PolicyInstance) -> None: ...
    def list(self) -> list[PolicyInstance]: ...


class IncidentRepository(Protocol):
    def add(self, i: Incident) -> None: ...
    def get(self, incident_id: str) -> Incident | None: ...
    def save(self, i: Incident) -> None: ...
    def list_by_status(self, status: IncidentStatus) -> list[Incident]: ...
    def list_by_policy(self, policy_id: str) -> list[Incident]: ...


class AuditLog(Protocol):
    """Append-only. Record berupa dict yang sudah JSON-able."""

    def append(self, record: dict[str, Any]) -> None: ...
    def list(self, policy_id: str | None = None) -> list[dict[str, Any]]: ...


class OracleRepository(Protocol):
    """Ground truth benchmark. Hanya dibaca oleh verifier, tidak pernah oleh pembentuk
    konteks atau command, supaya kandidat tidak bisa melihat jawaban acuan."""

    def put(self, task_id: str, answer: str) -> None: ...
    def get(self, task_id: str) -> str | None: ...


class UnitOfWork(Protocol):
    candidates: CandidateRepository
    policies: PolicyRepository
    incidents: IncidentRepository
    audit: AuditLog
    oracle: OracleRepository

    def __enter__(self) -> "UnitOfWork": ...
    def __exit__(self, *exc: object) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> UnitOfWork: ...


class EmbeddingProvider(Protocol):
    model_id: str

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        """Kembalikan matriks (n, dim) dengan baris ternormalisasi L2."""
        ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class IdGenerator(Protocol):
    def new_id(self) -> str: ...


class PolicyLocks(Protocol):
    def lock(self, policy_id: str) -> AbstractContextManager[None]: ...
