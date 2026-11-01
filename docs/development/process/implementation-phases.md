# Implementation Phases

> Status note: translated from the original implementation plan (October 2026). The code may have diverged from this plan; see docs/architecture for the current structure.

Every task follows: **Red** (write a failing test, run it, confirm it fails for the right reason) -> **Green** (minimal implementation) -> **Refactor**. The "First test" column is the test written before the code.

Week estimates are rough and assume one part-time person; adjust them to the semester schedule.

## Phase 0: Foundation (week 1)

| ID | Task | First test | DoD |
|---|---|---|---|
| F0-01 | Scaffold repo, `uv`, ruff, mypy strict, pytest, pre-commit | `test_smoke_import` | Local CI green |
| F0-02 | `create_app` + `/healthz` | `test_healthz_returns_ok` | |
| F0-03 | Settings (`ARCLAYER_MODE`, DB URL, API key) | `test_oracle_router_absent_in_service_mode` | |
| F0-04 | DB + initial Alembic migration | `test_migration_up_down` | |
| F0-05 | Architecture test: `arclayer_sdk` does not import `arclayer.core` | `T-ARCH-01` | |

## Phase 1: Contracts (week 2)

| ID | Task | First test |
|---|---|---|
| F1-01 | Enums + `FaultEvent` | `test_fault_event_rejects_extra_fields`, `test_confidence_bounds` |
| F1-02 | `CandidateSpec` + Table 6 YAML loader | `test_default_registry_has_six_candidates`, `test_unknown_precondition_rejected` |
| F1-03 | `RecoveryCommand`, `ExecutionResult`, `VerificationResult`, `OutcomeAck` | `test_execute_requires_candidate_id`, `test_C_L_clipped_range` |
| F1-04 | JSON Schema export | `test_schema_export_stable` (snapshot test) |

## Phase 2: Control plane core (weeks 3-5)

| ID | Task | First test |
|---|---|---|
| F2-01 | Redaction | `test_redacts_bearer_token`, `test_redaction_idempotent` |
| F2-02 | Normalizer | `test_truncation_deterministic` |
| F2-03 | Features `f_t` | `test_f_dim_15`, `test_unknown_class_all_zero_onehot`, `test_features_in_unit_interval` (hypothesis) |
| F2-04 | Embedding wrapper + cache | `test_same_text_same_vector`, `test_model_version_recorded` (use a fake model in unit tests) |
| F2-05 | Features `g(t,h)` + P-D variant | `test_g_dim_4`, `test_wildcard_class_match_is_one`, `test_pd_drops_expected_indices` |
| F2-06 | Feature version hash | `test_policy_rejects_mismatched_feature_hash` |
| F2-07 | Gate (6 rules) | One test per rejection code + `test_gate_is_pure` + `test_empty_due_to_limit_escalates` |
| F2-08 | Verifier `step_check`, `benchmark_task_pass` | `test_new_incident_terminal_gives_S0`, `test_permission_violation_sets_V1` |
| F2-09 | Reward + weight validator | `test_reward_eq6`, `test_success_always_positive_under_default_weights`, `test_violation_never_positive` (hypothesis) |
| F2-10 | State machine | `T-CORE-09` transition table |
| F2-11 | Append-only audit logger | `test_audit_no_update_or_delete` |

## Phase 3: Policy (weeks 5-6)

| ID | Task | First test |
|---|---|---|
| F3-01 | `DisjointLinUCB` init | `test_init_A_lambda_I_b_zero` |
| F3-02 | Score from Equations 1-2 | `test_score_matches_closed_form` (compare against an explicit `inv` on small cases) |
| F3-03 | Update from Equations 4-5 | `test_only_chosen_arm_updated`, `test_bonus_shrinks_after_repeated_same_x` |
| F3-04 | Seeded tie-break | `test_tie_break_not_always_first`, `test_same_seed_same_choice` |
| F3-05 | Freeze (P-F) | `test_frozen_policy_ignores_update` |
| F3-06 | Persistence of A, b | `test_roundtrip_float64_exact` |
| F3-07 | Baselines B0-B4 | One behavior test per baseline; `test_b4_uses_same_embedding_model_as_p` |
| F3-08 | Factory from `kind` | `test_factory_all_conditions_table7` |
| F3-09 | LinUCB property test | On a synthetic linear bandit, cumulative regret of P < B3 after N steps (hypothesis, fixed seed) |

