"""Menjalankan satu kebijakan pada dunia sintetis lewat komponen lapisan eksternal saja:
SDK (handle_fault), client in-process, dan control plane dengan store memori.

Bukan harness eksperimen: tidak ada pemilihan alpha, P-D, P-F, atau outcome matrix.
Tujuannya membuktikan pipa jalan dan LinUCB belajar dari reward, dengan desain usulan:
belajar di 20% insiden (kalibrasi), lalu dievaluasi di 80% sisanya mulai dari snapshot itu."""

from __future__ import annotations

import numpy as np

import arclayer.contracts as C
from arclayer.bootstrap import build_inmemory_control_plane
from arclayer.delivery.inprocess import InProcessControlPlaneClient
from arclayer.delivery.mappers import candidate_from_spec, create_policy_cmd
from arclayer.host.runtime import handle_fault
from tests.support.synthetic_host import SyntheticHostAdapter, SyntheticWorld, synthetic_candidates

STATIC_MAP = {
    "tool_failure": ["h2_tool_repair"], "timeout": ["h2_tool_repair"],
    "tool_output_unused": ["h4_handoff_completer"],
    "handoff_incomplete": ["h4_handoff_completer", "h6_guided_rollback"],
    "plan_error": ["h3_replanner", "h6_guided_rollback"],
    "insufficient_verification": ["h5_verification_reviewer"],
}


def split_calibration(world: SyntheticWorld, seed: int, fraction: float = 0.2) -> tuple[list, list]:
    """Urutan acak ber-seed yang sama untuk semua kebijakan; (kalibrasi, evaluasi)."""
    order = np.random.default_rng(seed).permutation(len(world.incidents))
    items = [world.incidents[int(i)] for i in order]
    cut = int(len(items) * fraction)
    return items[:cut], items[cut:]


def run_policy(
    kind: str, seed: int, world: SyntheticWorld, incidents: list, alpha: float = 0.1, init_state: dict | None = None,
) -> tuple[float, dict | None]:
    """(reward rata-rata per insiden, state LinUCB akhir bila kind == "P").

    Safe-stop dan escalate tidak punya hasil dan dihitung reward 0 (penyebut = jumlah
    keputusan), supaya kebijakan yang sering berhenti tidak untung."""
    cp = build_inmemory_control_plane()
    svc = cp.services
    specs = synthetic_candidates()
    for spec in specs:
        svc.register_candidate.execute(candidate_from_spec(spec))
    for task_id, answer in world.oracle.items():
        svc.register_oracle_answer.execute(task_id, answer)

    policy = svc.create_policy.execute(create_policy_cmd(C.CreatePolicyIn(
        kind=kind, seed=seed, alpha=alpha,
        feature_spec=C.FeatureSpecIn(step_cap=20, budget_task_cap=3.0, n_max=1),
        allowed_permissions=sorted({p for s in specs for p in s.permissions}), n_max=1,
        caps=C.BudgetCapsIn(incident_cost_cap=1.0, incident_latency_cap_ms=300_000, task_cost_cap=3.0),
        static_map=STATIC_MAP, init_state=init_state if kind == "P" else None,
    )))

    adapter, client = SyntheticHostAdapter(world), InProcessControlPlaneClient(svc)
    for incident in incidents:
        handle_fault(incident, adapter, client, policy.policy_id)

    records = cp.store.audit_records
    decisions = sum(r["event"] == "decision" for r in records)
    reward = sum(r["reward"] for r in records if r["event"] == "result") / decisions
    state = svc.snapshot_policy.execute(policy.policy_id)["selector_state"] if kind == "P" else None
    return reward, state
