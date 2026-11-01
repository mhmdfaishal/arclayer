"""Repository di atas SQLAlchemy Core. Semua entity lewat codec (JSON <-> dataclass)."""

from __future__ import annotations

from typing import Any, Callable, Generic, TypeVar

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from arclayer.usecases.errors import Conflict
from arclayer.domain.entities import Incident, PolicyInstance
from arclayer.domain.enums import IncidentStatus
from arclayer.domain.models import Candidate
from arclayer.infrastructure.persistence.codec import decode, encode
from arclayer.infrastructure.persistence.sqlalchemy import schema

T = TypeVar("T")
ConnGetter = Callable[[], Connection]


class _EntityRepo(Generic[T]):
    table: Any
    key_col: str
    cls: type[T]

    def __init__(self, conn: ConnGetter) -> None:
        self._conn = conn

    def _key(self, obj: T) -> str:
        return getattr(obj, self.key_col)

    def _columns(self, obj: T) -> dict[str, Any]:
        return {}

    def _insert(self, obj: T) -> None:
        values = {self.key_col: self._key(obj), "payload": encode(obj), **self._columns(obj)}
        try:
            self._conn().execute(insert(self.table).values(**values))
        except IntegrityError as e:
            # Duplikat kunci. InMemoryStore menimpa diam-diam; menimpa policy/kandidat
            # yang sudah ada merusak eksperimen, jadi di sini dijadikan Conflict (409).
            raise Conflict(f"{self.table.name} {self._key(obj)} sudah ada") from e

    def _upsert(self, obj: T) -> None:
        values = {"payload": encode(obj), **self._columns(obj)}
        col = self.table.c[self.key_col]
        res = self._conn().execute(update(self.table).where(col == self._key(obj)).values(**values))
        if res.rowcount == 0:
            self._insert(obj)

    def _get(self, key: str) -> T | None:
        col = self.table.c[self.key_col]
        row = self._conn().execute(select(self.table.c.payload).where(col == key)).first()
        return decode(self.cls, row[0]) if row else None

    def _all(self, *where: Any) -> list[T]:
        stmt = select(self.table.c.payload).order_by(self.table.c.seq)
        for w in where:
            stmt = stmt.where(w)
        return [decode(self.cls, r[0]) for r in self._conn().execute(stmt).all()]


class CandidateRepo(_EntityRepo[Candidate]):
    table, key_col, cls = schema.candidates, "candidate_id", Candidate

    def _columns(self, c: Candidate) -> dict[str, Any]:
        return {"enabled": c.enabled}

    def add(self, c: Candidate) -> None:
        self._insert(c)

    def get(self, candidate_id: str) -> Candidate | None:
        return self._get(candidate_id)

    def update(self, c: Candidate) -> None:
        self._upsert(c)

    def list(self) -> list[Candidate]:
        return self._all()


class PolicyRepo(_EntityRepo[PolicyInstance]):
    table, key_col, cls = schema.policies, "policy_id", PolicyInstance

    def add(self, p: PolicyInstance) -> None:
        self._insert(p)

    def get(self, policy_id: str) -> PolicyInstance | None:
        return self._get(policy_id)

    def save(self, p: PolicyInstance) -> None:
        self._upsert(p)

    def list(self) -> list[PolicyInstance]:
        return self._all()


class IncidentRepo(_EntityRepo[Incident]):
    table, key_col, cls = schema.incidents, "incident_id", Incident

    def _columns(self, i: Incident) -> dict[str, Any]:
        return {"policy_id": i.policy_id, "task_id": i.event.task_id, "status": i.status.value}

    def add(self, i: Incident) -> None:
        self._insert(i)

    def get(self, incident_id: str) -> Incident | None:
        return self._get(incident_id)

    def save(self, i: Incident) -> None:
        self._upsert(i)

    def list_by_status(self, status: IncidentStatus) -> list[Incident]:
        return self._all(schema.incidents.c.status == status.value)

    def list_by_policy(self, policy_id: str) -> list[Incident]:
        return self._all(schema.incidents.c.policy_id == policy_id)


class AuditRepo:
    def __init__(self, conn: ConnGetter) -> None:
        self._conn = conn

    def append(self, record: dict[str, Any]) -> None:
        self._conn().execute(
            insert(schema.audit).values(
                policy_id=record.get("policy_id"), event=str(record.get("event", "")), payload=record
            )
        )

    def list(self, policy_id: str | None = None) -> list[dict[str, Any]]:
        stmt = select(schema.audit.c.payload).order_by(schema.audit.c.id)
        if policy_id is not None:
            stmt = stmt.where(schema.audit.c.policy_id == policy_id)
        return [r[0] for r in self._conn().execute(stmt).all()]


class OracleRepo:
    def __init__(self, conn: ConnGetter) -> None:
        self._conn = conn

    def put(self, task_id: str, answer: str) -> None:
        t = schema.oracle
        res = self._conn().execute(update(t).where(t.c.task_id == task_id).values(answer=answer))
        if res.rowcount == 0:
            self._conn().execute(insert(t).values(task_id=task_id, answer=answer))

    def get(self, task_id: str) -> str | None:
        t = schema.oracle
        row = self._conn().execute(select(t.c.answer).where(t.c.task_id == task_id)).first()
        return row[0] if row else None
