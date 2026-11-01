from __future__ import annotations

from dataclasses import replace

from arclayer.usecases.errors import Conflict, NotFound
from arclayer.usecases.ports import UnitOfWorkFactory
from arclayer.domain.models import Candidate


class RegisterCandidate:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self.uow_factory = uow_factory

    def execute(self, c: Candidate) -> Candidate:
        with self.uow_factory() as uow:
            if uow.candidates.get(c.candidate_id) is not None:
                # Perubahan isi kandidat harus lewat candidate_id/versi baru agar audit
                # dan snapshot policy lama tetap bermakna.
                raise Conflict(f"kandidat {c.candidate_id} sudah terdaftar")
            uow.candidates.add(c)
            uow.audit.append({"event": "candidate_registered", "candidate_id": c.candidate_id, "version": c.version})
            uow.commit()
        return c


class ListCandidates:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self.uow_factory = uow_factory

    def execute(self) -> list[Candidate]:
        with self.uow_factory() as uow:
            return uow.candidates.list()


class SetCandidateEnabled:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self.uow_factory = uow_factory

    def execute(self, candidate_id: str, enabled: bool) -> Candidate:
        with self.uow_factory() as uow:
            c = uow.candidates.get(candidate_id)
            if c is None:
                raise NotFound(f"kandidat {candidate_id}")
            c = replace(c, enabled=enabled)
            uow.candidates.update(c)
            uow.audit.append({"event": "candidate_enabled_changed", "candidate_id": candidate_id, "enabled": enabled})
            uow.commit()
        return c


class RegisterOracleAnswer:
    """Hanya dipasang di mode eksperimen (lihat interface HTTP)."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self.uow_factory = uow_factory

    def execute(self, task_id: str, answer: str) -> None:
        with self.uow_factory() as uow:
            uow.oracle.put(task_id, answer)
            # Jawaban sengaja tidak ditulis ke audit.
            uow.audit.append({"event": "oracle_registered", "task_id": task_id})
            uow.commit()
