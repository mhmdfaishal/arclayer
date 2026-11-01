"""Eligibility and safety gate. Fungsi murni: tidak ada I/O, tidak ada state.

Gate hanya menyaring hal yang bersifat keras (izin, kapabilitas host, prasyarat wajib,
anggaran, batas insiden). Kelas fault yang didukung kandidat TIDAK disaring di sini;
ia masuk sebagai fitur lunak agar LinUCB dan B2 benar-benar berbeda perilakunya.
"""

from __future__ import annotations

from dataclasses import dataclass

from arclayer.domain.enums import Action, RejectionCode
from arclayer.domain.models import Candidate, FaultEvent, GateRejection
from arclayer.domain.preconditions import precondition_satisfied


@dataclass(frozen=True)
class GateConfig:
    allowed_permissions: frozenset[str]
    n_max: int


@dataclass(frozen=True)
class GateResult:
    eligible: tuple[Candidate, ...]
    rejections: tuple[GateRejection, ...]
    empty_action: Action | None  # None bila eligible tidak kosong


def _first_rejection(event: FaultEvent, c: Candidate, cfg: GateConfig) -> RejectionCode | None:
    if not c.enabled:
        return RejectionCode.DISABLED
    if not set(c.permissions) <= cfg.allowed_permissions:
        return RejectionCode.PERMISSION_NOT_ALLOWED
    if not set(c.required_host_capabilities) <= set(event.host_capabilities):
        return RejectionCode.HOST_CAPABILITY_MISSING
    if not all(precondition_satisfied(p, event) for p in c.required_preconditions):
        return RejectionCode.PRECONDITION_UNMET
    if c.max_cost > event.budget_remaining_cost or c.max_latency_ms > event.time_remaining_ms:
        return RejectionCode.OVER_BUDGET
    return None


def evaluate_gate(event: FaultEvent, candidates: tuple[Candidate, ...], cfg: GateConfig) -> GateResult:
    if event.prior_incidents_in_task >= cfg.n_max:
        rejections = tuple(GateRejection(c.candidate_id, RejectionCode.INCIDENT_LIMIT) for c in candidates)
        return GateResult(eligible=(), rejections=rejections, empty_action=Action.ESCALATE)

    eligible: list[Candidate] = []
    rejections: list[GateRejection] = []
    for c in candidates:
        code = _first_rejection(event, c, cfg)
        if code is None:
            eligible.append(c)
        else:
            rejections.append(GateRejection(c.candidate_id, code))

    if eligible:
        return GateResult(tuple(eligible), tuple(rejections), None)

    # Anggaran habis = kondisi berhenti yang harus dieskalasi ke pengguna (Algoritme 1,
    # langkah 15). Kandidat nonaktif diabaikan saat menilai alasannya.
    active_codes = {r.code for r in rejections if r.code is not RejectionCode.DISABLED}
    action = Action.ESCALATE if active_codes == {RejectionCode.OVER_BUDGET} else Action.SAFE_STOP
    return GateResult((), tuple(rejections), action)
