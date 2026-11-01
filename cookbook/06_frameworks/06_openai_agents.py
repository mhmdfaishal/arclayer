"""An OpenAI Agents SDK agent with a fault handler.

A complete OpenAI Agents SDK host with ArcLayer plugged in at one place: a tool function is wrapped so a
failure inside it goes to ArcLayer, which picks a recovery, the host runs it, and the agent carries on.
Requires `openai-agents`, which is not a dependency of ArcLayer (tested with 0.24.0).

Run from the repository root:
    PYTHONPATH=libs/arclayer python cookbook/06_frameworks/06_openai_agents.py
"""

import asyncio
import functools
from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Callable

from agents import Agent, Model, ModelResponse, Runner, Usage, function_tool, set_tracing_disabled  # your host framework
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText

from arclayer import ArcLayer  # the library
from arclayer.contracts import CandidateSpec, ExecutionResultIn, FaultEventIn, Terminal

# The SDK uploads traces to OpenAI by default. This demo runs offline, so switch that off.
set_tracing_disabled(True)


# ---- 1. Your Agents SDK host: nothing ArcLayer-specific in these tools and this model ----------
class ToolError(Exception):
    pass


async def search(question: str) -> str:  # the primary tool, down in this demo
    raise ToolError("search API returned 503")


def search_backup(question: str) -> str:  # an alternative way to get the same evidence
    return f"cached result for {question}"


class ScriptedModel(Model):  # stands in for the LLM: asks for the tool, then answers from its output
    async def get_response(self, system_instructions, input, model_settings, tools, output_schema, handoffs,
                           tracing, *, previous_response_id, conversation_id, prompt):
        results = [item["output"] for item in input if isinstance(item, dict) and item.get("type") == "function_call_output"]
        if not results:
            item = ResponseFunctionToolCall(
                id="call-1", call_id="call-1", type="function_call", name="search", arguments='{"question": "q1"}',
            )
        else:
            item = ResponseOutputMessage(
                id="msg-1", type="message", role="assistant", status="completed",
                content=[ResponseOutputText(text=f"{results[-1]} -> done", type="output_text", annotations=[])],
            )
        return ModelResponse(output=[item], usage=Usage(), response_id=None)

    def stream_response(self, *args, **kwargs):  # Runner.run does not stream
        raise NotImplementedError


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
    args: tuple
    error: Exception
    backup: Callable[..., Any]
    recovered: Any = None  # filled by the executor when the recovery works


class UseBackup:  # the recovery (self-healing): your own logic, run when ArcLayer picks "use_backup"
    candidate_id = "use_backup"

    def execute(self, command, fault):
        started = perf_counter()
        fault.recovered = fault.backup(*fault.args)
        return ExecutionResultIn(
            incident_id=command.incident_id, candidate_id=self.candidate_id, terminal=Terminal.TASK_COMPLETED,
            cost_used=0.0, tokens_used=0, latency_ms=int((perf_counter() - started) * 1000),
            actions_performed=["call_backup"],
        )


class AgentsSdkAdapter:  # translates a ToolFault into the contract ArcLayer understands
    host_id = "openai-agents-demo"
    capabilities = ["use_backup"]

    def to_fault_event(self, fault, policy_instance_id):
        return FaultEventIn(
            run_id="run-1", task_id=fault.args[0], step_index=0,
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
adapter = AgentsSdkAdapter()


# ---- 3. The fault handler: wrap a tool so a failure goes to ArcLayer instead of ending the run --
def guarded(tool, backup):
    @functools.wraps(tool)  # the SDK builds the tool's name, description and schema from the function it is given
    async def run(*args):
        try:
            return await tool(*args)
        except Exception as error:
            fault = ToolFault(tool.__name__, args, error, backup)
            # The SDK runs tools on its event loop; the sync handle_fault would block it while ArcLayer works.
            await layer.handle_fault_async(fault, adapter, policy_id)  # choose, run and score a recovery
            if fault.recovered is not None:
                return fault.recovered  # the agent carries on as if the tool had succeeded
            raise  # recovery failed or was refused: the SDK reports the error to the model

    return run


# ---- 4. Agent wiring: the only change is that "search" is registered wrapped -------------------
agent = Agent(
    name="researcher",
    instructions="Answer the question using the search tool.",
    model=ScriptedModel(),
    tools=[function_tool(guarded(search, backup=search_backup))],
)

result = asyncio.run(Runner.run(agent, "q1"))
print(result.final_output)  # cached result for q1 -> done
