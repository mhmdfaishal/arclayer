# Risks and Gotchas

> Status note: translated from the original implementation plan (October 2026). The code may have diverged from this plan; see docs/architecture for the current structure.

This section was deliberately placed first in the plan because several points change the design, not just implementation details.

## 1.1 Constant features caused by the eligibility gate (affects Equation 2 and H2)

The vector `g(t,h)` in the proposal contains (a) a fault-class match indicator and (b) a state-precondition match indicator. The eligibility gate also filters on preconditions. As a result:

- The **precondition indicator** is always 1 for every candidate that passes the gate. This feature is constant, collinear with the bias, and carries no information.
- The **class indicator** will end up the same way if the gate also filters on supported classes.

Recommendation:
1. The gate filters only on **hard** constraints: permissions (allowlist), required state preconditions, maximum cost against the remaining budget, and active-candidate status.
2. **Supported classes** are treated as a **soft feature** (`class_match`), not a filter. This is also consistent with B2, which uses the class column as a mapping, so the difference between P and B2 really tests learning.
3. Replace the binary precondition indicator with an **optional-precondition completeness score** (the ratio of optional preconditions that are met, for example when evidence artifacts are only partly available), or drop the feature and adjust `d`.

This must be decided before the feature code is frozen (see Open Question Q1).

## 1.2 One-hot + bias = collinear

The one-hot encoding of the fault class and the one-hot encoding of the orchestration pattern each sum to 1, which equals the bias term. With ridge regularization (`A = λI`) a solution still exists, so this is not fatal, but the interpretation of `θ` per feature becomes ambiguous. For audit and interpretability, also keep a version that omits one reference category as an analysis option. The main path does not need to change.

## 1.3 Definition of `S_t` per incident vs post-repair pass rate per task

The primary metric is computed per task, while the reward is computed per incident. An explicit rule is needed:

- After candidate `h_t` is executed, the host **continues the task** until (a) the task completes, (b) a new incident appears, or (c) the budget or time limit runs out.
- `S_t = 1` only if (a) occurs and the verifier/benchmark declares a pass.
- If (b) occurs, `S_t = 0` for incident `t`, and incident `t+1` is a new round (following step 16 of Algorithm 1).
- If `N_max = 1`, this chain does not occur and the definition becomes simple.

Consequence: the reward is not truly "immediate" on long tasks; it is delayed until the rollout finishes. This is still valid as a bandit because there is no value propagation to other decisions, but it must be stated explicitly in Chapter IV.

## 1.4 Ground-truth leakage to candidates

The DoVer paper gives the reference answer to the hypothesis proposer. Here the verifier needs GAIA ground truth, but the candidates (the re-planner, the verification reviewer) **must not** see it. Design: ground truth enters only through a `VerifierOracle` that the experiment harness registers with the control plane. It never appears in `FaultEvent`, `FaultContext`, or `RecoveryCommand`. A dedicated test covers this (T-SEC-02).

## 1.5 Cost of paired experiments

8 conditions x N incidents x S seeds, each needing a host replay from a checkpoint plus a rollout to completion. With GAIA rollouts, this is expensive. Cost-saving option (Section 9.4): an **outcome matrix**. Run each gate-passing candidate once per incident, cache the result, then simulate all policies and seeds offline. Validity requirements:

- The execution result of a candidate does not depend on the policy history. This holds for `N_max = 1`. For `N_max > 1`, the "number of prior incidents" feature and the follow-up incidents depend on earlier choices, so the outcome matrix is valid only for the first incident per task.
- Determinism at temperature zero is **not guaranteed** on commercial LLM APIs. Measure the variance first (Phase 5, task E-01) before relying on the cache.

Recommendation: the outcome matrix as the main path with `N_max = 1`, plus a small subset of full online execution to validate that offline and online results agree.

## 1.6 StateMAS availability

Per the proposal, the StateMAS artifacts have not been found. This plan does **not** depend on StateMAS: the reference host is built in-house (Phase 4), and a StateMAS adapter is only built if the artifacts appear.

## 1.7 Concurrency of policy updates

LinUCB is sequential: decision `t+1` must see the update from `t`. If several hosts send incidents in parallel to the same policy, the update order becomes nondeterministic and the experiment cannot be reproduced. Design:

- Policy state is locked per `policy_instance_id` (asyncio lock + DB transaction).
- For experiments, each `(condition, seed)` has its own `policy_instance_id`, and its incident stream is processed sequentially by the harness.
- Results sent twice (network retry) are rejected via `Idempotency-Key`.

## 1.8 Results that never return

If the host crashes and never sends a result, the incident is marked `censored` after the TTL. **No update** is made to `A_h, b_h` for censored incidents (updating with reward 0 would introduce bias). They are reported separately.

## 1.9 Tie-breaking

At the start, several candidates can have equal scores. NumPy `argmax` always picks the first index, so the registry order becomes a hidden bias. Use a seeded random tie-break per `policy_instance_id`.
