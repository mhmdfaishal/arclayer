"""An Agno agent with a fault handler.

A complete Agno host with ArcLayer plugged in at one place: a tool hook on the `search` tool sends a
failure to ArcLayer, which picks a recovery, the host runs it, and the agent carries on. The model is
a scripted stand-in, so the example runs offline, but the agent loop and the tool call are Agno's own.
Requires `agno`, which is not a dependency of ArcLayer (tested with 3.1.12).

Run from the repository root:
    PYTHONPATH=libs/arclayer python cookbook/06_frameworks/03_agno.py
"""

import json
import os

os.environ["AGNO_TELEMETRY"] = "false"  # Agno phones home by default; keep the example offline

from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter
from typing import Callable

from agno.agent import Agent  # your host framework
from agno.models.base import Model
from agno.models.response import ModelResponse
from agno.tools import Function

from arclayer import ArcLayer  # the library
from arclayer.contracts import CandidateSpec, ExecutionResultIn, FaultEventIn, Terminal


# ---- 1. Your Agno host: nothing ArcLayer-specific in these tools and this model ----------------
class ToolError(Exception):
    pass


def search(question: str) -> str:  # the primary tool, down in this demo
    """Search for evidence about a question."""
    raise ToolError("search API returned 503")


def search_backup(question: str) -> str:  # an alternative way to get the same evidence
    return f"cached result for {question}"


@dataclass
class ScriptedModel(Model):
    """Stands in for an LLM: calls `search` for the question, then answers from the tool result."""

    id: str = "scripted"

    def invoke(self, messages, **kwargs):
        last = messages[-1]
        if last.role == "tool":
            return ModelResponse(role="assistant", content=f"{last.content} -> done")
        call = {"id": "call-1", "type": "function",
                "function": {"name": "search", "arguments": json.dumps({"question": last.content})}}
        return ModelResponse(role="assistant", tool_calls=[call])

    async def ainvoke(self, *args, **kwargs):
        return self.invoke(*args, **kwargs)

    def invoke_stream(self, *args, **kwargs):
        raise NotImplementedError

    def ainvoke_stream(self, *args, **kwargs):
        raise NotImplementedError

    def _parse_provider_response(self, response, **kwargs):
        return response

    def _parse_provider_response_delta(self, response):
        return response


# ---- 2. ArcLayer: what it may choose from, how a fault is described, how a recovery runs -------
CANDIDATES = [
    CandidateSpec(
        candidate_id="use_backup",  # the executor with the same candidate_id runs it
        version="1",
        description="Run the tool's backup",  # embedded: its similarity to the fault is one feature
        capabilities=["use_backup"],
        supported_classes=["tool_failure", "timeout"],  # fault classes it suits ("*" = all); a hint, not a filter
        required_host_capabilities=["use_backup"],  # must be listed in the adapter's capabilities
        max_cost=0.2, max_latency_ms=60_000,  # the gate skips it when the remaining budget is smaller
        permissions=["call_backup"],  # actions it may take; any other action is a violation
        verifier_id="task_completed",  # success = the host reports task_completed
    ),
]


@dataclass
class ToolFault:  # what your host hands to ArcLayer when a tool fails
    tool: str
    arguments: dict
    error: Exception
    backup: Callable[..., str]
    recovered: str | None = None  # filled by the executor when the recovery works


class UseBackup:  # the recovery (self-healing): your own logic, run when ArcLayer picks "use_backup"
    candidate_id = "use_backup"

    def execute(self, command, fault):
        started = perf_counter()
        fault.recovered = fault.backup(**fault.arguments)
        return ExecutionResultIn(
            incident_id=command.incident_id, candidate_id=self.candidate_id, terminal=Terminal.TASK_COMPLETED,
            cost_used=0.0, tokens_used=0, latency_ms=int((perf_counter() - started) * 1000),
            actions_performed=["call_backup"],
        )


class AgnoAdapter:  # translates a ToolFault into the contract ArcLayer understands
    host_id = "agno-demo"
    capabilities = ["use_backup"]

    def to_fault_event(self, fault, policy_instance_id):
        return FaultEventIn(
            run_id="run-1", task_id=str(fault.arguments), step_index=0,
            occurred_at=datetime.now(timezone.utc), active_agent=fault.tool, agent_role="worker",
            orchestration="sequential", fault_class="tool_failure", label_source="deterministic",
            fault_description=str(fault.error), budget_remaining_cost=2.0, time_remaining_ms=120_000,
            prior_incidents_in_task=0, host_id=self.host_id, policy_instance_id=policy_instance_id,
            host_capabilities=self.capabilities,
        )

    def executors(self):
        return {"use_backup": UseBackup()}


layer = ArcLayer(None, candidates=CANDIDATES)  # None keeps state in memory; pass a SQLite URL to keep learning
policy_id = layer.create_policy("P", seed=1)
adapter = AgnoAdapter()


# ---- 3. The fault handler: a tool hook, so a failure goes to ArcLayer instead of ending the run ---
def guarded(backup):
    # Agno calls a tool hook around the tool and hands it the next link in `function_call`.
    # This hook is sync, so it calls the sync `handle_fault`; under `agent.arun` make it an
    # `async def` and `await layer.handle_fault_async(...)` so the event loop is not blocked.
    def hook(function_name, function_call, arguments):
        try:
            return function_call(**arguments)
        except Exception as error:
            fault = ToolFault(function_name, dict(arguments), error, backup)
            layer.handle_fault(fault, adapter, policy_id)  # choose, run and score a recovery
            if fault.recovered is not None:
                return fault.recovered  # the agent carries on as if the tool had succeeded
            raise  # recovery failed or was refused: the original error surfaces

    return hook


# ---- 4. Agent wiring: the only change is that "search" is registered with the hook -------------
agent = Agent(
    model=ScriptedModel(),
    tools=[Function(name="search", entrypoint=search, tool_hooks=[guarded(search_backup)])],
)

print(agent.run("q1").content)  # cached result for q1 -> done
