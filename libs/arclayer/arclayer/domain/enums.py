"""Enum domain. Urutan anggota FaultClass dan OrchestrationPattern menentukan
posisi one-hot di vektor fitur, jadi menambah/mengubah urutan = versi fitur baru."""

from enum import StrEnum


class FaultClass(StrEnum):
    TOOL_FAILURE = "tool_failure"
    TIMEOUT = "timeout"
    TOOL_OUTPUT_UNUSED = "tool_output_unused"
    HANDOFF_INCOMPLETE = "handoff_incomplete"
    PLAN_ERROR = "plan_error"
    INSUFFICIENT_VERIFICATION = "insufficient_verification"


class OrchestrationPattern(StrEnum):
    CENTRALIZED = "centralized"
    SEQUENTIAL = "sequential"
    CONCURRENT = "concurrent"
    DECENTRALIZED = "decentralized"


class LabelSource(StrEnum):
    DETERMINISTIC = "deterministic"
    INJECTOR = "injector"
    ATTRIBUTION = "attribution"


class Action(StrEnum):
    EXECUTE = "execute"
    SAFE_STOP = "safe_stop"
    ESCALATE = "escalate"


class Precondition(StrEnum):
    STEP_REPEATABLE = "STEP_REPEATABLE"
    TOOL_STATUS_AVAILABLE = "TOOL_STATUS_AVAILABLE"
    ORCHESTRATOR_MESSAGE_ACCESS = "ORCHESTRATOR_MESSAGE_ACCESS"
    STATE_SUMMARY_AVAILABLE = "STATE_SUMMARY_AVAILABLE"
    EVIDENCE_ARTIFACT_AVAILABLE = "EVIDENCE_ARTIFACT_AVAILABLE"
    CHECKPOINT_AVAILABLE = "CHECKPOINT_AVAILABLE"


class RejectionCode(StrEnum):
    DISABLED = "DISABLED"
    PERMISSION_NOT_ALLOWED = "PERMISSION_NOT_ALLOWED"
    HOST_CAPABILITY_MISSING = "HOST_CAPABILITY_MISSING"
    PRECONDITION_UNMET = "PRECONDITION_UNMET"
    OVER_BUDGET = "OVER_BUDGET"
    INCIDENT_LIMIT = "INCIDENT_LIMIT"


class Terminal(StrEnum):
    TASK_COMPLETED = "task_completed"
    NEW_INCIDENT = "new_incident"
    BUDGET_EXHAUSTED = "budget_exhausted"
    EXECUTOR_ERROR = "executor_error"


class IncidentStatus(StrEnum):
    # Status antara (context built, gated, verified, updated) terjadi di dalam satu
    # transaksi use case sehingga tidak dipersistenkan sebagai status tersendiri.
    RECEIVED = "received"
    SAFE_STOPPED = "safe_stopped"
    ESCALATED = "escalated"
    AWAITING_RESULT = "awaiting_result"
    RECOVERED = "recovered"
    FAILED = "failed"
    CENSORED = "censored"


class PolicyKind(StrEnum):
    B0 = "B0"  # tanpa recovery
    B1 = "B1"  # retry
    B2 = "B2"  # pemetaan statis
    B3 = "B3"  # acak dari kandidat lolos gate
    B4 = "B4"  # kesamaan semantik
    P = "P"  # LinUCB usulan
    P_D = "P_D"  # LinUCB tanpa fitur kandidat
    P_F = "P_F"  # LinUCB beku setelah kalibrasi


class FeatureVariant(StrEnum):
    FULL = "full"
    NO_CANDIDATE = "no_candidate"
