# Test Hosts and Fault Injectors

> Status note: translated from the original implementation plan (October 2026). The code may have diverged from this plan; see docs/architecture for the current structure. The code described here now lives in the sibling project projects/evaluation.

## 8.1 Synthetic host (mandatory, built first)

Purpose: prove the end-to-end pipeline and show that LinUCB learns, **before** spending any LLM budget. It is not evidence for the thesis.

- Generates incidents with `fault_class`, `orchestration`, checkpoint, and a seeded random budget.
- Success probability of each candidate: `p(h | f) = sigmoid(θ*_h · x)`, with a hidden `θ*_h` constructed so that a static mapping is not optimal (e.g. `h3` is better than `h6` for `plan_error` only in the `sequential` pattern).
- Cost and latency are drawn from a per-candidate distribution.

Acceptance test: over 2,000 incidents, mean cumulative reward satisfies P > B2 > B3, and the regret of P is empirically sublinear (the curve flattens). If this fails, there is a bug that must be fixed before moving to the real host.

## 8.2 Reference host (GAIA Level 1 / GAIA-Free)

Requirements: (a) four orchestration patterns, (b) a checkpoint at every step and the ability to reload it, (c) free tools only (consistent with GAIA-Free), (d) hook points for fault detection and injection.

Framework candidates (pick one, Q2):
- **LangGraph**: a per-step checkpointer is already available in the framework (recalling, not verified; check the documentation of the pinned version). Makes the `h6` rollback easier.
- **Microsoft Agent Framework**: used to build StateMAS according to the MARS paper (as stated in the proposal), so it is the closest to the MARS protocol if StateMAS is not released.
- **AG2/AutoGen**: used by DoVer for MathChat; DoVer reports needing a checkpoint wrapper of about one thousand lines (as stated in the proposal), so it is more expensive to build.

Recommendation: reference host = a framework with native checkpoints (LangGraph or Microsoft Agent Framework candidate), second host = another framework with a different orchestration pattern, to support the portability claim in Problem Limitation 6.

Per-host implementation:
1. `NativeFaultDetector`: timeouts, tool exceptions, injector output.
2. `HostAdapter.to_fault_event`: mapping from native state to `FaultEvent`.
3. Six `RecoveryExecutor`s (h1..h6). The prompts for h3 (re-planner), h4 (handoff completer), h5 (verification reviewer), and h6 (rollback guide) are frozen as versioned templates.
4. A runner that executes one GAIA task and stops at the first incident or when the task finishes.

## 8.3 Fault injectors

Each injector: a pure function `inject(step, state, rng) -> InjectedState` plus a label (`fault_class`, `step_index`). Injectors are run from the checkpoint before the injection point, on an execution that succeeded (proposal III.3.3, second path).

| Class | Injection mechanism |
|---|---|
| tool_failure | The tool returns a structured error or its arguments are corrupted |
| timeout | The tool does not respond until the time limit |
| tool_output_unused | The tool output is removed from the next agent's context |
| handoff_incomplete | The handoff message is truncated or an important field is removed |
| plan_error | One step of the orchestrator's plan is replaced by a wrong step |
| insufficient_verification | The verification step is skipped and the answer is submitted directly |

Rule "inactive injections are not counted" (III.3.3): an injector writes `activated=true` only if the execution path actually passes through the modified point. Incidents with `activated=false` are discarded before the policy runs.

## 8.4 StateMAS adapter (conditional)

Built only if the artifact is available and verified to be runnable. Tasks: map the StateMAS snapshot to `FaultEvent`, map `checkpoint_id` to a snapshot, and map the executors to the StateMAS replay API.
