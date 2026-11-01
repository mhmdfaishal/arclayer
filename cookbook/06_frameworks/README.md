# Frameworks

ArcLayer imports no agent framework. These examples show where it plugs into each one. Each framework is an optional install that is not a dependency of ArcLayer, and every example is skipped by the test suite when its framework is missing.

The scenario is the same in all of them: the primary `search` tool fails with a 503, ArcLayer picks `use_backup`, the host runs the backup, and the run carries on as if the tool had succeeded. Only the place where ArcLayer enters differs, so comparing two files shows what is framework-specific.

## Examples

| File | Framework (tested with) | ArcLayer enters at | You should see |
|---|---|---|---|
| [01_langgraph_basic.py](01_langgraph_basic.py) | `langgraph` 1.2.15 | The node function: wrap it before `add_node` | `cached result for q1 -> done` |
| [02_langgraph_learning.py](02_langgraph_learning.py) | `langgraph` 1.2.15 | The same node, with two candidates and ten questions: the policy learns that `retry` does not help | `q0: not recovered`, then nine recoveries through `use_backup`, and `{'retry': 1, 'use_backup': 9}` |
| [03_agno.py](03_agno.py) | `agno` 3.1.3 and 3.1.12 | The tool hook: `Function(..., tool_hooks=[...])` | `cached result for q1 -> done` |
| [04_crewai.py](04_crewai.py) | `crewai` 1.15.33 | The tool's `func`: `tool.model_copy(update={"func": ...})` | `cached result for q1 -> done` |
| [05_autogen.py](05_autogen.py) | `autogen-agentchat` and `autogen-ext` 0.7.5 | The async function given to `FunctionTool` | `cached result for q1` |
| [06_openai_agents.py](06_openai_agents.py) | `openai-agents` 0.24.0 | The async function given to `function_tool` | `cached result for q1 -> done` |
| [07_pydantic_ai.py](07_pydantic_ai.py) | `pydantic-ai-slim` 2.64.0 | The async function given to `Agent(tools=[...])` | `cached result for q1 -> done` |
| [08_smolagents.py](08_smolagents.py) | `smolagents` 1.26.0 | The function given to `tool(...)` | `cached result for q1 -> done` |

In every file the host code has nothing ArcLayer-specific. The only change to your framework wiring is that the failing tool or node is registered wrapped.

## How the examples run offline

No example calls an LLM or needs an API key. Where the framework runs an agent loop, a small scripted model stands in for the LLM: it asks for the `search` tool once and then answers from the tool result. The agent loop, tool dispatch and your wrapper are the framework's real code; only the model's decision to call `search` is fixed. LangGraph has no model, so it runs a plain graph.

Telemetry is switched off in the files that need it (Agno, CrewAI, OpenAI Agents tracing). The Pydantic AI example only hides its first-run banner, which prints to stderr and makes no network call. Each example was also run with outbound network connections blocked and made none.

## When the recovery fails

If no recovery works, the wrapper re-raises the original error. What the framework does next is not ArcLayer's choice, and it differs. These results come from running each example with a backup that also fails:

| Framework | What happens |
|---|---|
| Agno | The error text goes to the model and the run finishes. |
| CrewAI | The error goes to the agent as a tool message and the run finishes. |
| AutoGen | The error goes back to the model as an error result and the run finishes. |
| OpenAI Agents | The model gets only the SDK's generic "An error occurred while running the tool", and the run finishes. |
| Pydantic AI | The exception leaves `run_sync` and the run stops. |
| smolagents | The agent retries until its step limit and returns an empty result. |

Decide this on purpose. If a failed recovery must stop the run, catch the exception outside the framework call or raise the framework's own stop signal.

## Gotchas

- **Install each framework in its own virtual environment.** CrewAI 1.15.33 requires `pydantic>=2.11.9,<2.13`, while ArcLayer's `pyproject.toml` asks for `pydantic>=2.14,<3`, so `pip` cannot install both together. The CrewAI example does run on pydantic 2.12.5 with ArcLayer on `PYTHONPATH`, but that is not an installable combination. The other five frameworks resolved alongside ArcLayer's pins.
- **Async frameworks need `handle_fault_async`.** AutoGen, OpenAI Agents and Pydantic AI call tools on an event loop, and the sync `handle_fault` would block it while the recovery runs. Agno, CrewAI and smolagents tools are synchronous in these examples, so they use `handle_fault`.
- **Wrapped tools keep their schema through `functools.wraps`.** AutoGen, OpenAI Agents, Pydantic AI and smolagents read the signature or docstring of the function to build the tool schema, and `functools.wraps` is what keeps it. A tool that takes the framework's context argument needs a wrapper with the same signature.
- **CrewAI writes under the home folder.** It stores settings and a key in `~/.config/crewai` and `~/Library/Application Support/crewai`, and `CREWAI_STORAGE_DIR` does not move them. The example points `HOME` at a temporary folder for the process and removes it at exit.
- **Agno telemetry is read from the environment at run time.** The example sets `AGNO_TELEMETRY=false` before importing Agno, because `Agent(telemetry=False)` is overridden by that variable.
- **OpenAI Agents tracing.** `set_tracing_disabled(True)` is in the example. With no `OPENAI_API_KEY` set, the SDK skips trace export anyway, so the switch only changes behaviour for someone who has a key set; that case was not tested.

## Not covered

Streaming, handoffs, multi-agent teams and native function-calling models are not exercised. Google ADK, Strands and LlamaIndex have no example yet.

## Run one

From the repository root, with the framework installed in the Python you use:

```bash
PYTHONPATH=libs/arclayer python cookbook/06_frameworks/03_agno.py
```
