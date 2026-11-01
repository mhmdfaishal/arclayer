# Original Repository Layout

> This is the repository layout proposed in the original plan. It was never built as written: the real layout is libs/arclayer, libs/arclayer_contracts and libs/arclayer_sdk, described in docs/architecture/layout.md.

> Status note: translated from the original implementation plan (October 2026). The code may have diverged from this plan; see docs/architecture for the current structure.

```
recovery-control-layer/
  pyproject.toml
  uv.lock
  README.md
  configs/
    candidates/default.yaml        # Table 6
    gate/default.yaml              # permission and limit rules
    features/v1.yaml               # feature definitions and normalization (frozen)
    reward/default.yaml            # w_s=1, w_c=0.2, w_l=0.1, w_v=1
    experiments/*.yaml
  src/
    arclayer/                           # control plane
      api/
        app.py                     # FastAPI factory, lifespan
        deps.py                    # DI: db session, registry, selector factory
        routes/
          incidents.py
          candidates.py
          policies.py
          oracle.py                # active only when ARCLAYER_MODE=experiment
          health.py
        errors.py
        security.py                # API key per host
      contracts/                   # Pydantic: single source of truth for contracts
        events.py                  # FaultEvent (Table 4)
        context.py                 # FaultContext, FeatureVector
        candidates.py              # CandidateSpec
        commands.py                # RecoveryCommand, ScoreBreakdown
        results.py                 # ExecutionResult, VerificationResult, OutcomeAck
        enums.py                   # FaultClass, OrchestrationPattern, Action
      core/
        normalizer.py
        redaction.py
        context_builder.py
        features.py                # f_t and g(t,h)
        embeddings.py              # frozen model wrapper + cache
        registry.py
        gate.py
        verifier.py
        reward.py
        orchestrator.py            # Algorithm 1
        state_machine.py
      policy/
        base.py                    # Selector Protocol
        linucb.py                  # P, P-D, P-F
        baselines.py               # B0..B4
        factory.py
      store/
        models.py                  # SQLAlchemy ORM
        repo.py
        migrations/
      audit/
        logger.py
    arclayer_sdk/                       # installed on the host side
      client.py                    # async + sync HTTP client
      adapter.py                   # Protocol HostAdapter, RecoveryExecutor
      runtime.py                   # loop: emit -> execute -> report
      inprocess.py                 # no-HTTP mode for unit tests and the outcome matrix
    hosts/                         # test hosts
      synthetic/                   # synthetic host for sanity checks
      langgraph_host/              # reference host (candidate, see Q2)
      second_host/                 # second host for the portability claim
      statemas_adapter/            # only if the artifact is available
    injectors/
      tool_failure.py
      timeout.py
      tool_output_unused.py
      handoff_incomplete.py
      plan_error.py
      insufficient_verification.py
  experiments/
    runner.py                      # incident stream, seeds, conditions
    outcome_matrix.py
    calibrate.py                   # alpha selection on calibration data
    split.py                       # 20/80 by task_id
  analysis/
    metrics.py
    stats.py                       # McNemar, per-task bootstrap, Wilcoxon, Holm
    power.py
    report.py
  tests/
    unit/ integration/ e2e/ property/
```

The `arclayer_sdk` package deliberately imports **nothing** from `arclayer.core`, only from `arclayer.contracts`. This keeps the host independent of control plane internals, and it is verified by an import test (T-ARCH-01).
