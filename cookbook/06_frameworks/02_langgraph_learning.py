"""LangGraph: learning which recovery works.

The same graph with two recovery candidates and ten questions. The primary search tool is down, so
`retry` never helps; ArcLayer tries it once, sees it fail, and from then on picks `use_backup`.
Requires `langgraph`, which is not a dependency of ArcLayer.

Run from the repository root:
    PYTHONPATH=libs/arclayer python cookbook/06_frameworks/02_langgraph_learning.py
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter
from typing import Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from arclayer import ArcLayer
from arclayer.contracts import CandidateSpec, ExecutionResultIn, FaultEventIn, Terminal


class ToolError(Exception):
    pass


class State(TypedDict, total=False):
    question: str
    evidence: str
    answer: str


# 1. Your graph nodes, unchanged. The primary search tool is down in this demo.
def search(state):
    raise ToolError("search API returned 503")


def search_backup(state):
    return {"evidence": f"cached result for {state['question']}"}


def answer(state):
    return {"answer": f"{state['evidence']} -> done"}


# 2. The recovery candidates ArcLayer may choose from.
def candidate(candidate_id, capability, classes, permission, description):
    return CandidateSpec(
        candidate_id=candidate_id, version="1", description=description, capabilities=[capability],
        supported_classes=classes, required_preconditions=[], optional_preconditions=[],
        required_host_capabilities=[capability], max_cost=0.2, max_latency_ms=60_000,
        permissions=[permission], verifier_id="task_completed",
    )


CANDIDATES = [
    candidate("retry", "retry_step", "*", "rerun_step", "Run the failed node again"),
    candidate("use_backup", "use_backup", ["tool_failure", "timeout"], "call_backup", "Run the node's backup tool"),
]


# 3. The host side: what a fault looks like, how to describe it, how to run a candidate.
@dataclass
class NodeFault:
    node: str
    state: dict
    error: Exception
    rerun: Callable[[dict], dict]
    backup: Callable[[dict], dict]
    recovered: dict | None = None  # filled by the executor when recovery works


class Executor:
    def __init__(self, candidate_id, pick, action):
        self.candidate_id, self.pick, self.action = candidate_id, pick, action

    def execute(self, command, fault):
        started = perf_counter()
        try:
            fault.recovered = self.pick(fault)(fault.state)
            terminal = Terminal.TASK_COMPLETED
        except Exception:
            terminal = Terminal.NEW_INCIDENT
        return ExecutionResultIn(
            incident_id=command.incident_id, candidate_id=self.candidate_id, terminal=terminal,
            cost_used=0.0, tokens_used=0, latency_ms=int((perf_counter() - started) * 1000),
            actions_performed=[self.action],
        )


class LangGraphAdapter:
    host_id = "langgraph-demo"
    capabilities = ["retry_step", "use_backup"]

    def to_fault_event(self, fault, policy_instance_id):
        return FaultEventIn(
            run_id="run-1", task_id=fault.state["question"], step_index=0,
            occurred_at=datetime.now(timezone.utc), active_agent=fault.node, agent_role="worker",
            orchestration="sequential",
            fault_class="timeout" if isinstance(fault.error, TimeoutError) else "tool_failure",
            label_source="deterministic", fault_description=str(fault.error),
            budget_remaining_cost=2.0, time_remaining_ms=120_000, prior_incidents_in_task=0,
            host_id=self.host_id, policy_instance_id=policy_instance_id, host_capabilities=self.capabilities,
        )

    def executors(self):
        return {
            "retry": Executor("retry", lambda f: f.rerun, "rerun_step"),
            "use_backup": Executor("use_backup", lambda f: f.backup, "call_backup"),
        }


# 4. The fault handler: wrap a node so a failure goes to ArcLayer instead of ending the run.
layer = ArcLayer(None, candidates=CANDIDATES)  # in memory; pass a SQLite URL to keep what it learns
policy_id = layer.create_policy("P", seed=1)
adapter = LangGraphAdapter()


def guarded(name, node, backup):
    def run(state):
        try:
            return node(state)
        except Exception as error:
            fault = NodeFault(name, dict(state), error, node, backup)
            layer.handle_fault(fault, adapter, policy_id)  # picks, runs and scores a recovery
            if fault.recovered is not None:
                return fault.recovered  # the graph continues as if the node had succeeded
            raise  # safe_stop, escalate or failed recovery: the original error surfaces

    return run


builder = StateGraph(State)
builder.add_node("search", guarded("search", search, search_backup))
builder.add_node("answer", answer)
builder.add_edge(START, "search")
builder.add_edge("search", "answer")
builder.add_edge("answer", END)
graph = builder.compile()

for i in range(10):
    try:
        print(graph.invoke({"question": f"q{i}"})["answer"])
    except ToolError:
        print(f"q{i}: not recovered")
print(layer.snapshot_policy(policy_id).selector_state["n"])  # how often each candidate was chosen
