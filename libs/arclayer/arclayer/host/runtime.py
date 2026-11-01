"""The loop a host runs when it detects a fault: report it, run the chosen candidate, report the result."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from arclayer.contracts import (
    Action,
    ExecutionResultIn,
    OutcomeAckOut,
    RecoveryCommandOut,
    Terminal,
)
from arclayer.host.protocols import ControlPlaneClient, HostAdapter


class HostMisconfigured(RuntimeError):
    """Control plane memerintahkan kandidat yang tidak punya executor di host."""


@dataclass(frozen=True)
class FaultOutcome:
    command: RecoveryCommandOut
    result: ExecutionResultIn | None = None
    ack: OutcomeAckOut | None = None


def handle_fault(
    native_fault: Any,
    adapter: HostAdapter,
    client: ControlPlaneClient,
    policy_instance_id: str,
    native_context: Any = None,
    idempotency_key: str | None = None,
) -> FaultOutcome:
    event = adapter.to_fault_event(native_fault, policy_instance_id)
    command = client.post_incident(event)
    if command.action is not Action.EXECUTE:
        # safe_stop/escalate: tidak ada yang dieksekusi dan control plane tidak
        # menunggu hasil, jadi tidak ada yang dilaporkan.
        return FaultOutcome(command)

    assert command.candidate_id is not None
    executor = adapter.executors().get(command.candidate_id)
    if executor is None:
        # Dilempar sebelum eksekusi: insiden tetap menunggu hasil di server dan akan
        # di-censor oleh TTL, bukan dilaporkan sebagai kegagalan kandidat (itu bias).
        raise HostMisconfigured(f"host {adapter.host_id} tidak punya executor untuk kandidat {command.candidate_id}")

    # Default ke insiden native: executor biasanya butuh konteks yang sama dengan yang
    # membentuk FaultEvent.
    ctx = native_fault if native_context is None else native_context
    started = time.perf_counter()
    try:
        result = executor.execute(command, ctx)
    except Exception:
        # Kegagalan executor tetap dilaporkan: tanpa itu policy strict_sequential
        # tertahan menunggu hasil. Latensi diukur di sisi host (control plane tidak
        # melihat durasi eksekusi).
        result = ExecutionResultIn(
            incident_id=command.incident_id,
            candidate_id=command.candidate_id,
            terminal=Terminal.EXECUTOR_ERROR,
            final_answer=None,
            cost_used=0.0,
            tokens_used=0,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
    key = idempotency_key or f"{command.incident_id}:{command.candidate_id}"
    ack = client.post_result(result, key)
    return FaultOutcome(command, result, ack)
