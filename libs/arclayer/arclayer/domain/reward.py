from dataclasses import dataclass

from arclayer.domain.errors import InvalidRewardWeights
from arclayer.domain.models import Verification


@dataclass(frozen=True)
class RewardWeights:
    s: float = 1.0
    c: float = 0.2
    l: float = 0.1  # noqa: E741
    v: float = 1.0

    def validate(self) -> None:
        # Invarian usulan: keberhasilan tanpa pelanggaran selalu positif (w_c + w_l < w_s),
        # dan pelanggaran tidak pernah menghasilkan reward bersih positif (w_v >= w_s).
        if min(self.s, self.c, self.l, self.v) < 0:
            raise InvalidRewardWeights("bobot tidak boleh negatif")
        if not self.c + self.l < self.s:
            raise InvalidRewardWeights("w_c + w_l harus < w_s")
        if not self.v >= self.s:
            raise InvalidRewardWeights("w_v harus >= w_s")


def compute_reward(v: Verification, w: RewardWeights) -> float:
    """Persamaan (6): r_t = w_s S_t - w_c C_t - w_l L_t - w_v V_t."""
    return w.s * v.S - w.c * v.C - w.l * v.L - w.v * v.V
