from arclayer.domain.enums import Terminal
from arclayer.domain.models import BudgetCaps, Candidate, ExecutionResult, Verification


def compute_verification(
    result: ExecutionResult,
    candidate: Candidate,
    caps: BudgetCaps,
    success: bool,
) -> Verification:
    """Hitung S, C, L, V di sisi control plane, bukan di host, supaya host tidak bisa
    memanipulasi reward. `success` berasal dari verifier (mis. kecocokan jawaban).

    S = 1 hanya jika rollout benar-benar berakhir dengan tugas selesai; munculnya insiden
    baru berarti kandidat ini gagal dan insiden berikutnya dihitung sebagai putaran baru.
    """
    S = 1 if (success and result.terminal is Terminal.TASK_COMPLETED) else 0
    C = min(result.cost_used / caps.incident_cost_cap, 1.0) if caps.incident_cost_cap > 0 else 1.0
    L = min(result.latency_ms / caps.incident_latency_cap_ms, 1.0) if caps.incident_latency_cap_ms > 0 else 1.0

    violations: list[str] = sorted(set(result.actions_performed) - set(candidate.permissions))
    if result.cost_used > candidate.max_cost:
        violations.append("max_cost_exceeded")
    if result.latency_ms > candidate.max_latency_ms:
        violations.append("max_latency_exceeded")

    return Verification(
        S=S,
        C=max(C, 0.0),
        L=max(L, 0.0),
        V=1 if violations else 0,
        details={"violations": violations, "terminal": result.terminal.value},
    )
