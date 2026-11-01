"""A host that dies in the middle of a recovery.

An incident whose result never arrives stays "awaiting_result". A policy in strict mode refuses new
incidents while one is waiting. When an ArcLayer starts it closes the incidents a previous process
left behind (censored, without teaching the policy). Turn that off with
`censor_orphans_on_start=False` if several instances share a database.

Run from the repository root:
    PYTHONPATH=libs/arclayer python cookbook/04_persistence/02_crash_and_orphans.py
"""

import tempfile
from datetime import datetime, timezone

from arclayer import ArcLayer, PolicyBusy
from arclayer.contracts import CandidateSpec, FaultEventIn


def event(task_id, policy_id):
    return FaultEventIn(
        run_id="run-1", task_id=task_id, step_index=1, occurred_at=datetime.now(timezone.utc),
        active_agent="researcher", agent_role="worker", orchestration="sequential",
        fault_class="tool_failure", label_source="deterministic", fault_description="tool timeout",
        budget_remaining_cost=2.0, time_remaining_ms=120_000, prior_incidents_in_task=0,
        host_id="cookbook", policy_instance_id=policy_id, host_capabilities=["retry_step"],
    )


retry = CandidateSpec(
    candidate_id="retry", version="1", description="Run the failed step again", capabilities=["retry_step"],
    supported_classes="*", required_host_capabilities=["retry_step"], max_cost=0.2, max_latency_ms=60_000,
    permissions=["rerun_step"], verifier_id="task_completed",
)

with tempfile.TemporaryDirectory() as folder:
    database = f"sqlite:///{folder}/arclayer.db"

    first_process = ArcLayer(database, candidates=[retry])
    policy_id = first_process.create_policy("P", seed=1, strict_sequential=True)
    command = first_process.post_incident(event("task-1", policy_id))
    print("before the crash:", first_process.incident(command.incident_id).status)
    # The host process dies here. The result is never reported.

    kept = ArcLayer(database, censor_orphans_on_start=False)
    print("restart without censoring:", kept.incident(command.incident_id).status)
    try:
        kept.post_incident(event("task-2", policy_id))
    except PolicyBusy:
        print("the strict policy is stuck behind the orphan (PolicyBusy)")

    restarted = ArcLayer(database)  # the default closes incidents a previous process left waiting
    print("restart with the default:", restarted.incident(command.incident_id).status)
    restarted.post_incident(event("task-2", policy_id))
    print("the policy accepts new incidents again")
