"""Skema tabel. Entity disimpan sebagai payload JSON (hasil codec) plus kolom terindeks
untuk kueri yang dipakai use case. Memecah entity ke kolom relasional tidak dilakukan:
PolicyInstance dan Incident bersarang dalam, dan satu-satunya konsumennya adalah codec,
jadi JSON menghindari migrasi skema setiap kali field domain bertambah.

Kolom `seq` (autoincrement) menjaga urutan registrasi pada list(), meniru urutan
insersi dict di InMemoryStore; kunci bisnis dipisah sebagai kolom UNIQUE."""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, Column, DDL, Index, Integer, MetaData, String, Table, Text, event

metadata = MetaData()

candidates = Table(
    "candidates", metadata,
    Column("seq", Integer, primary_key=True),
    Column("candidate_id", String(200), nullable=False, unique=True),
    Column("enabled", Boolean, nullable=False),
    Column("payload", JSON, nullable=False),
)

policies = Table(
    "policies", metadata,
    Column("seq", Integer, primary_key=True),
    Column("policy_id", String(200), nullable=False, unique=True),
    Column("payload", JSON, nullable=False),
)

incidents = Table(
    "incidents", metadata,
    Column("seq", Integer, primary_key=True),
    Column("incident_id", String(200), nullable=False, unique=True),
    Column("policy_id", String(200), nullable=False),
    Column("task_id", String(200), nullable=False),
    Column("status", String(50), nullable=False),
    Column("payload", JSON, nullable=False),
    Index("ix_incidents_status", "status"),
    Index("ix_incidents_policy_id", "policy_id"),
    Index("ix_incidents_task_id", "task_id"),
)

# sqlite_autoincrement: id tidak pernah dipakai ulang, urutan audit monoton.
audit = Table(
    "audit", metadata,
    Column("id", Integer, primary_key=True),
    Column("policy_id", String(200), nullable=True),
    Column("event", String(100), nullable=False),
    Column("payload", JSON, nullable=False),
    Index("ix_audit_policy_id", "policy_id"),
    sqlite_autoincrement=True,
)

oracle = Table(
    "oracle", metadata,
    Column("task_id", String(200), primary_key=True),
    Column("answer", Text, nullable=False),
)

# Append-only ditegakkan di level database, bukan hanya konvensi kode: kode aplikasi
# yang salah (atau SQL manual) tidak bisa mengubah atau menghapus jejak audit.
for _op in ("UPDATE", "DELETE"):
    event.listen(
        audit,
        "after_create",
        DDL(
            f"CREATE TRIGGER IF NOT EXISTS audit_no_{_op.lower()} BEFORE {_op} ON audit "
            "BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END"
        ).execute_if(dialect="sqlite"),
    )
