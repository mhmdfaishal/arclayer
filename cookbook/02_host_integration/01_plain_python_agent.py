"""A fault handler around a tool, in plain Python.

No agent framework: a decorator wraps a tool function. When the tool fails, the failure goes to
ArcLayer, a recovery runs, and the caller receives a value as if the tool had worked. The same
pattern fits any framework that lets you wrap a function.

Run from the repository root:
    PYTHONPATH=libs/arclayer python cookbook/02_host_integration/01_plain_python_agent.py
"""

import functools
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from arclayer import ArcLayer
from arclayer.contracts import CandidateSpec, ExecutionResultIn, FaultEventIn, Terminal


class ToolDown(Exception):
    pass


@dataclass
class ToolFault:
    """What the host hands to ArcLayer when a tool call fails."""

    tool: str
    args: tuple
    error: Exception
    backup: Callable[..., Any]
    result: Any = None
    recovered: bool = False


class UseCache:
    candidate_id = "use_cache"

    def execute(self, command, fault):
        fault.result = fault.backup(*fault.args)  # your own recovery logic
        fault.recovered = True
        return ExecutionResultIn(
            incident_id=command.incident_id, candidate_id=self.candidate_id, terminal=Terminal.TASK_COMPLETED,
            cost_used=0.0, tokens_used=0, latency_ms=5, actions_performed=["read_cache"],
        )


class Adapter:
    host_id = "plain-python"
    capabilities = ["use_cache"]

    def to_fault_event(self, fault, policy_instance_id):
        return FaultEventIn(
            run_id="run-1", task_id=f"{fault.tool}:{fault.args}", step_index=1,
            occurred_at=datetime.now(timezone.utc), active_agent=fault.tool, agent_role="tool",
            orchestration="sequential", fault_class="tool_failure", label_source="deterministic",
            fault_description=str(fault.error), budget_remaining_cost=2.0, time_remaining_ms=120_000,
            prior_incidents_in_task=0, host_id=self.host_id, policy_instance_id=policy_instance_id,
            host_capabilities=self.capabilities,
        )

    def executors(self):
        return {"use_cache": UseCache()}


layer = ArcLayer(None, candidates=[CandidateSpec(
    candidate_id="use_cache", version="1", description="Answer from the cache when the live tool is down",
    capabilities=["use_cache"], supported_classes=["tool_failure", "timeout"],
    required_host_capabilities=["use_cache"], max_cost=0.2, max_latency_ms=60_000,
    permissions=["read_cache"], verifier_id="task_completed",
)])
policy_id = layer.create_policy("P", seed=1)
adapter = Adapter()


def self_healing(backup):
    """The fault handler: wrap any tool so a failure is handed to ArcLayer."""

    def decorate(tool):
        @functools.wraps(tool)
        def wrapper(*args):
            try:
                return tool(*args)
            except Exception as error:
                fault = ToolFault(tool.__name__, args, error, backup)
                layer.handle_fault(fault, adapter, policy_id)
                if fault.recovered:
                    return fault.result
                raise

        return wrapper

    return decorate


def cached_price(item):
    return {"widget": 9.99}.get(item, 0.0)


@self_healing(backup=cached_price)
def fetch_price(item):
    raise ToolDown("pricing API returned 503")  # the live tool is down


def agent(item):
    """Your agent code: it neither knows nor cares that the tool failed."""
    return f"{item} costs {fetch_price(item)}"


print("the agent says:", agent("widget"))
print("recoveries run:", layer.snapshot_policy(policy_id).selector_state["n"])
