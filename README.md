# ArcLayer

A framework-agnostic recovery control layer for LLM multi-agent (agentic) systems, as a Python library.

Your multi-agent system keeps running on whatever framework it already uses. When it detects a fault, it reports the fault to ArcLayer. ArcLayer filters your registered recovery candidates with a feasibility and safety gate, selects one with a LinUCB contextual bandit, receives the verified outcome from the host, and updates its policy. ArcLayer decides; the host acts. It never executes anything inside the host and never calls an LLM.

```
 your host process
 ┌──────────────────────────────┐   fault context    ┌─────────────────────────────────┐
 │ agents, tools, state         │ ────────────────>  │ ArcLayer                        │
 │ + HostAdapter, executors     │ <────────────────  │  gate -> LinUCB -> decision     │
 │                              │  recovery command  │  verifier -> reward -> update   │
 └──────────────────────────────┘                    │  SQLite state + audit           │
                                                     └─────────────────────────────────┘
```

One host owns one `ArcLayer`. There is no server, no network call and no API key.

## Use it

```python
from arclayer import ArcLayer

layer = ArcLayer("sqlite:////var/lib/myhost/arclayer.db", candidates="candidates.yaml")
policy_id = layer.create_policy("P", seed=1)

# when your framework detects a fault:
outcome = layer.handle_fault(native_fault, MyAdapter(), policy_id)
```

`MyAdapter` maps a native fault to a `FaultEventIn` and provides one executor per recovery candidate. A complete example that runs as written is in [docs/integration/quickstart.md](docs/integration/quickstart.md). Async frameworks use `await layer.handle_fault_async(...)`.

Keep latency measured on the host, report `actions_performed` truthfully, and report `terminal="new_incident"` when recovery raises a new fault.

## Example: LangGraph

A complete LangGraph host with ArcLayer plugged in. It runs as written (it needs `langgraph`, which is not a dependency of ArcLayer). The graph, its nodes and its edges are your host; ArcLayer enters at one place: a node is wrapped so that a failure inside it goes to ArcLayer, which picks a recovery, the host runs it, and the graph carries on.

```python
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
```

The search node fails; ArcLayer chooses `use_backup`; the executor runs it; the graph reaches `answer` as if nothing had happened. With a second candidate such as `retry` and a loop of questions, the policy learns which recovery works for this fault: the full version, with its output, is in [docs/integration/langgraph.md](docs/integration/langgraph.md). Async graphs use `await layer.handle_fault_async(...)` in an async node.

## Repository

