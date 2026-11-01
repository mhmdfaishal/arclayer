from __future__ import annotations

import threading
import uuid
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class UuidGenerator:
    def new_id(self) -> str:
        return str(uuid.uuid4())


class ThreadPolicyLocks:
    """Lock per policy instance dalam satu proses. Cukup untuk satu worker Uvicorn;
    multi-worker butuh lock di database (di luar cakupan eksperimen)."""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[str, threading.RLock] = defaultdict(threading.RLock)

    @contextmanager
    def lock(self, policy_id: str) -> Iterator[None]:
        with self._guard:
            lk = self._locks[policy_id]
        with lk:
            yield
