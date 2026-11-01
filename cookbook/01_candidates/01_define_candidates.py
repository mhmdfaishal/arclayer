"""Defining recovery candidates.

A CandidateSpec says what a recovery needs and what it may do. ArcLayer never runs it: the executor
in your host does. This example registers three candidates, then disables one.

Run from the repository root:
    PYTHONPATH=libs/arclayer python cookbook/01_candidates/01_define_candidates.py
"""

from arclayer import ArcLayer, Conflict
from arclayer.contracts import CandidateSpec

candidates = [
    CandidateSpec(
        candidate_id="retry",
        version="1",
        description="Run the failed step again on the same agent",
        capabilities=["retry_step"],
        supported_classes="*",  # suits every fault class; a hint for the policy, not a filter
        required_preconditions=["STEP_REPEATABLE"],  # the fault event must say the step can be repeated
        required_host_capabilities=["retry_step"],  # the host adapter must declare this capability
        max_cost=0.2,
        max_latency_ms=60_000,
        permissions=["rerun_step"],  # the only actions it may take
        verifier_id="task_completed",
    ),
    CandidateSpec(
        candidate_id="replan",
        version="1",
        description="Rewrite the orchestrator's plan with guidance",
        capabilities=["replan"],
        supported_classes=["plan_error"],
        required_preconditions=["ORCHESTRATOR_MESSAGE_ACCESS"],
        required_host_capabilities=["replan"],
        max_cost=0.3,
        max_latency_ms=60_000,
        permissions=["edit_plan"],
        verifier_id="task_completed",
    ),
    CandidateSpec(
        candidate_id="rollback",
        version="1",
        description="Return to the checkpoint before the fault and continue with a repair hint",
        capabilities=["rollback", "guided_repair"],
        supported_classes=["plan_error", "handoff_incomplete"],
        required_preconditions=["CHECKPOINT_AVAILABLE"],
        required_host_capabilities=["rollback"],
        max_cost=0.4,
        max_latency_ms=180_000,
        permissions=["load_checkpoint", "inject_guidance"],
        verifier_id="task_completed",
    ),
]

layer = ArcLayer(None, candidates=candidates)

for spec in layer.candidates():
    classes = spec.supported_classes if spec.supported_classes == "*" else [c.value for c in spec.supported_classes]
    needs = [p.value for p in spec.required_preconditions]
    print(f"{spec.candidate_id:<9} classes={classes} needs={needs} may={spec.permissions}")

try:
    layer.register_candidate(candidates[0])
except Conflict as error:
    print("registering the same id twice:", type(error).__name__)

layer.set_candidate_enabled("rollback", False)
policy_id = layer.create_policy("P", seed=1)
print("candidates in a policy created after disabling rollback:", layer.get_policy(policy_id).candidate_ids)
