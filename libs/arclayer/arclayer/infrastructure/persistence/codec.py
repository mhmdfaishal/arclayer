"""Codec dataclass domain <-> struktur JSON-able dengan round-trip persis.

Kenapa dibuat generik berbasis type hints dan bukan memakai to_jsonable():
to_jsonable() satu arah dan lossy (tuple jadi list, frozenset diurutkan, tidak ada info
tipe). Persistence butuh decode yang mengembalikan tuple/frozenset/enum/datetime asli,
karena sebagian domain bergantung padanya (mis. `set(c.permissions) <= ...`, kesetaraan
dataclass frozen, hash). Decoder dikendalikan get_type_hints sehingga menambah field di
domain tidak perlu mengubah file ini.

Batasan yang disengaja: field bertipe `Any` (selector_state, rng_state, parameters,
extra) diperlakukan sebagai JSON murni. Isinya sudah dict/list/angka/string dari
use case, jadi tidak ada tipe khusus yang hilang. Float dijaga bit-exact karena
json memakai repr() yang round-trip untuk float64.
"""

from __future__ import annotations

import dataclasses
import types
import typing
from datetime import datetime
from enum import Enum
from functools import lru_cache
from typing import Any, Union, get_args, get_origin, get_type_hints


def encode(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: encode(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, (frozenset, set)):
        # Urutan stabil agar payload deterministik (berguna untuk diff dan audit).
        return sorted((encode(v) for v in obj), key=str)
    if isinstance(obj, (tuple, list)):
        return [encode(v) for v in obj]
    if isinstance(obj, dict):
        return {(k.value if isinstance(k, Enum) else k): encode(v) for k, v in obj.items()}
    return obj


@lru_cache(maxsize=None)
def _hints(cls: type) -> dict[str, Any]:
    return get_type_hints(cls)


def decode(tp: Any, data: Any) -> Any:
    if tp is Any:
        return data
    origin = get_origin(tp)

    if origin is Union or origin is types.UnionType:
        args = get_args(tp)
        if data is None:
            if type(None) in args:
                return None
            raise TypeError(f"None tidak valid untuk {tp}")
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) != 1:
            raise TypeError(f"union ambigu tidak didukung: {tp}")
        return decode(non_none[0], data)

    if origin is tuple:
        args = get_args(tp)
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(decode(args[0], v) for v in data)
        return tuple(decode(a, v) for a, v in zip(args, data, strict=True))
    if origin is frozenset:
        (arg,) = get_args(tp)
        return frozenset(decode(arg, v) for v in data)
    if origin is list:
        (arg,) = get_args(tp)
        return [decode(arg, v) for v in data]
    if origin is dict:
        k_tp, v_tp = get_args(tp)
        return {decode(k_tp, k): decode(v_tp, v) for k, v in data.items()}

    if isinstance(tp, type):
        if dataclasses.is_dataclass(tp):
            hints = _hints(tp)
            kwargs = {f.name: decode(hints[f.name], data[f.name]) for f in dataclasses.fields(tp) if f.name in data}
            return tp(**kwargs)
        if issubclass(tp, Enum):
            return tp(data)
        if tp is datetime:
            return datetime.fromisoformat(data)
        # Skalar (str/int/float/bool) dikembalikan apa adanya: tidak di-cast supaya
        # int yang sengaja disimpan di field float tidak berubah diam-diam.
        return data

    raise TypeError(f"tipe tidak didukung codec: {tp}")


__all__ = ["encode", "decode"]
