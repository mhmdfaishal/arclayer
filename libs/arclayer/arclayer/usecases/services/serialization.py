"""Konversi objek domain ke struktur JSON-able untuk audit dan fingerprint."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any

import numpy as np


def to_jsonable(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_jsonable(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    if isinstance(obj, dict):
        return {(k.value if isinstance(k, Enum) else str(k)): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        items = [to_jsonable(v) for v in obj]
        return sorted(items, key=str) if isinstance(obj, (set, frozenset)) else items
    return obj


def fingerprint(obj: Any) -> str:
    raw = json.dumps(to_jsonable(obj), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def state_checksum(state: dict[str, Any] | None) -> str | None:
    """Checksum A dan b; dipakai di audit untuk membuktikan urutan pembaruan."""
    if state is None:
        return None
    return fingerprint({"A": state.get("A"), "b": state.get("b")})
