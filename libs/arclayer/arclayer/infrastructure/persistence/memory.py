"""Adapter persistence in-memory dengan semantik transaksi sederhana.

Dipakai untuk unit test dan simulasi offline (outcome matrix), di mana overhead SQLite
tidak diperlukan. Perubahan di-stage per UnitOfWork dan baru diterapkan saat commit;
get() mengembalikan salinan dalam (deepcopy) supaya mutasi tanpa save() tidak bocor,
meniru perilaku repository berbasis database.
"""

from __future__ import annotations

import copy
import threading
from typing import Any

from arclayer.domain.entities import Incident, PolicyInstance
from arclayer.domain.enums import IncidentStatus
from arclayer.domain.models import Candidate


class InMemoryStore:
    def __init__(self) -> None:
        self.candidates: dict[str, Candidate] = {}
        self.policies: dict[str, PolicyInstance] = {}
        self.incidents: dict[str, Incident] = {}
        self.audit_records: list[dict[str, Any]] = []
        self.oracle: dict[str, str] = {}
        self._commit_lock = threading.Lock()

    def uow(self) -> "InMemoryUnitOfWork":
        return InMemoryUnitOfWork(self)


class _Repo:
    def __init__(self, base: dict[str, Any], staged: dict[str, Any]) -> None:
        self._base = base
        self._staged = staged

    def _get(self, key: str) -> Any:
        if key in self._staged:
            return copy.deepcopy(self._staged[key])
        v = self._base.get(key)
        return copy.deepcopy(v) if v is not None else None

    def _put(self, key: str, value: Any) -> None:
        self._staged[key] = copy.deepcopy(value)

    def _all(self) -> list[Any]:
        merged = {**self._base, **self._staged}
        return [copy.deepcopy(v) for v in merged.values()]


class _CandidateRepo(_Repo):
    def add(self, c: Candidate) -> None:
        self._put(c.candidate_id, c)

    def get(self, candidate_id: str) -> Candidate | None:
        return self._get(candidate_id)

    def update(self, c: Candidate) -> None:
        self._put(c.candidate_id, c)

    def list(self) -> list[Candidate]:
        return self._all()


class _PolicyRepo(_Repo):
    def add(self, p: PolicyInstance) -> None:
        self._put(p.policy_id, p)

    def get(self, policy_id: str) -> PolicyInstance | None:
        return self._get(policy_id)

    def save(self, p: PolicyInstance) -> None:
        self._put(p.policy_id, p)

    def list(self) -> list[PolicyInstance]:
        return self._all()


class _IncidentRepo(_Repo):
    def add(self, i: Incident) -> None:
        self._put(i.incident_id, i)

    def get(self, incident_id: str) -> Incident | None:
        return self._get(incident_id)

    def save(self, i: Incident) -> None:
        self._put(i.incident_id, i)

    def list_by_status(self, status: IncidentStatus) -> list[Incident]:
        return [i for i in self._all() if i.status is status]

    def list_by_policy(self, policy_id: str) -> list[Incident]:
        return [i for i in self._all() if i.policy_id == policy_id]


class _AuditLog:
    def __init__(self, base: list[dict[str, Any]], staged: list[dict[str, Any]]) -> None:
        self._base = base
        self._staged = staged

    def append(self, record: dict[str, Any]) -> None:
        self._staged.append(copy.deepcopy(record))

    def list(self, policy_id: str | None = None) -> list[dict[str, Any]]:
        rows = self._base + self._staged
        return [copy.deepcopy(r) for r in rows if policy_id is None or r.get("policy_id") == policy_id]


class _OracleRepo(_Repo):
    def put(self, task_id: str, answer: str) -> None:
        self._put(task_id, answer)

    def get(self, task_id: str) -> str | None:
        return self._get(task_id)


class InMemoryUnitOfWork:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store
        self._reset()

    def _reset(self) -> None:
        self._st: dict[str, dict[str, Any]] = {"c": {}, "p": {}, "i": {}, "o": {}}
        self._audit: list[dict[str, Any]] = []
        s = self._store
        self.candidates = _CandidateRepo(s.candidates, self._st["c"])
        self.policies = _PolicyRepo(s.policies, self._st["p"])
        self.incidents = _IncidentRepo(s.incidents, self._st["i"])
        self.oracle = _OracleRepo(s.oracle, self._st["o"])
        self.audit = _AuditLog(s.audit_records, self._audit)

    def __enter__(self) -> "InMemoryUnitOfWork":
        return self

    def __exit__(self, *exc: object) -> None:
        # Tanpa commit eksplisit, semua perubahan dibuang (perilaku rollback default).
        self.rollback()

    def commit(self) -> None:
        s = self._store
        with s._commit_lock:
            s.candidates.update(self._st["c"])
            s.policies.update(self._st["p"])
            s.incidents.update(self._st["i"])
            s.oracle.update(self._st["o"])
            s.audit_records.extend(self._audit)
        self._reset()

    def rollback(self) -> None:
        self._reset()
