"""Interfaces a host implements (HostAdapter, RecoveryExecutor) and the client protocol that
handle_fault talks to (ControlPlaneClient, which ArcLayer satisfies)."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from arclayer.contracts import ExecutionResultIn, FaultEventIn, OutcomeAckOut, RecoveryCommandOut


class ControlPlaneClient(Protocol):
    def post_incident(self, event: FaultEventIn) -> RecoveryCommandOut: ...

    def post_result(self, result: ExecutionResultIn, idempotency_key: str) -> OutcomeAckOut: ...


class RecoveryExecutor(Protocol):
    """Implementasi satu kandidat agen pemulihan di dalam host. Wajib melaporkan
    `actions_performed` dengan jujur; control plane menandai pelanggaran (V=1) bila
    aksi di luar izin kandidat."""

    candidate_id: str

    def execute(self, command: RecoveryCommandOut, native_context: Any) -> ExecutionResultIn: ...


class HostAdapter(Protocol):
    host_id: str
    capabilities: list[str]

    def to_fault_event(self, native_fault: Any, policy_instance_id: str) -> FaultEventIn: ...

    def executors(self) -> Mapping[str, RecoveryExecutor]: ...
