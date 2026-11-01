# Experiment Harness

> Status note: translated from the original implementation plan (October 2026). The code may have diverged from this plan; see docs/architecture for the current structure. The code described here now lives in the sibling project projects/evaluation.

## 9.1 Configuration

```yaml
experiment_id: gaia_l1_main_v1
host: reference_host
benchmark: gaia_level1          # or statemas_gaia_free
feature_version: v1
reward: default
n_max: 1
budget:
  per_incident_cost: 1.0
  per_task_cost: 3.0
  per_incident_timeout_ms: 300000
model:
  backbone: <locked in Phase 5>
  temperature: 0
  max_tokens: <locked>
conditions: [B0, B1, B2, B3, B4, P, P_D, P_F]
seeds: [11, 23, 37, 41, 59]
split: { calibration: 0.2, evaluation: 0.8, by: task_id, seed: 7 }
alpha_grid: [0.1, 0.25, 0.5, 1.0]
lambda: 0.45
mode: outcome_matrix            # or online
```

The configuration is hashed and the hash is stored in every record. The configuration used for evaluation is committed before the evaluation data is opened (local pre-registration).

## 9.2 Split

`split.py`: split the unique `task_id`s with a fixed seed, 20/80. All incidents from one `task_id` (across patterns and models) fall into one part. Test: no `task_id` appears in both parts (T-EXP-01).

## 9.3 Calibration

On the calibration data:
1. Freeze the normalization (`step_cap`, `budget_task_cap`).
2. For each `α` in the grid, run P on all seeds; choose the `α` with the highest mean cumulative reward. Tie: choose the smallest `α`.
3. The snapshot of P after calibration = the initialization of P-F.
4. Pilot study: estimate the proportion of discordant pairs for P vs B2 for the power analysis (Section 10.2).

Design question: does P on the evaluation data start from zero or from the calibration snapshot? The proposal is not explicit. If P starts from zero while P-F starts from the snapshot, the P vs P-F comparison is not equivalent. Recommendation: P and P-D each start from their own calibration snapshot and then keep learning; P-F starts from the same snapshot and is frozen. This way P vs P-F purely tests online learning (Q5).

## 9.4 Outcome matrix mode

1. For every evaluation incident, run the host from the checkpoint for **each** candidate that passes the gate, once. Store the `ExecutionResult` and `VerificationResult`.
2. Measure determinism: a 10% subset of incidents is re-run 3 times per candidate; report the proportion of `S` values that change. If it exceeds a threshold set in advance (e.g. 5%), store all three results and draw one at random (seeded) during simulation, or switch to online mode.
3. Simulate each condition x seed: a sequential incident stream with the same seeded random order for all conditions; the selector chooses; the outcome is taken from the matrix; updates run as usual through `InProcessClient`.
4. Validation: a small subset is run fully online; compare it with the simulation.

Advantage: the LLM cost is about `|H_t|` executions per incident, not `8 x seeds`. Limitation: only valid for `N_max = 1` (Gotcha 1.5). This must be recorded in the threats-to-validity chapter.

## 9.5 Online mode

For `N_max > 1` or for validation. Each condition x seed runs the real host for every incident. The harness processes one incident at a time per policy instance; parallelism is only across instances.
