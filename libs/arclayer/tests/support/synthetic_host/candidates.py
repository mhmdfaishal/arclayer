"""Enam kandidat awal (Tabel 6 usulan) dalam bentuk kontrak publik. Salinan sengaja
terpisah dari tests.factories karena kode produksi tidak boleh mengimpor test; kesetaraan
keduanya dijaga oleh test."""

from __future__ import annotations

from arclayer.contracts import CandidateSpec, FaultClass, Precondition


def synthetic_candidates() -> list[CandidateSpec]:
    def spec(**kw) -> CandidateSpec:
        base = dict(
            version="1", supported_classes="*", required_preconditions=[Precondition.STEP_REPEATABLE],
            optional_preconditions=[], max_cost=0.15, max_latency_ms=60_000, verifier_id="benchmark_task_pass",
            enabled=True,
        )
        base.update(kw)
        return CandidateSpec(**base)

    return [
        spec(
            candidate_id="h1_retry", description="Menjalankan ulang langkah gagal pada agen yang sama",
            capabilities=["retry_step"], required_host_capabilities=["retry_step"], permissions=["rerun_step"],
        ),
        spec(
            candidate_id="h2_tool_repair",
            description="Memperbaiki argumen atau memakai tool gratis alternatif yang diizinkan",
            capabilities=["repair_tool"], supported_classes=[FaultClass.TOOL_FAILURE, FaultClass.TIMEOUT],
            required_preconditions=[Precondition.TOOL_STATUS_AVAILABLE], required_host_capabilities=["repair_tool"],
            max_cost=0.2, permissions=["call_allowed_tool"],
        ),
        spec(
            candidate_id="h3_replanner", description="Memperbarui rencana orchestrator secara terarah",
            capabilities=["replan"], supported_classes=[FaultClass.PLAN_ERROR],
            required_preconditions=[Precondition.ORCHESTRATOR_MESSAGE_ACCESS], required_host_capabilities=["replan"],
            max_cost=0.3, permissions=["edit_plan"],
        ),
        spec(
            candidate_id="h4_handoff_completer",
            description="Menyusun ulang konteks yang hilang dari state lalu mengirim ulang pesan",
            capabilities=["resend_handoff"],
            supported_classes=[FaultClass.HANDOFF_INCOMPLETE, FaultClass.TOOL_OUTPUT_UNUSED],
            required_preconditions=[Precondition.STATE_SUMMARY_AVAILABLE],
            required_host_capabilities=["resend_handoff"], max_cost=0.25, permissions=["resend_message"],
        ),
        spec(
            candidate_id="h5_verification_reviewer",
            description="Memeriksa bukti dan menurunkan ulang jawaban sebelum diserahkan",
            capabilities=["review_answer"], supported_classes=[FaultClass.INSUFFICIENT_VERIFICATION],
            required_preconditions=[], optional_preconditions=[Precondition.EVIDENCE_ARTIFACT_AVAILABLE],
            required_host_capabilities=["review_answer"], max_cost=0.25, permissions=["review_answer"],
        ),
        spec(
            candidate_id="h6_guided_rollback",
            description="Kembali ke checkpoint sebelum fault dengan panduan perbaikan satu langkah",
            capabilities=["rollback", "guided_repair"],
            supported_classes=[FaultClass.PLAN_ERROR, FaultClass.HANDOFF_INCOMPLETE],
            required_preconditions=[Precondition.CHECKPOINT_AVAILABLE], required_host_capabilities=["rollback"],
            max_cost=0.4, max_latency_ms=180_000, permissions=["load_checkpoint", "inject_guidance"],
        ),
    ]
