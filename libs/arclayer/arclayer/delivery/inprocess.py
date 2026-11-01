"""Transport in-process: memenuhi ControlPlaneClient tanpa HTTP.

Dipakai untuk test dan simulasi outcome matrix supaya overhead jaringan tidak masuk ke
metrik latensi. Jalur validasi kontrak tetap sama dengan HTTP karena masukan/keluaran
tetap melewati model Pydantic arclayer.contracts.
"""

from __future__ import annotations

import arclayer.contracts as C
from arclayer.bootstrap import Services
from arclayer.delivery.mappers import ack_to_out, command_to_out, event_from_in, result_from_in


class InProcessControlPlaneClient:
    def __init__(self, services: Services) -> None:
        self.services = services

    def post_incident(self, event: C.FaultEventIn) -> C.RecoveryCommandOut:
        return command_to_out(self.services.handle_incident.execute(event_from_in(event)))

    def post_result(self, result: C.ExecutionResultIn, idempotency_key: str) -> C.OutcomeAckOut:
        return ack_to_out(self.services.report_result.execute(result_from_in(result), idempotency_key))