```
arclayer/
├── README.md                        # overview, usage, repository map, known limitations
├── .gitignore                       # kept out of git: virtualenv, caches, SQLite files, editor and OS files
├── docs/                            # documentation, every folder has a README.md
│   ├── README.md                    # documentation index
│   ├── architecture/                # the code as it is today
│   │   ├── layout.md                # repository map and where the 11 components of Table 4 live
│   │   ├── dependency-rules.md      # which package may import which (enforced by test_architecture.py)
│   │   ├── incident-flow.md         # one fault from the host to a policy update
│   │   ├── persistence.md           # what the database holds and why
│   │   └── extending.md             # where new code goes
│   ├── integration/                 # connecting a host
│   │   ├── quickstart.md            # a complete example that runs as written
│   │   ├── langgraph.md             # a LangGraph graph with a fault handler and two recovery candidates, runs as written
│   │   ├── host-adapter.md          # HostAdapter, RecoveryExecutor, handle_fault
│   │   ├── api-reference.md         # arguments, methods and exceptions of ArcLayer
│   │   └── contracts.md             # shape of the messages (FaultEventIn and so on)
│   ├── operations/
│   │   ├── configuration.md         # constructor arguments, policy defaults, bundled config files
│   │   └── running-and-testing.md   # environment setup and running the tests
│   ├── troubleshooting/
│   │   ├── environment.md           # virtualenv, import and file-location problems
│   │   └── runtime-errors.md        # exceptions, stuck incidents, unexpected behaviour
│   └── development/                 # design notes
│       ├── decisions/               # the reasoning behind the design
│       │   ├── overview.md  risks-and-gotchas.md  technical-decisions.md  open-questions.md
│       │   └── deviations-from-plan.md      # implementation vs plan vs proposal, and the library-only decision
│       ├── design/                  # the design as planned: architecture, contracts, components
│       │   └── system-architecture.md  data-contracts.md  components.md  api-design.md  original-repository-layout.md
│       ├── evaluation/              # the evaluation plan (its code lives in the sibling project evaluation)
│       │   └── test-hosts-and-fault-injectors.md  experiment-harness.md  statistical-analysis.md
│       ├── process/                 # phases, testing strategy, security and ethics
│       │   └── implementation-phases.md  testing-strategy.md  security-and-ethics.md
│       ├── research/
│       │   ├── failure-handling-alignment.md   # review of a practitioner article and the papers: gaps, recommendations
│       │   └── sources.md                      # sources used and how each was verified
│       └── archive/
│           └── implementation-plan.id.md       # the original plan in Indonesian
├── cookbook/                        # runnable recipes, one concept per file
│   ├── README.md                    # how to run, topic index, conventions
│   ├── 00_quickstart/               # one complete integration; ArcLayer learning which recovery works
│   │   └── README.md  01_hello_recovery.py  02_learning_which_recovery_works.py
│   ├── 01_candidates/               # defining candidates (code, YAML) and why the gate rejects one
│   │   └── README.md  01_define_candidates.py  candidates.yaml  02_candidates_from_yaml.py  03_why_a_candidate_was_rejected.py
│   ├── 02_host_integration/         # fault handler around a tool, executor failures, async host, two-step reporting
│   │   └── README.md  01_plain_python_agent.py  02_when_an_executor_fails.py  03_async_host.py  04_report_in_two_steps.py
│   ├── 03_policies/                 # choosing a policy, overlapping incidents, warm start and freeze
│   │   └── README.md  01_choose_a_policy.py  02_strict_sequential.py  03_warm_start_and_freeze.py
│   ├── 04_persistence/              # keeping what was learned, surviving a crash
│   │   └── README.md  01_persist_and_resume.py  02_crash_and_orphans.py
│   ├── 05_verification/             # how success is scored: ground truth, permissions, budget
│   │   └── README.md  01_ground_truth.py  02_permissions_and_budget.py
│   └── 06_frameworks/               # ArcLayer inside LangGraph, Agno, CrewAI, AutoGen, OpenAI Agents, Pydantic AI, smolagents
│       └── README.md  01_langgraph_basic.py  02_langgraph_learning.py  03_agno.py  04_crewai.py
│           05_autogen.py  06_openai_agents.py  07_pydantic_ai.py  08_smolagents.py
└── libs/
    └── arclayer/                    # the only library
        ├── pyproject.toml           # package metadata; dependencies: pydantic, SQLAlchemy, PyYAML, numpy; extras: embeddings, dev
        ├── pytest.ini               # pythonpath ".", tests folder, the "slow" marker
        ├── requirements.txt         # pinned versions for the development environment (includes structlog, which no code uses)
        ├── configs/                 # default inputs for experiments and examples; never loaded automatically
        │   ├── candidates/default.yaml     # the six initial recovery candidates (Table 6)
        │   ├── features/v1.yaml            # frozen feature spec
        │   ├── gate/default.yaml           # allowed permissions and n_max
        │   ├── reward/default.yaml         # reward weights (s, c, l, v)
        │   └── baselines/static_map.yaml   # static map fault class -> candidate (baseline B2)
        ├── arclayer/                # the package
        │   ├── __init__.py          # exports ArcLayer, the errors, HostAdapter, RecoveryExecutor, handle_fault
        │   ├── api.py               # the ArcLayer class a host imports
        │   ├── bootstrap.py         # composition root: chooses the store and embedder, builds the services
        │   ├── contracts/
        │   │   └── schemas.py       # all message models and enums (Pydantic); imports nothing else from arclayer
        │   ├── host/                # the surface a host uses
        │   │   ├── protocols.py     # HostAdapter, RecoveryExecutor, ControlPlaneClient
        │   │   └── runtime.py       # handle_fault, FaultOutcome, HostMisconfigured
        │   ├── domain/              # core rules, plain Python plus numpy
        │   │   ├── models.py        # value objects (FaultEvent, Candidate, RecoveryCommand, ...)
        │   │   ├── entities.py      # entities with a life cycle (Incident, PolicyInstance)
        │   │   ├── enums.py         # FaultClass, Action, RejectionCode, IncidentStatus, ...
        │   │   ├── errors.py        # DomainError, IllegalTransition, InvalidRewardWeights
        │   │   ├── features.py      # feature vector x_{t,h} (d = 20)
        │   │   ├── gate.py          # feasibility and safety gate (pure function)
        │   │   ├── preconditions.py # evaluates a candidate's preconditions against the event
        │   │   ├── verification.py  # computes S, C, L, V from an execution result
        │   │   ├── reward.py        # reward weights and the reward (Equation 6)
        │   │   ├── state_machine.py # legal incident status transitions
        │   │   ├── answer_matching.py   # GAIA-style answer matching (an approximation written from memory)
        │   │   └── policies/
        │   │       ├── base.py      # the Selector protocol
        │   │       ├── linucb.py    # disjoint LinUCB (Equations 1 to 5)
        │   │       ├── baselines.py # baselines B0 to B4
        │   │       └── factory.py   # builds a selector from a policy
        │   ├── usecases/            # one class per business action
        │   │   ├── incidents.py     # HandleIncident, ReportResult, CensorExpired, GetIncident
        │   │   ├── candidates.py    # register, list, enable or disable, ground truth
        │   │   ├── policies.py      # create, get, freeze, snapshot a policy
        │   │   ├── ports.py         # Protocols for storage, embeddings, clock, ids, locks
        │   │   ├── errors.py        # NotFound, Conflict, PolicyBusy, FeatureMismatch
        │   │   └── services/
        │   │       ├── redaction.py     # masks secrets before embedding or storing
        │   │       ├── verifiers.py     # verifier registry (benchmark_task_pass, task_completed)
        │   │       ├── serialization.py # domain objects to JSON, fingerprints, checksums
        │   │       └── rng.py           # per-policy RNG whose state is persisted
        │   ├── delivery/
        │   │   ├── inprocess.py     # the in-process client ArcLayer uses
        │   │   └── mappers.py       # translates contracts (Pydantic) to and from domain models
        │   ├── infrastructure/
        │   │   ├── config/loaders.py   # YAML readers (candidates, features, reward, gate, static map)
        │   │   ├── persistence/
        │   │   │   ├── codec.py        # domain dataclasses to and from JSON, exact round trip
        │   │   │   ├── memory.py       # in-memory store (nothing persists)
        │   │   │   └── sqlalchemy/     # SQLite: schema.py (tables and audit triggers), store.py (transactions), repositories.py
        │   │   └── runtime/system.py   # SystemClock, UuidGenerator, ThreadPolicyLocks
        │   └── apiclients/embedding/   # every call that leaves the process
        │       ├── hashing.py          # offline hashed embedding (no semantic meaning)
        │       └── sentence_transformer.py  # semantic embedding through a local model
        └── tests/
            ├── factories.py         # domain object factories for tests
            ├── support/             # test helpers, not production code
            │   ├── synthetic_host/  # test double: synthetic incident generator (adapter, candidates, world)
            │   └── synthetic_run.py # runs one policy on the synthetic world through ArcLayer
            ├── system/
            │   └── test_synthetic_learning.py  # LinUCB must beat B1, B2 and B3 (acceptance criterion 8.1)
            └── unit/                # mirrors the package layout
                ├── test_architecture.py   # enforces the import rules and the third-party confinement
                ├── test_bootstrap.py      # composition root
                ├── api/  contracts/  delivery/  host/  synthetic_host/
                ├── domain/          # gate, features, LinUCB, baselines, reward, state machine
                ├── usecases/        # use cases and services (conftest.py holds the harness fixtures)
                ├── infrastructure/  # config loaders, codec, SQLite store
                └── apiclients/embedding/  # the real sentence-transformers model (slow)
```