## Phase 4: API, orchestrator, SDK, synthetic host (weeks 6-8)

| ID | Task | First test |
|---|---|---|
| F4-01 | In-process `Orchestrator` (Algorithm 1) | `test_algorithm1_happy_path`, `test_empty_Ht_safe_stop` |
| F4-02 | `/incidents` and `/result` routes | `test_post_incident_returns_command`, `test_duplicate_result_same_key_idempotent`, `test_duplicate_result_different_payload_409` |
| F4-03 | Strict sequential lock | `test_second_incident_423_while_pending` |
| F4-04 | Censoring TTL | `test_censored_incident_no_update` |
| F4-05 | Candidates/policies/oracle routes | `test_oracle_not_leaked_into_command` (**T-SEC-02**: search for ground-truth strings across the entire `RecoveryCommand` and `FaultContext`) |
| F4-06 | SDK `HttpClient` + `InProcessClient` | The same contract test is run on both transports |
| F4-07 | Synthetic host | `test_synthetic_host_deterministic_under_seed` |
| F4-08 | Synthetic E2E | `test_linucb_beats_static_on_synthetic` (acceptance criterion 8.1) |

**Milestone M1 (end of week 8):** the end-to-end pipeline runs on the synthetic host, all Table 7 conditions can be run, and the audit can be regenerated.

## Phase 5: Reference host and injectors (weeks 9-12)

| ID | Task | First test |
|---|---|---|
| F5-01 | Framework decision (Q2) + checkpoint spike | Spike: save and load a checkpoint on a toy task, identical state |
| F5-02 | Host with 4 orchestration patterns | `test_each_pattern_completes_toy_task` |
| F5-03 | Free tools + GAIA Level 1 loader | `test_gaia_answer_normalization` |
| F5-04 | `to_fault_event` adapter | Contract test: events from the host pass schema validation |
| F5-05 | Executors h1..h6 + versioned prompt templates | Per executor: test with a fake LLM (stub) for flow and permissions |
| F5-06 | 6 injectors + `activated` flag | `test_inactive_injection_flagged` per injector |
| F5-07 | E-01: measure temperature-zero determinism | Variance report (not a unit test) |
| F5-08 | Second host (different framework) | The same SDK contract test passes |

**Milestone M2 (end of week 12):** two real hosts are integrated through the same SDK without changes to the control plane. This is the main evidence for the framework-agnostic claim.

## Phase 6: Experiment harness (weeks 12-14)

| ID | Task | First test |
|---|---|---|
| F6-01 | Split by task_id | **T-EXP-01** no task_id leakage |
| F6-02 | Same seeded stream order for all conditions | `test_same_order_across_conditions` |
| F6-03 | Alpha calibration + snapshot | `test_alpha_selected_only_from_calibration_data` |
| F6-04 | Outcome matrix builder | `test_matrix_has_entry_per_eligible_candidate` |
| F6-05 | Offline simulator | `test_offline_equals_online_on_synthetic_host` |
| F6-06 | Pilot + power analysis | `test_power_formula_against_known_values` |

## Phase 7: Experiment execution and analysis (weeks 14-16+)

| ID | Task |
|---|---|
| F7-01 | Freeze all configurations, commit, record the hash |
| F7-02 | Run calibration |
| F7-03 | Build the evaluation outcome matrix |
| F7-04 | Simulate all conditions x seeds |
| F7-05 | Validate on an online subset |
| F7-06 | Statistics + report; weight sensitivity analysis (16 combinations) and LLM verifier |
| F7-07 | Replication artifact package (code, benchmark version, incident list, seeds, model configuration, injection schedule, candidate metadata, weights, LinUCB parameters, redacted audit, analysis scripts) |
