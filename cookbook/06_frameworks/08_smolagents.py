"""A smolagents agent with a fault handler.

A complete smolagents host with ArcLayer plugged in at one place: a tool function is wrapped so a failure
inside it goes to ArcLayer, which picks a recovery, the host runs it, and the agent carries on.
Requires `smolagents`, which is not a dependency of ArcLayer (tested with 1.26.0).

Run from the repository root:
    PYTHONPATH=libs/arclayer python cookbook/06_frameworks/08_smolagents.py
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps
from time import perf_counter
from typing import Callable

from smolagents import ChatMessage, LogLevel, MessageRole, Model, ToolCallingAgent, tool  # your host framework
from smolagents.models import ChatMessageToolCall, ChatMessageToolCallFunction

from arclayer import ArcLayer  # the library
from arclayer.contracts import CandidateSpec, ExecutionResultIn, FaultEventIn, Terminal


# ---- 1. Your smolagents host: nothing ArcLayer-specific in these tools and this model ----------
class ToolError(Exception):
    pass


def search(query: str) -> str:  # the primary tool, down in this demo
    """Search for evidence about a question.

    Args:
        query: The question to search for.
    """
    raise ToolError("search API returned 503")


def search_backup(query: str) -> str:  # an alternative way to get the same evidence
    """Read evidence about a question from the cache.

    Args:
        query: The question to look up.
    """
    return f"cached result for {query}"


class ScriptedModel(Model):  # stands in for the LLM so the demo needs no network and no API key
    def generate(self, messages, stop_sequences=None, response_format=None, tools_to_call_from=None, **kwargs):
        last = messages[-1].content[0]["text"]  # the agent's memory, as the last message
        if last.startswith("Observation:"):  # the tool has answered: finish with it
            evidence = last.removeprefix("Observation:").strip()
            name, arguments = "final_answer", {"answer": f"{evidence} -> done"}
        else:  # first step, or the previous tool call raised: ask for the search
            name, arguments = "search", {"query": "q1"}
        call = ChatMessageToolCall(ChatMessageToolCallFunction(arguments, name), id=f"call-{name}", type="function")
        return ChatMessage(role=MessageRole.ASSISTANT, content="", tool_calls=[call])


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
class ToolFault:  # what your host hands to ArcLayer when a tool call fails
    tool: str
    args: tuple
    kwargs: dict
    error: Exception
    backup: Callable
    recovered: str | None = None  # filled by the executor when the recovery works


class UseBackup:  # the recovery (self-healing): your own logic, run when ArcLayer picks "use_backup"
    candidate_id = "use_backup"

    def execute(self, command, fault):
        started = perf_counter()
        fault.recovered = fault.backup(*fault.args, **fault.kwargs)
        return ExecutionResultIn(
            incident_id=command.incident_id, candidate_id=self.candidate_id, terminal=Terminal.TASK_COMPLETED,
            cost_used=0.0, tokens_used=0, latency_ms=int((perf_counter() - started) * 1000),
            actions_performed=["call_backup"],
        )


class SmolagentsAdapter:  # translates a ToolFault into the contract ArcLayer understands
    host_id = "smolagents-demo"
    capabilities = ["use_backup"]

    def to_fault_event(self, fault, policy_instance_id):
        return FaultEventIn(
            run_id="run-1", task_id=str(fault.kwargs or fault.args), step_index=0,
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
adapter = SmolagentsAdapter()


# ---- 3. The fault handler: wrap a tool function so a failure goes to ArcLayer instead of the agent
def guarded(function, backup):
    # wraps() keeps the signature and docstring: smolagents' @tool builds the tool schema from them
    @wraps(function)
    def run(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Exception as error:
            fault = ToolFault(function.__name__, args, kwargs, error, backup)
            layer.handle_fault(fault, adapter, policy_id)  # choose, run and score a recovery
            if fault.recovered is not None:
                return fault.recovered  # the agent sees the backup's output as if the tool had succeeded
            raise  # recovery failed or was refused: smolagents reports the error to the model

    return run


# ---- 4. Agent wiring: the only change is that "search" is registered wrapped -------------------
agent = ToolCallingAgent(
    tools=[tool(guarded(search, backup=search_backup))],
    model=ScriptedModel(),
    verbosity_level=LogLevel.OFF,  # keeps smolagents' console panels out of the output
)

print(agent.run("Answer question q1"))  # cached result for q1 -> done
