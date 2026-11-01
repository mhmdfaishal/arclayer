"""Embedding deterministik berbasis hashing token (bag-of-words ter-hash).

Bukan pengganti model semantik: dipakai untuk test dan simulasi agar cepat, bebas
unduhan, dan deterministik lintas mesin. Eksperimen utama memakai
SentenceTransformerEmbeddingProvider; model_id berbeda membuat policy menolak
campuran keduanya (lihat FeatureMismatch).
"""

from __future__ import annotations

import hashlib
import re
from typing import Sequence

import numpy as np

_TOKEN = re.compile(r"[a-z0-9]+")


class HashingEmbeddingProvider:
    def __init__(self, dim: int = 384) -> None:
        self.dim = dim
        self.model_id = f"hashing-{dim}"

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim)
        for tok in _TOKEN.findall(text.lower()):
            h = hashlib.blake2b(tok.encode(), digest_size=8).digest()
            idx = int.from_bytes(h[:4], "little") % self.dim
            sign = 1.0 if h[4] & 1 else -1.0
            v[idx] += sign
        n = np.linalg.norm(v)
        return v / n if n > 0 else v

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        return np.vstack([self._vec(t) for t in texts]) if texts else np.zeros((0, self.dim))
