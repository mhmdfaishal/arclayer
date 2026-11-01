from __future__ import annotations

from typing import Any, Protocol

import numpy as np

from arclayer.domain.models import ArmFeatures, FaultEvent, Selection


class Selector(Protocol):
    """Strategy: semua kebijakan (B0..B4, P, P-D, P-F) punya antarmuka yang sama
    sehingga jalur kode use case identik dan perbedaan hasil hanya dari kebijakan."""

    def select(self, arms: tuple[ArmFeatures, ...], event: FaultEvent, rng: np.random.Generator) -> Selection: ...

    def update(self, candidate_id: str, x: np.ndarray, reward: float) -> bool:
        """Kembalikan True bila parameter benar-benar berubah."""
        ...

    def export_state(self) -> dict[str, Any] | None: ...
