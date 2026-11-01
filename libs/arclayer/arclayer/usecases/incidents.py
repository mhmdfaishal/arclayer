"""Use case inti: Algoritme 1 usulan, dipecah menjadi dua panggilan sesuai Gambar 2.

HandleIncident  = langkah 1-8  (konteks, gate, skor, pilih satu kandidat, perintah)
ReportResult    = langkah 9-16 (verifikasi, reward, update hanya kandidat terpilih)
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np

from arclayer.usecases.errors import Conflict, FeatureMismatch, NotFound, PolicyBusy
from arclayer.usecases.ports import Clock, EmbeddingProvider, IdGenerator, PolicyLocks, UnitOfWorkFactory
from arclayer.usecases.services import rng as rng_svc
from arclayer.usecases.services.redaction import redact_event
from arclayer.usecases.services.serialization import fingerprint, state_checksum, to_jsonable
from arclayer.usecases.services.verifiers import SuccessVerifier
from arclayer.domain.entities import Incident, PolicyInstance
from arclayer.domain.enums import Action, IncidentStatus, PolicyKind, Precondition, Terminal
from arclayer.domain.errors import IllegalTransition
from arclayer.domain.features import build_x, spec_hash
from arclayer.domain.gate import evaluate_gate
from arclayer.domain.models import (
    ArmFeatures,
    Candidate,
    ExecutionResult,
    FaultEvent,
    OutcomeAck,
    RecoveryCommand,
    Selection,
)
from arclayer.domain.policies.factory import build_selector
from arclayer.domain.reward import compute_reward
from arclayer.domain.verification import compute_verification


def _parameters(c: Candidate, event: FaultEvent) -> dict[str, object]:
    params: dict[str, object] = {"template": f"{c.candidate_id}@{c.version}"}
    if Precondition.CHECKPOINT_AVAILABLE in c.required_preconditions:
        params["checkpoint_id"] = event.checkpoint_id
    if event.fault_class is not None:
        params["fault_class"] = event.fault_class.value
    return params


def _conditions(c: Candidate) -> tuple[str, ...]:
    return (
        f"verifier:{c.verifier_id}",
        f"max_cost<={c.max_cost}",
        f"max_latency_ms<={c.max_latency_ms}",
        "permissions:" + ",".join(sorted(c.permissions)),
    )


class HandleIncident:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        embedder: EmbeddingProvider,
        clock: Clock,
        ids: IdGenerator,
        locks: PolicyLocks,
    ) -> None:
        self.uow_factory = uow_factory
        self.embedder = embedder
        self.clock = clock
        self.ids = ids
        self.locks = locks

    def _cosines(self, event: FaultEvent, cands: tuple[Candidate, ...]) -> list[float]:
        vecs = self.embedder.embed([event.fault_description, *[c.description for c in cands]])
        return [float(vecs[0] @ v) for v in vecs[1:]]

    def execute(self, raw_event: FaultEvent) -> RecoveryCommand:
        pid = raw_event.policy_instance_id
        with self.locks.lock(pid), self.uow_factory() as uow:
            policy = uow.policies.get(pid)
            if policy is None:
                raise NotFound(f"policy {pid}")
            if policy.embedding_model_id != self.embedder.model_id or policy.feature_hash != spec_hash(
                policy.feature_spec, policy.variant, self.embedder.model_id
            ):
                raise FeatureMismatch("model embedding/spesifikasi fitur berbeda dari yang dibekukan")
            if policy.strict_sequential and policy.pending_incident_id is not None:
                raise PolicyBusy(f"policy {pid} masih menunggu hasil insiden {policy.pending_incident_id}")

            now = self.clock.now()
            event = redact_event(raw_event)
            incident = Incident(
                incident_id=self.ids.new_id(),
                policy_id=pid,
                event=event,
                status=IncidentStatus.RECEIVED,
                received_at=now,
            )

            command = self._decide(policy, incident)
            incident.command = command
            incident.decided_at = now

            if command.action is Action.EXECUTE:
                incident.transition(IncidentStatus.AWAITING_RESULT)
                policy.pending_incident_id = incident.incident_id if policy.strict_sequential else None
            elif command.action is Action.ESCALATE:
                incident.transition(IncidentStatus.ESCALATED)
            else:
                incident.transition(IncidentStatus.SAFE_STOPPED)

            uow.incidents.add(incident)
            uow.policies.save(policy)
            uow.audit.append({
                "event": "decision",
                "incident_id": incident.incident_id,
                "policy_id": pid,
                "policy_kind": policy.kind.value,
                "seed": policy.seed,
                "experiment_id": policy.experiment_id,
                "feature_hash": policy.feature_hash,
                "task_id": event.task_id,
                "fault_class": event.fault_class.value if event.fault_class else None,
                "orchestration": event.orchestration.value,
                "fault_context": to_jsonable(event),
                "eligible": [a.candidate_id for a in incident.arms],
                "rejections": to_jsonable(incident.rejections),
                "arms": to_jsonable(incident.arms),
                "scores": to_jsonable(command.scores),
                "chosen": command.candidate_id,
                "action": command.action.value,
                "reason": command.reason,
                "at": now.isoformat(),
            })
            uow.commit()
        return command

    def _decide(self, policy: PolicyInstance, incident: Incident) -> RecoveryCommand:
        event = incident.event

        def stop(action: Action, reason: str, sel: Selection | None = None) -> RecoveryCommand:
            return RecoveryCommand(
                incident_id=incident.incident_id, action=action, candidate_id=None, parameters={},
                verification_conditions=(), scores=sel.scores if sel else (),
                excluded=incident.rejections, reason=reason, deadline_ms=0,
            )

        # B0 tidak melewati gate: batas bawah "tanpa recovery".
        if policy.kind is PolicyKind.B0:
            return stop(Action.SAFE_STOP, "B0: tanpa recovery")

        gate = evaluate_gate(event, policy.candidates, policy.gate_config)
        incident.rejections = gate.rejections
        if not gate.eligible:
            assert gate.empty_action is not None
            return stop(gate.empty_action, "tidak ada kandidat yang lolos gate")

        cosines = self._cosines(event, gate.eligible)
        incident.arms = tuple(
            ArmFeatures(
                candidate_id=c.candidate_id,
                x=tuple(float(v) for v in build_x(event, c, cos, policy.feature_spec, policy.variant)),
                cosine=cos,
            )
            for c, cos in zip(gate.eligible, cosines)
        )

        selector = build_selector(policy)
        rng = rng_svc.restore(policy.rng_state)
        sel = selector.select(incident.arms, event, rng)
        policy.rng_state = rng_svc.dump(rng)

        if sel.candidate_id is None:
            return stop(Action.SAFE_STOP, sel.reason, sel)
        # Pengaman: kebijakan apa pun tidak boleh keluar dari wilayah yang diizinkan gate.
        if sel.candidate_id not in {a.candidate_id for a in incident.arms}:
            raise AssertionError(f"selector memilih kandidat di luar H_t: {sel.candidate_id}")

        cand = policy.candidate(sel.candidate_id)
        return RecoveryCommand(
            incident_id=incident.incident_id,
            action=Action.EXECUTE,
            candidate_id=cand.candidate_id,
            parameters=_parameters(cand, event),
            verification_conditions=_conditions(cand),
            scores=sel.scores,
            excluded=gate.rejections,
            reason=sel.reason,
            deadline_ms=cand.max_latency_ms,
        )


class ReportResult:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        verifiers: dict[str, SuccessVerifier],
        clock: Clock,
        locks: PolicyLocks,
    ) -> None:
        self.uow_factory = uow_factory
        self.verifiers = verifiers
        self.clock = clock
        self.locks = locks

    def execute(self, result: ExecutionResult, idempotency_key: str) -> OutcomeAck:
        with self.uow_factory() as uow0:
            peek = uow0.incidents.get(result.incident_id)
        if peek is None:
            raise NotFound(f"insiden {result.incident_id}")

        with self.locks.lock(peek.policy_id), self.uow_factory() as uow:
            incident = uow.incidents.get(result.incident_id)
            policy = uow.policies.get(peek.policy_id)
            assert incident is not None and policy is not None
            fp = fingerprint(result)

            # Idempotensi: pengiriman ulang identik mengembalikan ack yang sama tanpa
            # pembaruan kedua; payload/kunci berbeda untuk insiden yang sama = konflik.
            if incident.idempotency_key is not None:
                if incident.idempotency_key == idempotency_key and incident.result_fingerprint == fp:
                    assert incident.ack is not None
                    return incident.ack
                raise Conflict(f"hasil insiden {incident.incident_id} sudah dilaporkan dengan payload/kunci berbeda")

            if incident.status is not IncidentStatus.AWAITING_RESULT:
                raise IllegalTransition(f"insiden {incident.incident_id} berstatus {incident.status.value}, tidak menunggu hasil")
            assert incident.command is not None
            if result.candidate_id != incident.command.candidate_id:
                raise Conflict(f"hasil untuk {result.candidate_id}, padahal yang diperintahkan {incident.command.candidate_id}")

            cand = policy.candidate(result.candidate_id)
            verifier = self.verifiers[cand.verifier_id]
            success = verifier(result, uow.oracle.get(incident.event.task_id))
            verification = compute_verification(result, cand, policy.caps, success)
            reward = compute_reward(verification, policy.reward_weights)

            selector = build_selector(policy)
            before = state_checksum(policy.selector_state)
            x = np.asarray(incident.arm(result.candidate_id).x)
            updated = selector.update(result.candidate_id, x, reward)  # hanya kandidat terpilih
            if updated:
                policy.selector_state = selector.export_state()
            after = state_checksum(policy.selector_state)

            if verification.S == 1:
                status, label = IncidentStatus.RECOVERED, "recovered"
            elif (
                result.terminal is Terminal.BUDGET_EXHAUSTED
                or incident.event.prior_incidents_in_task + 1 >= policy.gate_config.n_max
            ):
                # Tidak akan ada putaran berikutnya untuk tugas ini (Algoritme 1, langkah 15).
                status, label = IncidentStatus.ESCALATED, "escalate"
            else:
                status, label = IncidentStatus.FAILED, "failed"
            incident.transition(status)

            now = self.clock.now()
            ack = OutcomeAck(incident.incident_id, label, reward, updated)
            incident.result = result
            incident.verification = verification
            incident.reward = reward
            incident.policy_updated = updated
            incident.idempotency_key = idempotency_key
            incident.result_fingerprint = fp
            incident.ack = ack
            incident.result_at = now
            if policy.pending_incident_id == incident.incident_id:
                policy.pending_incident_id = None

            uow.incidents.save(incident)
            uow.policies.save(policy)
            uow.audit.append({
                "event": "result",
                "incident_id": incident.incident_id,
                "policy_id": policy.policy_id,
                "policy_kind": policy.kind.value,
                "seed": policy.seed,
                "experiment_id": policy.experiment_id,
                "task_id": incident.event.task_id,
                "fault_class": incident.event.fault_class.value if incident.event.fault_class else None,
                "orchestration": incident.event.orchestration.value,
                "chosen": result.candidate_id,
                "execution_result": to_jsonable(result),
                "S": verification.S,
                "C": verification.C,
                "L": verification.L,
                "V": verification.V,
                "verification_details": to_jsonable(verification.details),
                "reward": reward,
                "status": label,
                "policy_updated": updated,
                "checksum_before": before,
                "checksum_after": after,
                "at": now.isoformat(),
            })
            uow.commit()
        return ack


class CensorExpired:
    """Insiden tanpa hasil melewati TTL ditandai censored dan TIDAK memperbarui policy:
    memperbarui dengan reward 0 akan membiaskan estimasi."""

    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock, locks: PolicyLocks, ttl: timedelta) -> None:
        self.uow_factory = uow_factory
        self.clock = clock
        self.locks = locks
        self.ttl = ttl

    def execute(self, ttl: timedelta | None = None) -> list[str]:
        """`ttl` overrides the configured TTL; `timedelta(0)` censors every incident still waiting."""
        limit = self.ttl if ttl is None else ttl
        now = self.clock.now()
        with self.uow_factory() as uow:
            waiting = uow.incidents.list_by_status(IncidentStatus.AWAITING_RESULT)
        expired = [i for i in waiting if i.decided_at is not None and now - i.decided_at > limit]
        done: list[str] = []
        for stale in expired:
            with self.locks.lock(stale.policy_id), self.uow_factory() as uow:
                inc = uow.incidents.get(stale.incident_id)
                if inc is None or inc.status is not IncidentStatus.AWAITING_RESULT:
                    continue
                inc.transition(IncidentStatus.CENSORED)
                uow.incidents.save(inc)
                pol = uow.policies.get(inc.policy_id)
                if pol is not None and pol.pending_incident_id == inc.incident_id:
                    pol.pending_incident_id = None
                    uow.policies.save(pol)
                uow.audit.append({
                    "event": "censored", "incident_id": inc.incident_id,
                    "policy_id": inc.policy_id, "at": now.isoformat(),
                })
                uow.commit()
                done.append(inc.incident_id)
        return done


class GetIncident:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self.uow_factory = uow_factory

    def execute(self, incident_id: str) -> Incident:
        with self.uow_factory() as uow:
            i = uow.incidents.get(incident_id)
        if i is None:
            raise NotFound(f"insiden {incident_id}")
        return i
