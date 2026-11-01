"""A LangGraph graph with a fault handler.

A complete LangGraph host with ArcLayer plugged in at one place: a node is wrapped so a failure inside
it goes to ArcLayer, which picks a recovery, the host runs it, and the graph carries on.
Requires `langgraph`, which is not a dependency of ArcLayer.

Run from the repository root:
    PYTHONPATH=libs/arclayer python cookbook/06_frameworks/01_langgraph_basic.py
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter
from typing import Callable, TypedDict

from langgraph.graph import END, START, StateGraph  # your host framework

from arclayer import ArcLayer  # the library
from arclayer.contracts import CandidateSpec, ExecutionResultIn, FaultEventIn, Terminal


# ---- 1. Your LangGraph host: nothing ArcLayer-specific in these nodes -------------------------
class ToolError(Exception):
    pass


class State(TypedDict, total=False):
    question: str
    evidence: str
    answer: str


def search(state):  # the primary tool, down in this demo
    raise ToolError("search API returned 503")


def search_backup(state):  # an alternative way to get the same evidence
    return {"evidence": f"cached result for {state['question']}"}


def answer(state):
    return {"answer": f"{state['evidence']} -> done"}


# ---- 2. ArcLayer: what it may choose from, how a fault is described, how a recovery runs -------
CANDIDATES = [
    CandidateSpec(
        candidate_id="use_backup",  # the executor with the same candidate_id runs it
        version="1",
        description="Run the node's backup tool",  # embedded: its similarity to the fault is one feature
        capabilities=["use_backup"],
        supported_classes=["tool_failure", "timeout"],  # fault classes it suits ("*" = all); a hint, not a filter
        required_host_capabilities=["use_backup"],  # must be listed in the adapter's capabilities
        max_cost=0.2, max_latency_ms=60_000,  # the gate skips it when the remaining budget is smaller
        permissions=["call_backup"],  # actions it may take; any other action is a violation
        verifier_id="task_completed",  # success = the host reports task_completed
    ),
]


@dataclass
class NodeFault:  # what your host hands to ArcLayer when a node fails
    node: str
    state: dict
    error: Exception
    backup: Callable[[dict], dict]
    recovered: dict | None = None  # filled by the executor when the recovery works


class UseBackup:  # the recovery (self-healing): your own logic, run when ArcLayer picks "use_backup"
    candidate_id = "use_backup"

    def execute(self, command, fault):
        started = perf_counter()
        fault.recovered = fault.backup(fault.state)
        return ExecutionResultIn(
            incident_id=command.incident_id, candidate_id=self.candidate_id, terminal=Terminal.TASK_COMPLETED,
            cost_used=0.0, tokens_used=0, latency_ms=int((perf_counter() - started) * 1000),
            actions_performed=["call_backup"],
        )


class LangGraphAdapter:  # translates a NodeFault into the contract ArcLayer understands
    host_id = "langgraph-demo"
    capabilities = ["use_backup"]

    def to_fault_event(self, fault, policy_instance_id):
        return FaultEventIn(
            run_id="run-1", task_id=fault.state["question"], step_index=0,
            occurred_at=datetime.now(timezone.utc), active_agent=fault.node, agent_role="worker",
            orchestration="sequential", fault_class="tool_failure", label_source="deterministic",
            fault_description=str(fault.error), budget_remaining_cost=2.0, time_remaining_ms=120_000,
            prior_incidents_in_task=0, host_id=self.host_id, policy_instance_id=policy_instance_id,
            host_capabilities=self.capabilities,
        )

    def executors(self):
        return {"use_backup": UseBackup()}


layer = ArcLayer(None, candidates=CANDIDATES)  # None keeps state in memory; pass a SQLite URL to keep learning
policy_id = layer.create_policy("P", seed=1)
adapter = LangGraphAdapter()


# ---- 3. The fault handler: wrap a node so a failure goes to ArcLayer instead of ending the run --
def guarded(name, node, backup):
    def run(state):
        try:
            return node(state)
        except Exception as error:
            fault = NodeFault(name, dict(state), error, backup)
            layer.handle_fault(fault, adapter, policy_id)  # choose, run and score a recovery
            if fault.recovered is not None:
                return fault.recovered  # the graph carries on as if the node had succeeded
            raise  # recovery failed or was refused: the original error surfaces

    return run


# ---- 4. Graph wiring: the only change is that "search" is registered wrapped -------------------
builder = StateGraph(State)
builder.add_node("search", guarded("search", search, backup=search_backup))
builder.add_node("answer", answer)
builder.add_edge(START, "search")
builder.add_edge("search", "answer")
builder.add_edge("answer", END)
graph = builder.compile()

print(graph.invoke({"question": "q1"})["answer"])  # cached result for q1 -> done
