from arclayer.domain.enums import Precondition
from arclayer.domain.models import FaultEvent


def precondition_satisfied(p: Precondition, event: FaultEvent) -> bool:
    """Prasyarat dievaluasi hanya dari FaultEvent, tidak dari state internal host."""
    match p:
        case Precondition.STEP_REPEATABLE:
            return event.step_repeatable
        case Precondition.TOOL_STATUS_AVAILABLE:
            return event.tool_name is not None or event.tool_error_code is not None
        case Precondition.ORCHESTRATOR_MESSAGE_ACCESS:
            return event.orchestrator_accessible
        case Precondition.STATE_SUMMARY_AVAILABLE:
            return bool(event.last_messages_summary.strip())
        case Precondition.EVIDENCE_ARTIFACT_AVAILABLE:
            return len(event.available_artifacts) > 0
        case Precondition.CHECKPOINT_AVAILABLE:
            # ID checkpoint saja tidak cukup: host harus menyatakan bisa dipulihkan.
            return event.checkpoint_id is not None and event.checkpoint_restorable
    raise ValueError(f"precondition tidak dikenal: {p}")
