# ArcLayer cookbook

Runnable recipes, one concept per file. Every file stands alone, prints what it demonstrates, and needs no network, no API key and no LLM. The host systems in these examples are simulated; only `06_frameworks` uses a real agent framework.

## Run an example

From the repository root:

```bash
PYTHONPATH=libs/arclayer .venv/bin/python cookbook/00_quickstart/01_hello_recovery.py
```

`PYTHONPATH` tells Python where the `arclayer` package is; installing it with `pip` has not been tested yet. Environment setup is in [docs/operations](../docs/operations/running-and-testing.md).

## Topics

| Folder | You learn | Read it when |
|---|---|---|
| [00_quickstart](00_quickstart/README.md) | One complete integration, and ArcLayer learning which recovery works | You are starting |
| [01_candidates](01_candidates/README.md) | Defining recovery candidates in code or YAML, and why the gate rejects one | A recovery never runs |
| [02_host_integration](02_host_integration/README.md) | A fault handler around a tool, executor failures, async hosts, reporting in two steps | You are wiring ArcLayer into a host |
| [03_policies](03_policies/README.md) | Choosing a policy, overlapping incidents, warm start and freeze | You are deciding how ArcLayer picks |
| [04_persistence](04_persistence/README.md) | Keeping what was learned, and surviving a crash | You run ArcLayer for more than one process lifetime |
| [05_verification](05_verification/README.md) | How success is scored: ground truth, permissions, budget | You need to trust or tune the reward |
| [06_frameworks](06_frameworks/README.md) | ArcLayer inside LangGraph, Agno, CrewAI, AutoGen, OpenAI Agents SDK, Pydantic AI and smolagents | You use one of those frameworks |

A good reading order is the folder order. Folders `00` and `02` are enough to integrate a host.

## Conventions

- State lives in memory unless the file says otherwise. Examples that use a SQLite file create it in a temporary folder and delete it.
- Everything is seeded, so the output is the same on every run.
- Every example is run by `libs/arclayer/tests/system/test_cookbook.py`, so a recipe that stops working fails the test suite. Examples that need an agent framework are skipped when it is not installed.
- Each file starts with a docstring that says what it shows and how to run it.
