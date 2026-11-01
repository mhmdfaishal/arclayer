"""Kontrak UnitOfWork untuk SqlAlchemyStore: sama dengan InMemoryUnitOfWork."""

from __future__ import annotations

import threading
from dataclasses import replace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from arclayer.usecases.errors import Conflict
from arclayer.domain.enums import IncidentStatus, PolicyKind
from arclayer.infrastructure.persistence.sqlalchemy import SqlAlchemyStore
from tests.factories import make_candidate, make_event
from tests.unit.usecases.conftest import make_harness, policy_cmd


@pytest.fixture
def store(tmp_path):
    s = SqlAlchemyStore(f"sqlite:///{tmp_path / 'arclayer.db'}")
    s.create_all()
    yield s
    s.dispose()


def test_commit_persists_and_rollback_discards(store):
    with store.uow() as uow:
        uow.candidates.add(make_candidate(candidate_id="a"))
        uow.oracle.put("t1", "ans")
        uow.audit.append({"event": "x", "policy_id": None})
        uow.commit()
    with store.uow() as uow:
        uow.candidates.add(make_candidate(candidate_id="b"))
        uow.oracle.put("t2", "ans2")
        uow.audit.append({"event": "y"})
        # tanpa commit
    with store.uow() as uow:
        assert [c.candidate_id for c in uow.candidates.list()] == ["a"]
        assert uow.oracle.get("t2") is None and uow.oracle.get("t1") == "ans"
    assert [r["event"] for r in store.audit_records] == ["x"]


def test_explicit_rollback_discards(store):
    with store.uow() as uow:
        uow.candidates.add(make_candidate(candidate_id="a"))
        uow.rollback()
        uow.commit()
    with store.uow() as uow:
        assert uow.candidates.list() == []


def test_exception_inside_block_rolls_back(store):
    with pytest.raises(RuntimeError):
        with store.uow() as uow:
            uow.candidates.add(make_candidate(candidate_id="a"))
            raise RuntimeError("boom")
    with store.uow() as uow:
        assert uow.candidates.get("a") is None


def test_uncommitted_writes_visible_inside_same_uow_but_not_to_others(store):
    with store.uow() as uow:
        uow.candidates.add(make_candidate(candidate_id="a"))
        assert uow.candidates.get("a") is not None
        assert store.audit_records == []
        with store.engine.connect().execution_options(read_only=True) as other:
            assert other.execute(text("SELECT COUNT(*) FROM candidates")).scalar() == 0


def test_get_returns_independent_copies(store):
    with store.uow() as uow:
        uow.candidates.add(make_candidate(candidate_id="a"))
        uow.commit()
    with store.uow() as uow:
        a1 = uow.candidates.get("a")
        a2 = uow.candidates.get("a")
        assert a1 == a2 and a1 is not a2


def test_candidate_list_keeps_registration_order_and_update_keeps_position(store):
    with store.uow() as uow:
        for cid in ("z", "a", "m"):
            uow.candidates.add(make_candidate(candidate_id=cid))
        uow.commit()
    with store.uow() as uow:
        uow.candidates.update(replace(uow.candidates.get("z"), enabled=False))
        uow.commit()
    with store.uow() as uow:
        got = uow.candidates.list()
        assert [c.candidate_id for c in got] == ["z", "a", "m"]
        assert got[0].enabled is False


def test_duplicate_add_raises_conflict(store):
    with store.uow() as uow:
        uow.candidates.add(make_candidate(candidate_id="a"))
        uow.commit()
    with pytest.raises(Conflict):
        with store.uow() as uow:
            uow.candidates.add(make_candidate(candidate_id="a"))


def test_oracle_put_overwrites(store):
    with store.uow() as uow:
        uow.oracle.put("t", "one")
        uow.oracle.put("t", "two")
        uow.commit()
    with store.uow() as uow:
        assert uow.oracle.get("t") == "two"


def test_audit_filters_by_policy_and_preserves_order(store):
    with store.uow() as uow:
        uow.audit.append({"event": "e1", "policy_id": "p1"})
        uow.audit.append({"event": "e2", "policy_id": "p2"})
        uow.audit.append({"event": "e3", "policy_id": "p1", "n": 1.5})
        uow.commit()
    with store.uow() as uow:
        assert [r["event"] for r in uow.audit.list("p1")] == ["e1", "e3"]
        assert [r["event"] for r in uow.audit.list()] == ["e1", "e2", "e3"]
    assert store.audit_records[2] == {"event": "e3", "policy_id": "p1", "n": 1.5}


def test_audit_is_append_only_via_triggers(store):
    with store.uow() as uow:
        uow.audit.append({"event": "e1"})
        uow.commit()
    with store.engine.begin() as conn:
        with pytest.raises(DBAPIError, match="append-only"):
            conn.execute(text("UPDATE audit SET event = 'tampered'"))
    with store.engine.begin() as conn:
        with pytest.raises(DBAPIError, match="append-only"):
            conn.execute(text("DELETE FROM audit"))
    assert [r["event"] for r in store.audit_records] == ["e1"]


def test_file_db_uses_wal(store):
    with store.engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"


def test_memory_db_works_across_threads():
    s = SqlAlchemyStore("sqlite://")
    s.create_all()
    with s.uow() as uow:
        uow.candidates.add(make_candidate(candidate_id="a"))
        uow.commit()
    seen = []

    def read():
        with s.uow() as uow:
            seen.append(uow.candidates.get("a"))

    t = threading.Thread(target=read)
    t.start(); t.join()
    assert seen and seen[0] is not None


def test_data_survives_new_store_instance_on_same_file(tmp_path):
    url = f"sqlite:///{tmp_path / 'x.db'}"
    h = make_harness(store_kind="sqlite", db_url=url)
    pol = h.svc.create_policy.execute(policy_cmd(PolicyKind.P))
    cmd = h.svc.handle_incident.execute(make_event(policy_instance_id=pol.policy_id))
    h.store.dispose()
    s2 = SqlAlchemyStore(url)
    with s2.uow() as uow:
        assert uow.policies.get(pol.policy_id).pending_incident_id == cmd.incident_id
        assert uow.incidents.get(cmd.incident_id).status is IncidentStatus.AWAITING_RESULT
        assert len(uow.incidents.list_by_status(IncidentStatus.AWAITING_RESULT)) == 1
        assert len(uow.incidents.list_by_policy(pol.policy_id)) == 1


def test_concurrent_writers_do_not_lose_commits(store):
    def worker(i):
        for j in range(10):
            with store.uow() as uow:
                uow.audit.append({"event": f"e{i}-{j}"})
                uow.commit()

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert len(store.audit_records) == 40
