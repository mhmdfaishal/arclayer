"""Kebijakan pembanding non-pembelajaran (Tabel 7). update() selalu no-op tetapi tetap
dipanggil oleh use case supaya jalur kode semua kebijakan identik."""

from __future__ import annotations

from typing import Any

import numpy as np

from arclayer.domain.enums import FaultClass
from arclayer.domain.models import ArmFeatures, FaultEvent, Selection


class _NoLearning:
    def update(self, candidate_id: str, x: np.ndarray, reward: float) -> bool:
        return False

    def export_state(self) -> dict[str, Any] | None:
        return None


class NoRecoverySelector(_NoLearning):
    """B0: tidak pernah memilih; use case mengembalikan SAFE_STOP tanpa memanggil gate."""

    def select(self, arms, event, rng) -> Selection:
        return Selection(None, (), "B0: tanpa recovery")


class RetrySelector(_NoLearning):
    """B1: selalu retry. Bila kandidat retry tidak lolos gate, hasilnya SAFE_STOP dan
    dihitung sebagai bagian dari hasil B1, bukan dikecualikan."""

    def __init__(self, retry_candidate_id: str) -> None:
        self.retry_candidate_id = retry_candidate_id

    def select(self, arms, event, rng) -> Selection:
        ids = {a.candidate_id for a in arms}
        if self.retry_candidate_id in ids:
            return Selection(self.retry_candidate_id, (), "B1: retry")
        return Selection(None, (), "B1: kandidat retry tidak layak")


class StaticMapSelector(_NoLearning):
    """B2: pemetaan statis kelas fault ke daftar kandidat berprioritas, dibekukan
    sebelum eksperimen (diturunkan dari kolom kelas Tabel 6)."""

    def __init__(self, mapping: dict[FaultClass, tuple[str, ...]], default: tuple[str, ...]) -> None:
        self.mapping = mapping
        self.default = default

    def select(self, arms, event: FaultEvent, rng) -> Selection:
        ids = {a.candidate_id for a in arms}
        prio = self.mapping.get(event.fault_class, self.default) if event.fault_class else self.default
        for cid in prio:
            if cid in ids:
                return Selection(cid, (), f"B2: peta statis {event.fault_class}")
        return Selection(None, (), "B2: tidak ada kandidat peta yang layak")


class RandomSelector(_NoLearning):
    """B3: acak seragam dari kandidat lolos gate."""

    def select(self, arms, event, rng: np.random.Generator) -> Selection:
        if not arms:
            return Selection(None, (), "B3: kosong")
        return Selection(arms[int(rng.integers(len(arms)))].candidate_id, (), "B3: acak")


class SemanticSimilaritySelector(_NoLearning):
    """B4: argmax cosine antara deskripsi fault dan deskripsi kandidat, dengan model
    embedding yang sama seperti fitur LinUCB."""

    def select(self, arms: tuple[ArmFeatures, ...], event, rng: np.random.Generator) -> Selection:
        if not arms:
            return Selection(None, (), "B4: kosong")
        best = max(a.cosine for a in arms)
        ties = [a.candidate_id for a in arms if a.cosine == best]
        chosen = ties[int(rng.integers(len(ties)))] if len(ties) > 1 else ties[0]
        return Selection(chosen, (), "B4: kesamaan semantik tertinggi")
