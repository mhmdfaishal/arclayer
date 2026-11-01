"""A CrewAI crew with a fault handler.

A complete CrewAI host (Agent, Task, Crew, kickoff) with ArcLayer plugged in at one place: a tool is
wrapped so a failure inside it goes to ArcLayer, which picks a recovery, the host runs it, and the agent
carries on. A scripted model replaces the LLM, so the run needs no network and no API key.
Requires `crewai`, which is not a dependency of ArcLayer (tested with 1.15.33).

Run from the repository root:
    PYTHONPATH=libs/arclayer python cookbook/06_frameworks/04_crewai.py
"""

import atexit
import os
import shutil
import tempfile

# CrewAI phones home and writes credentials, settings and a database under the user's home directory.
# Switch the telemetry off and point HOME at a throwaway directory, before CrewAI is imported, so a
# run neither sends anything nor leaves anything behind. The cleanup is registered first so it runs last.
_scratch = tempfile.mkdtemp(prefix="arclayer-crewai-")
atexit.register(shutil.rmtree, _scratch, ignore_errors=True)
os.environ.update(
    HOME=_scratch, CREWAI_STORAGE_DIR=_scratch, CREWAI_DISABLE_TELEMETRY="true", OTEL_SDK_DISABLED="true",
    CREWAI_TRACING_ENABLED="false", CREWAI_DISABLE_VERSION_CHECK="true",
)

from dataclasses import dataclass  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from time import perf_counter  # noqa: E402
from typing import Callable  # noqa: E402

from crewai import Agent, Crew, Task  # noqa: E402  # your host framework
from crewai.llms.base_llm import BaseLLM  # noqa: E402
from crewai.tools import tool  # noqa: E402

from arclayer import ArcLayer  # noqa: E402  # the library
from arclayer.contracts import CandidateSpec, ExecutionResultIn, FaultEventIn, Terminal  # noqa: E402


# ---- 1. Your CrewAI host: nothing ArcLayer-specific in these tools and this model --------------
class ToolError(Exception):
    pass


@tool("search")
def search(question: str) -> str:
    """Search for evidence about a question."""
    raise ToolError("search API returned 503")  # the primary tool, down in this demo


def search_backup(question):  # an alternative way to get the same evidence
    return f"cached result for {question}"


class ScriptedLLM(BaseLLM):  # stands in for a real model: call the tool once, then answer from its output
    llm_type: str = "scripted"

    def call(self, messages, tools=None, callbacks=None, available_functions=None, from_task=None,
             from_agent=None, response_model=None):
        seen = [m["content"] for m in messages if m["role"] == "assistant" and "Observation:" in m["content"]]
        if not seen:
            return 'Thought: I need evidence\nAction: search\nAction Input: {"question": "q1"}'
        evidence = seen[-1].split("Observation:", 1)[1].strip().splitlines()[0]
        return f"Thought: I now know the final answer\nFinal Answer: {evidence} -> done"

    def get_input_tokens_count(self, messages, tools=None, response_model=None):
        return 0  # the base class would log an estimate warning on every call


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


class CrewAIAdapter:  # translates a ToolFault into the contract ArcLayer understands
    host_id = "crewai-demo"
    capabilities = ["use_backup"]

    def to_fault_event(self, fault, policy_instance_id):
        return FaultEventIn(
            run_id="run-1", task_id=fault.arguments["question"], step_index=0,
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
adapter = CrewAIAdapter()


# ---- 3. The fault handler: wrap a tool so a failure goes to ArcLayer instead of reaching the agent
def guarded(base_tool, backup):
    def run(**arguments):
        try:
            return base_tool.func(**arguments)
        except Exception as error:
            fault = ToolFault(base_tool.name, arguments, error, backup)
            # Sync call on purpose: CrewAI runs a sync tool function in a worker thread, so blocking here
            # does not stall an event loop. For an async tool, `await layer.handle_fault_async(...)` instead.
            layer.handle_fault(fault, adapter, policy_id)  # choose, run and score a recovery
            if fault.recovered is not None:
                return fault.recovered  # the agent sees a normal tool result
            raise  # recovery failed or was refused: the original error surfaces

    # CrewAI executes `Tool.func` both through `run()` and through its structured tool, so replacing it
    # covers every call path; the name, description and argument schema stay those of the original.
    return base_tool.model_copy(update={"func": run})


# ---- 4. Crew wiring: the only change is that "search" is registered wrapped --------------------
agent = Agent(
    role="researcher", goal="Answer the question from evidence", backstory="A careful analyst.",
    llm=ScriptedLLM(model="scripted"), tools=[guarded(search, backup=search_backup)], allow_delegation=False,
)
task = Task(description="Answer the question q1.", expected_output="One line with the evidence.", agent=agent)
crew = Crew(agents=[agent], tasks=[task])

print(crew.kickoff().raw)  # cached result for q1 -> done
