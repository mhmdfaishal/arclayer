"""Embedding semantik via sentence-transformers (dipakai eksperimen utama).

Model dimuat malas pada embed() pertama: mengimpor torch dan memuat bobot memakan detik
sampai puluhan detik, dan tidak boleh membebani startup service atau test yang tidak
membutuhkannya. Cache per teks ada karena deskripsi kandidat (konstan) di-embed ulang di
setiap insiden; hanya fault_description yang benar-benar baru.
"""

from __future__ import annotations

import threading
from typing import Any, Sequence

import numpy as np

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def _load_model(model_name: str, device: str | None) -> Any:
    # Import di dalam fungsi: torch hanya ditarik saat model benar-benar dibutuhkan,
    # dan test bisa mengganti fungsi ini dengan model palsu tanpa unduhan.
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name, device=device)


class SentenceTransformerEmbeddingProvider:
    def __init__(self, model_name: str = DEFAULT_MODEL, device: str | None = None) -> None:
        self.model_name = model_name
        self.device = device
        self.model_id = f"st:{model_name}"
        self._model: Any | None = None
        self._cache: dict[str, np.ndarray] = {}
        # Satu lock untuk load dan encode: endpoint sync berjalan di thread pool dan
        # model torch tidak dijamin aman dipakai bersamaan.
        self._lock = threading.Lock()

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 0))
        with self._lock:
            missing = list(dict.fromkeys(t for t in texts if t not in self._cache))
            if missing:
                if self._model is None:
                    self._model = _load_model(self.model_name, self.device)
                vecs = np.asarray(self._model.encode(missing), dtype=float)
                # Normalisasi dilakukan di sini (bukan bergantung pada flag model) agar
                # kontrak port "baris ternormalisasi L2" berlaku untuk model apa pun.
                norms = np.linalg.norm(vecs, axis=1, keepdims=True)
                vecs = np.divide(vecs, norms, out=np.zeros_like(vecs), where=norms > 0)
                for t, v in zip(missing, vecs):
                    self._cache[t] = v
            # np.vstack menyalin, jadi pemanggil tidak memegang view ke cache.
            return np.vstack([self._cache[t] for t in texts])
