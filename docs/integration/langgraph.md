# LangGraph example

A complete example: a two-node LangGraph graph whose search tool is down, a fault handler around the node, and two recovery candidates (retry and a backup tool). It runs as written. It needs `langgraph`, which is not a dependency of ArcLayer.

## Where ArcLayer plugs in

In LangGraph a node is a plain function from state to a state update, and an exception raised inside it ends the run. ArcLayer plugs in at the node: wrap the node function (`guarded` below) so that a failure goes to `layer.handle_fault` instead of ending the run. The graph itself, its nodes and its edges, does not change; only `add_node` receives the wrapped function. To get finer granularity, wrap a single tool call inside a node the same way.

```python
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
```

## What happens

1. The `search` node raises `ToolError`.
2. `guarded` packs the failure into a `NodeFault` and calls `layer.handle_fault`.
3. `LangGraphAdapter.to_fault_event` describes the fault (class, agent, budget, what the host can do).
4. The gate checks both candidates, and LinUCB picks one. The first pick is a guess, because nothing has been learned yet.
5. The executor for that candidate runs in your process and stores the recovered update on the fault.
6. ArcLayer verifies the result, computes the reward and updates the policy for the candidate that ran.
7. `guarded` returns the recovered update, so the graph carries on as if the node had succeeded, or re-raises the original error when recovery failed or was refused.

Output with `seed=1`:

```
q0: not recovered
cached result for q1 -> done
cached result for q2 -> done
cached result for q3 -> done
cached result for q4 -> done
cached result for q5 -> done
cached result for q6 -> done
cached result for q7 -> done
cached result for q8 -> done
cached result for q9 -> done
{'retry': 1, 'use_backup': 9}
```

The first fault went to `retry`, which failed because the primary tool is down. After that failure ArcLayer preferred `use_backup`, which works. The same run with seeds 2 to 5 gave the same result.

## Notes for a real graph

- Async graphs: make the wrapper an `async def` node and `await layer.handle_fault_async(...)`. Executors stay synchronous functions.
- Send a real `prior_incidents_in_task`. ArcLayer trusts the host's count when it applies the per-task cap `n_max`.
- Fill `cost_used` and `tokens_used` from your LLM usage, and set the policy's cost caps in the same unit.
- Use your own run id and step counter for `run_id` and `step_index`.
- Pass a SQLite URL to `ArcLayer` to keep what the policy learns between runs.
- A refused or failed recovery re-raises the original error, so the error handling you already have keeps working.
