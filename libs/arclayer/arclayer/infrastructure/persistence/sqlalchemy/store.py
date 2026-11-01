"""Store SQLAlchemy dengan semantik UnitOfWork yang sama seperti InMemoryUnitOfWork.

Satu UnitOfWork = satu koneksi = satu transaksi database. Keluar dari blok `with`
tanpa commit() melakukan rollback. Transaksi SQLite dibuka dengan BEGIN IMMEDIATE:
BEGIN default (deferred) membuat transaksi yang membaca lalu menulis gagal langsung
dengan SQLITE_BUSY saat ada penulis lain (snapshot WAL basi), tidak menunggu
busy_timeout. Dengan IMMEDIATE penulis diserialkan dan menunggu secara wajar; harganya
pembaca ikut mengantri, dapat diterima untuk skala eksperimen satu proses.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.pool import StaticPool

from arclayer.infrastructure.persistence.sqlalchemy import schema
from arclayer.infrastructure.persistence.sqlalchemy.repositories import (
    AuditRepo,
    CandidateRepo,
    IncidentRepo,
    OracleRepo,
    PolicyRepo,
)


def _is_memory(url: str) -> bool:
    u = make_url(url)
    return u.database in (None, "", ":memory:") or "mode=memory" in str(u.query)


class SqlAlchemyStore:
    def __init__(self, url: str = "sqlite:///./arclayer.db") -> None:
        self.url = url
        if not url.startswith("sqlite"):
            self.engine: Engine = create_engine(url)
            return
        memory = _is_memory(url)
        kwargs: dict[str, Any] = {
            # Uvicorn menjalankan endpoint sync di thread pool: koneksi lintas thread.
            "connect_args": {"check_same_thread": False, "timeout": 30},
        }
        if memory:
            # DB memori hanya ada per koneksi; satu koneksi bersama agar semua UoW
            # melihat data yang sama. Hanya untuk test satu thread, bukan produksi.
            kwargs["poolclass"] = StaticPool
        self.engine = create_engine(url, **kwargs)

        @event.listens_for(self.engine, "connect")
        def _on_connect(dbapi_conn, _record):  # noqa: ANN001
            # Matikan BEGIN implisit pysqlite (yang salah untuk DDL/SAVEPOINT);
            # transaksi dikendalikan penuh oleh event "begin" di bawah.
            dbapi_conn.isolation_level = None
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=30000")
            if not memory:
                # WAL: pembaca tidak memblokir penulis; NORMAL aman untuk WAL dan jauh
                # lebih murah dari FULL pada setiap commit.
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

        @event.listens_for(self.engine, "begin")
        def _on_begin(conn: Connection) -> None:
            # Koneksi baca murni (opsi read_only) cukup BEGIN deferred: di WAL ia tidak
            # pernah diblokir penulis dan tidak ikut mengantri lock tulis.
            read_only = conn.get_execution_options().get("read_only", False)
            conn.exec_driver_sql("BEGIN" if read_only else "BEGIN IMMEDIATE")

    def create_all(self) -> None:
        schema.metadata.create_all(self.engine)

    def uow(self) -> "SqlAlchemyUnitOfWork":
        return SqlAlchemyUnitOfWork(self.engine)

    def dispose(self) -> None:
        self.engine.dispose()

    @property
    def audit_records(self) -> list[dict[str, Any]]:
        """Hanya record yang sudah commit, urut penyisipan (setara InMemoryStore)."""
        with self.engine.connect().execution_options(read_only=True) as conn:
            rows = conn.execute(select(schema.audit.c.payload).order_by(schema.audit.c.id)).all()
        return [r[0] for r in rows]


class SqlAlchemyUnitOfWork:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._conn: Connection | None = None
        self.candidates = CandidateRepo(self._connection)
        self.policies = PolicyRepo(self._connection)
        self.incidents = IncidentRepo(self._connection)
        self.audit = AuditRepo(self._connection)
        self.oracle = OracleRepo(self._connection)

    def _connection(self) -> Connection:
        # Lazy: UoW yang tidak menyentuh repository tidak mengambil koneksi/lock.
        if self._conn is None:
            self._conn = self._engine.connect()
        return self._conn

    def __enter__(self) -> "SqlAlchemyUnitOfWork":
        return self

    def __exit__(self, *exc: object) -> None:
        try:
            self.rollback()
        finally:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def commit(self) -> None:
        if self._conn is not None:
            self._conn.commit()

    def rollback(self) -> None:
        if self._conn is not None:
            self._conn.rollback()