Empty `__init__.py` files are not listed. Files created at run time are not in the tree: the SQLite database (`arclayer.db` by default, wherever `db_url` and the working directory put it), `.venv/` and the pytest and Hypothesis caches.

Test hosts, the experiment harness and the statistical analysis are kept out of this repository, in the sibling project `evaluation`.

## Develop

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r libs/arclayer/requirements.txt

cd libs/arclayer
../../.venv/bin/python -m pytest        # add -m "not slow" to skip the long tests
```

To run a cookbook recipe, from the repository root:

```bash
PYTHONPATH=libs/arclayer .venv/bin/python cookbook/00_quickstart/01_hello_recovery.py
```

Call pytest and pip as `.venv/bin/python -m ...`; scripts inside a moved virtualenv keep the old absolute path in their shebang. More in [docs/operations](docs/operations/README.md).

## Documentation

| | |
|---|---|
| [cookbook](cookbook/README.md) | Runnable recipes, one concept per file: candidates, host integration, policies, persistence, verification, seven agent frameworks |
| [docs/integration](docs/integration/README.md) | Quickstart, adapter and executors, `ArcLayer` reference, contracts |
| [docs/architecture](docs/architecture/README.md) | Layers, dependency rules, one incident end to end, persistence |
| [docs/operations](docs/operations/README.md) | Configuration, setup, tests |
| [docs/troubleshooting](docs/troubleshooting/README.md) | Symptoms, causes, fixes |
| [docs/development](docs/development/README.md) | Design rationale, plan, evaluation plan, literature review |

## Known limitations

- `arclayer/domain/answer_matching.py` approximates the official GAIA answer scorer and was written from memory. Compare it with the official scorer before any main experiment, because it decides the success signal `S`.
- The default embedding (`hashing`) has no semantic meaning, so the cosine feature and baseline B4 are only meaningful with `embedding="st:<model>"`.
- One process per database file: policy locks live in process memory. Storage is tested with SQLite only.
- The framework-agnostic claim covers Python agent frameworks. Non-Python hosts, and learning shared across several processes, would need a separate service layer, which this library does not provide.
- Installing the package with `pip install` has not been tested; development uses the `pythonpath` entry in `libs/arclayer/pytest.ini`.
- A review of failure handling against production practice found gaps and recommended changes that are not implemented yet: [docs/development/research](docs/development/research/failure-handling-alignment.md).
