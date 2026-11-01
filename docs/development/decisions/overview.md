# Overview

> Status note: translated from the original implementation plan (October 2026). The code may have diverged from this plan; see docs/architecture for the current structure.

| Item | Decision |
|---|---|
| System form | One **control plane** service (FastAPI) + an **Adapter SDK** (Python library) installed on the multi-agent host side |
| Integration principle | The host keeps executing; the control plane only receives the fault context, selects a candidate, receives the result, verifies it, and updates the policy |
| Algorithm | Disjoint LinUCB (Equations 1-5), reward from Equation 6, `d = 20` features |
| Baselines | B0-B4, P, P-D, P-F (Table 7) implemented as a `Selector` with the same interface |
| Test hosts | (1) A synthetic host for sanity checks, (2) a reference host built on an open framework with checkpoints, (3) a second host to support the framework-agnostic claim |
| Discipline | TDD is mandatory: every task below starts with a failing test |

Mapping of the proposal's Chapter III to code modules:

| Part of the proposal | Module |
|---|---|
| Table 4 (minimum adapter information) | `arclayer/contracts/events.py` |
| Table 5 (components) | `arclayer/core/*` |
| Equations 1-5 | `arclayer/policy/linucb.py` |
| Equation 6 | `arclayer/core/reward.py` |
| Algorithm 1 | `arclayer/core/orchestrator.py` |
| Figure 2 | `arclayer/api/routes/incidents.py` + `arclayer_sdk/client.py` |
| Table 6 | `configs/candidates/*.yaml` |
| Table 7 | `arclayer/policy/baselines.py` + `arclayer/policy/linucb.py` |
| Table 8, III.3.4 | `experiments/` + `analysis/` |
