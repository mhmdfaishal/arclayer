"""Why a candidate was rejected.

Before ArcLayer chooses, a gate removes candidates that cannot or must not run. Each rejection
carries a reason code in `command.excluded`. When nothing is left, the command is not "execute".
This is the first place to look when a recovery never runs.

Run from the repository root:
    PYTHONPATH=libs/arclayer python cookbook/01_candidates/03_why_a_candidate_was_rejected.py
"""

from datetime import datetime, timezone

from arclayer import ArcLayer
from arclayer.contracts import CandidateSpec, FaultEventIn


def candidate(candidate_id, **changes):
    fields = dict(
        candidate_id=candidate_id, version="1", description=candidate_id, capabilities=["demo"],
        supported_classes="*", required_host_capabilities=[], max_cost=0.2, max_latency_ms=60_000,
        permissions=["rerun_step"], verifier_id="task_completed",
    )
    return CandidateSpec(**{**fields, **changes})


def event(policy_id, **changes):
    fields = dict(
        run_id="run-1", task_id="task-1", step_index=1, occurred_at=datetime.now(timezone.utc),
        active_agent="researcher", agent_role="worker", orchestration="sequential",
        fault_class="tool_failure", label_source="deterministic", fault_description="tool timeout",
        budget_remaining_cost=2.0, time_remaining_ms=120_000, prior_incidents_in_task=0,
        host_id="cookbook", policy_instance_id=policy_id, host_capabilities=["retry_step"],
    )
    return FaultEventIn(**{**fields, **changes})


layer = ArcLayer(None, candidates=[
    candidate("fits"),
    candidate("needs_checkpoint", required_preconditions=["CHECKPOINT_AVAILABLE"]),
    candidate("needs_rollback_capability", required_host_capabilities=["rollback"]),
    candidate("too_expensive", max_cost=5.0),
    candidate("forbidden_action", permissions=["delete_files"]),
])
policy_id = layer.create_policy("P", seed=1, allowed_permissions=["rerun_step"])

command = layer.post_incident(event(policy_id))
print("action:", command.action.value, "| chosen:", command.candidate_id)
for rejection in command.excluded:
    print(f"  rejected {rejection.candidate_id:<26} {rejection.code}")

print()
command = layer.post_incident(event(policy_id, task_id="task-2", budget_remaining_cost=0.1))
print("with 0.1 budget left -> action:", command.action.value)
for rejection in command.excluded:
    print(f"  rejected {rejection.candidate_id:<26} {rejection.code}")
