# Integration

How to connect a host system (LangGraph, AutoGen, Agno, a custom orchestrator, any Python agent framework) to ArcLayer. The host imports the library and calls it directly; there is no server, no network call and no API key. The integration surface is small: two Protocols to implement and one method to call.

| Document | Read it when |
|---|---|
| [quickstart.md](quickstart.md) | You want a complete working example first |
| [langgraph.md](langgraph.md) | You want to see where ArcLayer plugs into a LangGraph graph |
| [host-adapter.md](host-adapter.md) | You are writing the adapter and executors for a host |
| [api-reference.md](api-reference.md) | You need the arguments, methods and errors of `ArcLayer` |
| [contracts.md](contracts.md) | You need the exact shape of the messages |

For runnable recipes covering candidates, policies, persistence and verification, see the [cookbook](../../cookbook/README.md).

## The integration in five steps

1. Install `arclayer` in the host's environment.
2. Implement `HostAdapter.to_fault_event`, which maps a native fault to a `FaultEventIn`, and one `RecoveryExecutor` per recovery candidate the host supports.
3. Create one `ArcLayer`, register your candidates, and create a policy.
4. When the host detects a fault, call `layer.handle_fault(native_fault, adapter, policy_id)`.
5. Keep the host honest: measure latency on the host, report `actions_performed` truthfully, and report `terminal="new_incident"` when recovery itself raises a new fault.

## What stays on the host

ArcLayer decides, the host acts. Detecting faults, classifying them, executing recovery, checkpointing and rolling back state all belong to the host. ArcLayer sees only the fault context and the result the host chooses to send, and it imports no agent framework.

## One host, one ArcLayer

Create a single `ArcLayer` per host process and give it its own database file. Several threads, or several async tasks through `handle_fault_async`, can share it. Do not point two processes at one database file: policy locks live in process memory.
