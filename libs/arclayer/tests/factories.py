"""Factory objek domain untuk test. Nilai default membentuk insiden yang 'sehat'
sehingga setiap test cukup meng-override field yang relevan."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from arclayer.domain.enums import FaultClass, LabelSource, OrchestrationPattern, Precondition
from arclayer.domain.models import Candidate, FaultEvent

ALL_CAPS = ("retry_step", "repair_tool", "replan", "resend_handoff", "review_answer", "rollback")


def make_event(**overrides) -> FaultEvent:
    base = FaultEvent(
        run_id="run-1",
        task_id="task-1",
        step_index=3,
        step_total_estimate=10,
        occurred_at=datetime(2026, 10, 14, tzinfo=timezone.utc),
        active_agent="web_surfer",
        agent_role="worker",
        orchestration=OrchestrationPattern.CENTRALIZED,
        fault_class=FaultClass.TOOL_FAILURE,
        fault_confidence=None,
        label_source=LabelSource.INJECTOR,
        fault_description="search tool returned HTTP 500",
        last_messages_summary="orchestrator asked web_surfer to search",
        checkpoint_id="ckpt-3",
        checkpoint_restorable=True,
        step_repeatable=True,
        orchestrator_accessible=True,
        available_artifacts=("page.html",),
        tool_name="web_search",
        tool_error_code="HTTP_500",
        tool_duration_ms=1200,
        budget_remaining_cost=2.0,
        budget_remaining_tokens=None,
        time_remaining_ms=600_000,
        prior_incidents_in_task=0,
        host_id="host-a",
        policy_instance_id="pol-1",
        host_capabilities=ALL_CAPS,
    )
    return replace(base, **overrides)


def make_candidate(**overrides) -> Candidate:
    base = Candidate(
        candidate_id="h1_retry",
        version="1",
        description="Menjalankan ulang langkah gagal pada agen yang sama",
        capabilities=("retry_step",),
        supported_classes=None,
        required_preconditions=(Precondition.STEP_REPEATABLE,),
        optional_preconditions=(),
        required_host_capabilities=("retry_step",),
        max_cost=0.15,
        max_latency_ms=60_000,
        permissions=("rerun_step",),
        verifier_id="benchmark_task_pass",
        enabled=True,
    )
    return replace(base, **overrides)


def table6_candidates() -> tuple[Candidate, ...]:
    """Enam kandidat awal Tabel 6 usulan."""
    return (
        make_candidate(),
        make_candidate(
            candidate_id="h2_tool_repair",
            description="Memperbaiki argumen atau memakai tool gratis alternatif yang diizinkan",
            capabilities=("repair_tool",),
            supported_classes=(FaultClass.TOOL_FAILURE, FaultClass.TIMEOUT),
            required_preconditions=(Precondition.TOOL_STATUS_AVAILABLE,),
            required_host_capabilities=("repair_tool",),
            max_cost=0.2,
            permissions=("call_allowed_tool",),
        ),
        make_candidate(
            candidate_id="h3_replanner",
            description="Memperbarui rencana orchestrator secara terarah",
            capabilities=("replan",),
            supported_classes=(FaultClass.PLAN_ERROR,),
            required_preconditions=(Precondition.ORCHESTRATOR_MESSAGE_ACCESS,),
            required_host_capabilities=("replan",),
            max_cost=0.3,
            permissions=("edit_plan",),
        ),
        make_candidate(
            candidate_id="h4_handoff_completer",
            description="Menyusun ulang konteks yang hilang dari state lalu mengirim ulang pesan",
            capabilities=("resend_handoff",),
            supported_classes=(FaultClass.HANDOFF_INCOMPLETE, FaultClass.TOOL_OUTPUT_UNUSED),
            required_preconditions=(Precondition.STATE_SUMMARY_AVAILABLE,),
            required_host_capabilities=("resend_handoff",),
            max_cost=0.25,
            permissions=("resend_message",),
        ),
        make_candidate(
            candidate_id="h5_verification_reviewer",
            description="Memeriksa bukti dan menurunkan ulang jawaban sebelum diserahkan",
            capabilities=("review_answer",),
            supported_classes=(FaultClass.INSUFFICIENT_VERIFICATION,),
            required_preconditions=(),
            optional_preconditions=(Precondition.EVIDENCE_ARTIFACT_AVAILABLE,),
            required_host_capabilities=("review_answer",),
            max_cost=0.25,
            permissions=("review_answer",),
        ),
        make_candidate(
            candidate_id="h6_guided_rollback",
            description="Kembali ke checkpoint sebelum fault dengan panduan perbaikan satu langkah",
            capabilities=("rollback", "guided_repair"),
            supported_classes=(FaultClass.PLAN_ERROR, FaultClass.HANDOFF_INCOMPLETE),
            required_preconditions=(Precondition.CHECKPOINT_AVAILABLE,),
            required_host_capabilities=("rollback",),
            max_cost=0.4,
            max_latency_ms=180_000,
            permissions=("load_checkpoint", "inject_guidance"),
        ),
    )


ALL_PERMISSIONS = frozenset(
    p for c in table6_candidates() for p in c.permissions
)
