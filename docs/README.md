# ArcLayer documentation

ArcLayer is a framework-agnostic recovery control layer for LLM multi-agent (agentic) systems, shipped as a Python library. A host system, built with any Python agent framework, imports it and reports a detected fault; ArcLayer filters the registered recovery candidates with a safety gate, selects one with a LinUCB contextual bandit, receives the verified outcome, and updates its policy. One host owns one `ArcLayer`.

| Folder | Read it for |
|---|---|
| [architecture/](architecture/README.md) | The code: layers, dependency rules, one incident end to end, persistence, where new code goes |
| [integration/](integration/README.md) | Connecting a host: quickstart, adapter and executors, the `ArcLayer` reference, message contracts |
| [operations/](operations/README.md) | Configuration choices, setting up an environment, running the tests |
| [troubleshooting/](troubleshooting/README.md) | Symptoms, causes and fixes for environment and runtime problems |
| [../cookbook/](../cookbook/README.md) | Runnable recipes, one concept per file |
| [development/](development/README.md) | Design rationale, original plan, evaluation plan, and the literature review |

## Where to start

- Integrating a host: [integration/quickstart.md](integration/quickstart.md), or [integration/langgraph.md](integration/langgraph.md) for a LangGraph graph.
- New to the code: [architecture/layout.md](architecture/layout.md), then [architecture/incident-flow.md](architecture/incident-flow.md).
- Running the tests: [operations/running-and-testing.md](operations/running-and-testing.md).
