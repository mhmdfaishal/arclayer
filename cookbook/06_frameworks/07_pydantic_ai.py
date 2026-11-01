"""A Pydantic AI agent with a fault handler.

A complete Pydantic AI host with ArcLayer plugged in at one place: a tool function is wrapped so a
failure inside it goes to ArcLayer, which picks a recovery, the host runs it, and the agent carries on.
A scripted FunctionModel stands in for the LLM, so the example runs offline and needs no API key.
Requires `pydantic-ai-slim`, which is not a dependency of ArcLayer (tested with 2.64.0).

Run from the repository root:
    PYTHONPATH=libs/arclayer python cookbook/06_frameworks/07_pydantic_ai.py
"""

import functools
from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter
from typing import Callable

import pydantic_ai
from pydantic_ai import Agent  # your host framework
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from arclayer import ArcLayer  # the library
from arclayer.contracts import CandidateSpec, ExecutionResultIn, FaultEventIn, Terminal


# ---- 1. Your Pydantic AI host: nothing ArcLayer-specific in these tools -----------------------
pydantic_ai.BANNER_ENABLED = False  # keeps the first-run banner (stderr, no network) out of the example's output


class ToolError(Exception):
    pass


async def search(query: str) -> str:  # the primary tool, down in this demo
    raise ToolError("search API returned 503")


def search_backup(query: str) -> str:  # an alternative way to get the same evidence
    return f"cached result for {query}"


def scripted_llm(messages, info):  # stands in for the LLM: ask for the tool, then answer from its result
    last = messages[-1].parts[-1]
    if isinstance(last, ToolReturnPart):
        return ModelResponse(parts=[TextPart(f"{last.content} -> done")])
    return ModelResponse(parts=[ToolCallPart("search", {"query": "q1"})])


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


class PydanticAIAdapter:  # translates a ToolFault into the contract ArcLayer understands
    host_id = "pydantic-ai-demo"
    capabilities = ["use_backup"]

    def to_fault_event(self, fault, policy_instance_id):
        return FaultEventIn(
            run_id="run-1", task_id=fault.arguments["query"], step_index=0,
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
adapter = PydanticAIAdapter()


# ---- 3. The fault handler: wrap a tool so a failure goes to ArcLayer instead of ending the run --
def guarded(name, tool, backup):
    @functools.wraps(tool)  # Pydantic AI builds the model-facing schema from the wrapped signature
    async def run(**arguments):
        try:
            return await tool(**arguments)
        except Exception as error:
            fault = ToolFault(name, arguments, error, backup)
            # an async tool runs on the event loop: the sync handle_fault would block it while the recovery runs
            await layer.handle_fault_async(fault, adapter, policy_id)  # choose, run and score a recovery
            if fault.recovered is not None:
                return fault.recovered  # the agent carries on as if the tool had succeeded
            raise  # recovery failed or was refused: the original error ends the run

    return run


# ---- 4. Agent wiring: the only change is that "search" is registered wrapped -------------------
agent = Agent(FunctionModel(scripted_llm), tools=[guarded("search", search, backup=search_backup)])

print(agent.run_sync("q1").output)  # cached result for q1 -> done
