# System Architecture

> Status note: translated from the original implementation plan (October 2026). The code may have diverged from this plan; see docs/architecture for the current structure.

## 3.1 Components

```mermaid
flowchart LR
  subgraph HOST["Multi-agent host system (any framework)"]
    ORCH[Orchestrator / coordination pattern]
    AG[Primary agent]
    RA[Registered recovery agents h1..hK]
    CK[(Checkpoint / state store)]
    SDK[Adapter SDK: emit + executor]
    ORCH --> SDK
    SDK --> RA
    SDK --> CK
  end

  subgraph CP["Control plane (FastAPI)"]
    API[REST API /v1]
    NORM[Event normalizer + redaction]
    CTX[Fault context builder]
    REG[(Recovery registry)]
    GATE[Eligibility and safety gate]
    SEL[Selector: LinUCB / baseline]
    VER[Verifier]
    RW[Reward builder]
    PS[(Policy store)]
    AUD[(Audit logger)]
    API --> NORM --> CTX --> GATE
    REG --> GATE
    GATE --> SEL
    SEL <--> PS
    API --> VER --> RW --> PS
    SEL --> AUD
    VER --> AUD
  end

  subgraph EXP["Experiment environment (not production)"]
    BEN[Benchmark runner]
    INJ[Fault injector]
    ORA[Verifier oracle: ground truth]
    EVA[Evaluator + statistics]
  end

  SDK -- "POST /incidents" --> API
  API -- "RecoveryCommand" --> SDK
  SDK -- "POST /incidents/id/result" --> API
  BEN --> HOST
  INJ --> HOST
  ORA -.-> VER
  AUD -.-> EVA
```

## 3.2 Sequence of one incident (follows Figure 2 of the proposal)

```mermaid
sequenceDiagram
  participant H as Host + SDK
  participant A as API
  participant C as Context builder
  participant G as Registry + gate
  participant S as Selector
  participant P as Policy store
  participant V as Verifier
  participant R as Reward builder

  H->>A: POST /v1/incidents (FaultEvent)
  A->>C: normalize + build f_t
  C->>G: f_t
  G->>G: filter -> H_t
  alt H_t empty
    A-->>H: RecoveryCommand(action=safe_stop or escalate)
  else H_t not empty
    G->>S: H_t, x_t,h
    S->>P: read A_h, b_h (lock policy instance)
    S->>S: p_t,h, choose h_t
    A-->>H: RecoveryCommand(action=execute, h_t, params, scores)
    H->>H: execute h_t, continue rollout
    H->>A: POST /v1/incidents/{id}/result (ExecutionResult)
    A->>V: verify -> S,C,L,V
    V->>R: r_t (Equation 6)
    R->>P: update A_ht, b_ht (Equations 4-5), unlock
    A-->>H: OutcomeAck(status=recovered | failed | escalate)
  end
```

Design note: the policy instance lock is held from the decision until the result is received **only in sequential experiment mode** (`strict_sequential=true`). In service mode, decisions are read without holding the lock and the update is applied when the result arrives (the update order is recorded in the audit). Experiment mode must use `strict_sequential=true`.

## 3.3 Incident state machine

```
RECEIVED -> CONTEXT_BUILT -> GATED -> { SAFE_STOPPED | ESCALATED | DECIDED }
DECIDED -> AWAITING_RESULT -> VERIFIED -> UPDATED -> { RECOVERED | FAILED }
AWAITING_RESULT -> CENSORED   (TTL expired, no update)
```

An illegal transition returns HTTP 409. The state machine is tested with a transition-table test (T-CORE-09).
