# Security and Ethics (implementation of III.3.4)

> Status note: translated from the original implementation plan (October 2026). The code may have diverged from this plan; see docs/architecture for the current structure.

- Experiments run in an isolated environment (containers without production credentials; outbound network only to the model API and allowlisted free tools).
- The model API key is read from the environment and never enters `FaultEvent`, the audit, or the replication artifacts; redaction is tested.
- The gate and the allowlist are the only path to execution; the selector cannot produce a `candidate_id` outside `H_t` (assertion in the orchestrator + test).
- Cost limits per incident and per task are enforced in two places: the gate (before) and the verifier (`V=1` after).
- The system does not create new agents and does not add permissions: the registry changes only through configuration or the authenticated API, and a policy instance uses a snapshot.
