"""Disjoint LinUCB (Li dkk., 2010), Persamaan (1)-(5) usulan."""

from __future__ import annotations

from typing import Any

import numpy as np

from arclayer.domain.models import ArmFeatures, FaultEvent, ScoreBreakdown, Selection

# Toleransi absolut untuk menganggap dua skor seri.
_TIE_ATOL = 1e-12


class DisjointLinUCB:
    def __init__(
        self,
        candidate_ids: tuple[str, ...] | list[str],
        d: int,
        alpha: float,
        lam: float,
        frozen: bool = False,
    ) -> None:
        self.d = d
        self.alpha = alpha
        self.lam = lam
        self.frozen = frozen
        self.A: dict[str, np.ndarray] = {h: lam * np.eye(d) for h in candidate_ids}
        self.b: dict[str, np.ndarray] = {h: np.zeros(d) for h in candidate_ids}
        self.n: dict[str, int] = {h: 0 for h in candidate_ids}

    def score(self, h: str, x: np.ndarray) -> tuple[float, float, float]:
        x = np.asarray(x, dtype=float)
        # solve() alih-alih inv() eksplisit: lebih stabil secara numerik. Dengan d = 20
        # biaya dua solve per kandidat dapat diabaikan, jadi Sherman-Morrison tidak perlu.
        theta = np.linalg.solve(self.A[h], self.b[h])  # Persamaan (1)
        a_inv_x = np.linalg.solve(self.A[h], x)
        est = float(theta @ x)
        bonus = self.alpha * float(np.sqrt(max(float(x @ a_inv_x), 0.0)))
        return est, bonus, est + bonus  # Persamaan (2)

    def select(self, arms: tuple[ArmFeatures, ...], event: FaultEvent, rng: np.random.Generator) -> Selection:
        if not arms:
            return Selection(None, (), "tidak ada kandidat layak")
        breakdown = []
        for arm in arms:
            est, bonus, s = self.score(arm.candidate_id, np.asarray(arm.x))
            breakdown.append(ScoreBreakdown(arm.candidate_id, est, bonus, s))
        best = max(b.score for b in breakdown)
        # Tie-break acak ber-seed: argmax biasa selalu memilih indeks pertama sehingga
        # urutan registri diam-diam menjadi bias pada awal pembelajaran.
        ties = [b.candidate_id for b in breakdown if abs(b.score - best) <= _TIE_ATOL]
        chosen = ties[int(rng.integers(len(ties)))] if len(ties) > 1 else ties[0]
        return Selection(chosen, tuple(breakdown), "argmax skor UCB")  # Persamaan (3)

    def update(self, candidate_id: str, x: np.ndarray, reward: float) -> bool:
        if self.frozen:
            return False
        x = np.asarray(x, dtype=float)
        self.A[candidate_id] = self.A[candidate_id] + np.outer(x, x)  # Persamaan (4)
        self.b[candidate_id] = self.b[candidate_id] + reward * x  # Persamaan (5)
        self.n[candidate_id] += 1
        return True

    def export_state(self) -> dict[str, Any]:
        # tolist() pada float64 mempertahankan nilai persis saat round-trip JSON.
        return {
            "kind": "disjoint_linucb",
            "d": self.d,
            "alpha": self.alpha,
            "lam": self.lam,
            "frozen": self.frozen,
            "A": {h: a.tolist() for h, a in self.A.items()},
            "b": {h: v.tolist() for h, v in self.b.items()},
            "n": dict(self.n),
        }

    @classmethod
    def from_state(cls, state: dict[str, Any], expected_d: int | None = None) -> "DisjointLinUCB":
        d = int(state["d"])
        if expected_d is not None and d != expected_d:
            raise ValueError(f"dimensi state {d} != dimensi fitur {expected_d}")
        obj = cls(list(state["A"].keys()), d, float(state["alpha"]), float(state["lam"]), bool(state["frozen"]))
        obj.A = {h: np.array(a, dtype=float) for h, a in state["A"].items()}
        obj.b = {h: np.array(v, dtype=float) for h, v in state["b"].items()}
        obj.n = {h: int(c) for h, c in state["n"].items()}
        return obj
