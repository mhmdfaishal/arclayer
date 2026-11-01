"""ArcLayer: the class a host imports.

One host process owns one ArcLayer. It keeps its state (policies, incidents, audit) in a SQLite
file, or in memory when `db_url` is None, and talks to the host only through the contracts in
`arclayer.contracts` and the protocols in `arclayer.host`.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path
from typing import Any, Sequence

import arclayer.contracts as C
from arclayer.bootstrap import build_default_services, seed_candidates
from arclayer.delivery.inprocess import InProcessControlPlaneClient
from arclayer.delivery.mappers import (
    candidate_from_spec,
    candidate_to_spec,
    create_policy_cmd,
    incident_to_out,
    policy_to_out,
    snapshot_to_out,
)
from arclayer.host.protocols import HostAdapter
from arclayer.host.runtime import FaultOutcome, handle_fault
from arclayer.domain.errors import DomainError, IllegalTransition, InvalidRewardWeights
from arclayer.usecases.errors import ApplicationError, Conflict, FeatureMismatch, NotFound, PolicyBusy

__all__ = [
    "ArcLayer", "ApplicationError", "Conflict", "DomainError", "FeatureMismatch", "IllegalTransition",
    "InvalidRewardWeights", "NotFound", "PolicyBusy",
]


class ArcLayer:
    """
    Args:
        db_url: SQLite URL. None keeps everything in memory and forgets it on exit.
        embedding: "hashing" (offline, no semantic meaning) or "st:<sentence-transformers model>".
        candidates: a YAML path or a list of CandidateSpec, registered only while the registry is empty.
        censor_ttl_s: seconds before an incident without a result counts as abandoned.
        censor_orphans_on_start: close incidents a previous process left waiting for a result. Leave it on
            when this is the only process using the database.
    """

    def __init__(
        self,
        db_url: str | None = "sqlite:///./arclayer.db",
        *,
        embedding: str = "hashing",
        candidates: str | Path | Sequence[C.CandidateSpec] | None = None,
        censor_ttl_s: float = 3600,
        censor_orphans_on_start: bool = True,
    ) -> None:
        self._services = build_default_services(db_url, embedding, censor_ttl_s)
        self._client = InProcessControlPlaneClient(self._services)
        if candidates is not None:
            self._seed(candidates)
        if censor_orphans_on_start:
            self._services.censor_expired.execute(ttl=timedelta(0))

    def _seed(self, source: str | Path | Sequence[C.CandidateSpec]) -> None:
        if isinstance(source, (str, Path)):
            seed_candidates(self._services, source)
        elif not self._services.list_candidates.execute():
            for spec in source:
                self.register_candidate(spec)

    # candidates and ground truth

    def register_candidate(self, spec: C.CandidateSpec) -> C.CandidateSpec:
        return candidate_to_spec(self._services.register_candidate.execute(candidate_from_spec(spec)))

    def candidates(self) -> list[C.CandidateSpec]:
        return [candidate_to_spec(c) for c in self._services.list_candidates.execute()]

    def set_candidate_enabled(self, candidate_id: str, enabled: bool) -> C.CandidateSpec:
        """Affects policies created afterwards; a policy keeps the candidates it was created with."""
        return candidate_to_spec(self._services.set_candidate_enabled.execute(candidate_id, enabled))

    def register_ground_truth(self, task_id: str, answer: str) -> None:
        """Ground truth for the benchmark verifier. It is never sent to the host or to a candidate."""
        self._services.register_oracle_answer.execute(task_id, answer)

    # policies

    def create_policy(
        self,
        kind: str | C.PolicyKind = "P",
        seed: int = 0,
        *,
        n_max: int = 1,
        step_cap: int = 20,
        task_cost_cap: float = 3.0,
        incident_cost_cap: float = 1.0,
        incident_latency_cap_ms: int = 300_000,
        strict_sequential: bool = False,
        allowed_permissions: Sequence[str] | None = None,
        **options: Any,
    ) -> str:
        """Create a selection policy and return its id.

        `allowed_permissions` defaults to every permission of the enabled candidates. Cost caps use the
        unit your executors report in `cost_used`. `strict_sequential=True` rejects a new incident while
        another is waiting for its result (PolicyBusy), which experiments need for reproducibility.
        `options` are the remaining `CreatePolicyIn` fields: alpha, lam, reward_weights, static_map,
        static_default, retry_candidate_id, init_state, policy_id, experiment_id.
        """
        if allowed_permissions is None:
            allowed_permissions = sorted(
                {p for c in self._services.list_candidates.execute() if c.enabled for p in c.permissions}
            )
        body = C.CreatePolicyIn(
            kind=kind, seed=seed, n_max=n_max,
            feature_spec=C.FeatureSpecIn(step_cap=step_cap, budget_task_cap=task_cost_cap, n_max=n_max),
            caps=C.BudgetCapsIn(
                incident_cost_cap=incident_cost_cap,
                incident_latency_cap_ms=incident_latency_cap_ms,
                task_cost_cap=task_cost_cap,
            ),
            allowed_permissions=list(allowed_permissions),
            strict_sequential=strict_sequential,
            **options,
        )
        return self._services.create_policy.execute(create_policy_cmd(body)).policy_id

    def get_policy(self, policy_id: str) -> C.PolicyOut:
        return policy_to_out(self._services.get_policy.execute(policy_id))

    def freeze_policy(self, policy_id: str) -> C.PolicyOut:
        return policy_to_out(self._services.freeze_policy.execute(policy_id))

    def snapshot_policy(self, policy_id: str) -> C.PolicySnapshotOut:
        return snapshot_to_out(self._services.snapshot_policy.execute(policy_id))

    # incidents

    def post_incident(self, event: C.FaultEventIn) -> C.RecoveryCommandOut:
        return self._client.post_incident(event)

    def post_result(self, result: C.ExecutionResultIn, idempotency_key: str) -> C.OutcomeAckOut:
        return self._client.post_result(result, idempotency_key)

    def incident(self, incident_id: str) -> C.IncidentOut:
        return incident_to_out(self._services.get_incident.execute(incident_id))

    def handle_fault(
        self,
        native_fault: Any,
        adapter: HostAdapter,
        policy_id: str,
        native_context: Any = None,
        idempotency_key: str | None = None,
    ) -> FaultOutcome:
        """Report a fault, run the chosen candidate through the adapter's executors, report the result."""
        return handle_fault(native_fault, adapter, self, policy_id, native_context, idempotency_key)

    async def handle_fault_async(
        self,
        native_fault: Any,
        adapter: HostAdapter,
        policy_id: str,
        native_context: Any = None,
        idempotency_key: str | None = None,
    ) -> FaultOutcome:
        """`handle_fault` in a worker thread, so an async framework's event loop is not blocked."""
        return await asyncio.to_thread(self.handle_fault, native_fault, adapter, policy_id, native_context, idempotency_key)

    def censor_expired(self, ttl_s: float | None = None) -> list[str]:
        """Close incidents waiting longer than the TTL without updating the policy. Returns their ids."""
        return self._services.censor_expired.execute(None if ttl_s is None else timedelta(seconds=ttl_s))
