"""Pembentukan vektor fitur x_{t,h} = [f_t, g(t,h), 1] (Subbab III.2.2).

Tata letak FULL (d = 20):
  0-5   one-hot kelas fault (semua nol bila tidak diketahui)
  6     keyakinan kelas
  7-10  one-hot pola orkestrasi
  11    posisi relatif langkah
  12    insiden sebelumnya pada tugas / N_max
  13    checkpoint dapat dipulihkan
  14    sisa anggaran / batas anggaran tugas
  15    cosine(fault, deskripsi kandidat) dipetakan ke [0, 1]
  16    kecocokan kelas (1, 0, atau 0.5 bila kelas tidak diketahui)
  17    rasio biaya maksimum kandidat / sisa anggaran
  18    kelengkapan prasyarat opsional
  19    bias

Kenapa kelas dan prasyarat wajib tidak dijadikan indikator biner: gate sudah membuang
kandidat yang prasyarat wajibnya gagal, sehingga indikator semacam itu selalu 1 untuk
kandidat layak dan kolinear dengan bias. Kelas dibiarkan sebagai fitur lunak (gate tidak
menyaring kelas), dan prasyarat diganti rasio prasyarat opsional yang terpenuhi.

Varian NO_CANDIDATE (ablasi P-D, d = 17) membuang 15, 16, 18 tetapi mempertahankan rasio
biaya karena rasio biaya bukan fitur deskripsi/kapabilitas kandidat.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

import numpy as np

from arclayer.domain.enums import FaultClass, FeatureVariant, LabelSource, OrchestrationPattern
from arclayer.domain.models import Candidate, FaultEvent
from arclayer.domain.preconditions import precondition_satisfied

FEATURE_VERSION = "v1"


@dataclass(frozen=True)
class FeatureSpec:
    """Konstanta normalisasi yang dibekukan pada data kalibrasi."""

    step_cap: int
    budget_task_cap: float
    n_max: int
    version: str = FEATURE_VERSION


def _clip01(v: float) -> float:
    return float(min(max(v, 0.0), 1.0))


def fault_vector(event: FaultEvent, spec: FeatureSpec) -> np.ndarray:
    classes = list(FaultClass)
    onehot_class = np.zeros(len(classes))
    if event.fault_class is not None:
        onehot_class[classes.index(event.fault_class)] = 1.0

    if event.fault_class is None:
        confidence = 0.0
    elif event.fault_confidence is not None:
        confidence = event.fault_confidence
    elif event.label_source in (LabelSource.DETERMINISTIC, LabelSource.INJECTOR):
        # Label injektor/deterministik diketahui pasti.
        confidence = 1.0
    else:
        confidence = 0.0

    patterns = list(OrchestrationPattern)
    onehot_pattern = np.zeros(len(patterns))
    onehot_pattern[patterns.index(event.orchestration)] = 1.0

    if event.step_total_estimate:
        rel_step = event.step_index / max(event.step_total_estimate, 1)
    else:
        rel_step = event.step_index / max(spec.step_cap, 1)

    prior = event.prior_incidents_in_task / max(spec.n_max, 1)
    budget = event.budget_remaining_cost / spec.budget_task_cap if spec.budget_task_cap > 0 else 0.0

    tail = [
        _clip01(confidence),
        *onehot_pattern,
        _clip01(rel_step),
        _clip01(prior),
        1.0 if event.checkpoint_restorable else 0.0,
        _clip01(budget),
    ]
    return np.concatenate([onehot_class, np.asarray(tail, dtype=float)])


def interaction_vector(event: FaultEvent, cand: Candidate, cosine: float) -> np.ndarray:
    cos01 = _clip01((cosine + 1.0) / 2.0)

    if cand.supported_classes is None:
        class_match = 1.0
    elif event.fault_class is None:
        class_match = 0.5
    else:
        class_match = 1.0 if event.fault_class in cand.supported_classes else 0.0

    if event.budget_remaining_cost <= 0:
        cost_ratio = 1.0
    else:
        cost_ratio = _clip01(cand.max_cost / event.budget_remaining_cost)

    if cand.optional_preconditions:
        met = sum(precondition_satisfied(p, event) for p in cand.optional_preconditions)
        completeness = met / len(cand.optional_preconditions)
    else:
        completeness = 1.0

    return np.array([cos01, class_match, cost_ratio, completeness], dtype=float)


def build_x(
    event: FaultEvent,
    cand: Candidate,
    cosine: float,
    spec: FeatureSpec,
    variant: FeatureVariant,
) -> np.ndarray:
    f = fault_vector(event, spec)
    g = interaction_vector(event, cand, cosine)
    if variant is FeatureVariant.NO_CANDIDATE:
        g = g[[2]]
    return np.concatenate([f, g, [1.0]])


def dimension(spec: FeatureSpec, variant: FeatureVariant) -> int:
    f_dim = len(FaultClass) + 1 + len(OrchestrationPattern) + 4
    g_dim = 4 if variant is FeatureVariant.FULL else 1
    return f_dim + g_dim + 1


def spec_hash(spec: FeatureSpec, variant: FeatureVariant, embedding_model_id: str) -> str:
    """Hash yang disimpan di policy dan audit. Mengikat juga urutan enum dan model
    embedding supaya policy menolak insiden yang fiturnya dibentuk berbeda."""
    payload = {
        "spec": asdict(spec),
        "variant": variant.value,
        "embedding_model": embedding_model_id,
        "fault_classes": [c.value for c in FaultClass],
        "patterns": [p.value for p in OrchestrationPattern],
    }
    raw = json.dumps(payload, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()
