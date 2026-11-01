"""Dunia sintetis: insiden acak ber-seed dan model keberhasilan tersembunyi.

BUKAN bukti tesis (Subbab 8.1): hanya sanity check bahwa pipa end-to-end berjalan dan
LinUCB bisa belajar sebelum menghabiskan biaya LLM.

Model tersembunyi: P(sukses | insiden, h) = sigmoid(theta_h . z), z = [one-hot kelas (6),
one-hot orkestrasi (4), checkpoint dapat dipulihkan, bias]. Theta disusun dari tiga tabel
logit (kelas, orkestrasi, checkpoint) supaya mudah dibaca dan di-tuning. Peta statis B2
sengaja tidak optimal: kandidat terbaik berubah menurut pola orkestrasi dan ketersediaan
checkpoint (mis. plan_error: h6 unggul di sequential/decentralized, h3 di centralized).
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np

from tests.support.synthetic_host.candidates import synthetic_candidates
from arclayer.contracts import FaultClass, OrchestrationPattern

CANDIDATE_IDS = (
    "h1_retry", "h2_tool_repair", "h3_replanner", "h4_handoff_completer",
    "h5_verification_reviewer", "h6_guided_rollback",
)
CLASSES = list(FaultClass)
ORCHS = list(OrchestrationPattern)
_Z_DIM = len(CLASSES) + len(ORCHS) + 2
_BASE_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)
_SPECS = {s.candidate_id: s for s in synthetic_candidates()}

# Urutan kelas: tool_failure, timeout, tool_output_unused, handoff_incomplete, plan_error,
# insufficient_verification. Urutan orkestrasi: centralized, sequential, concurrent, decentralized.
# Nilai berupa logit (0.0 = 50%, 0.85 = 70%, 1.4 = 80%, -1.4 = 20%).
_CLASS_LOGIT = {
    "h1_retry": [-0.7, -0.1, -1.3, -1.2, -1.5, -1.2],
    "h2_tool_repair": [0.8, 0.5, -2.0, -2.0, -2.0, -2.0],
    "h3_replanner": [-2.2, -2.2, -2.0, -2.0, 0.4, -2.2],
    "h4_handoff_completer": [-1.8, -1.8, 0.0, 0.3, -1.6, -1.2],
    "h5_verification_reviewer": [-2.0, -2.0, -1.8, -1.8, -1.8, 0.7],
    # Tanpa bonus checkpoint; bonus ada di _CKPT_LOGIT. h6 hanya lolos gate bila
    # checkpoint ada, jadi efektifnya konstanta per kelas.
    "h6_guided_rollback": [-1.8, -1.8, -0.6, -0.4, -0.6, -0.6],
}
_ORCH_LOGIT = {
    "h1_retry": [0.0, 0.0, 0.3, 0.8],
    "h2_tool_repair": [0.3, 0.0, 0.0, -1.2],
    "h3_replanner": [0.9, -1.4, 0.2, -1.0],
    "h4_handoff_completer": [0.4, 0.0, -0.3, -0.2],
    "h5_verification_reviewer": [0.0, 0.0, 0.3, -0.4],
    "h6_guided_rollback": [-0.2, 0.7, 0.0, 0.5],
}
_CKPT_LOGIT = {
    "h1_retry": 0.0, "h2_tool_repair": 0.0, "h3_replanner": 0.0, "h4_handoff_completer": 0.0,
    "h5_verification_reviewer": 0.0, "h6_guided_rollback": 1.0,
}
_BIAS = {h: 0.0 for h in CANDIDATE_IDS}


def _z(fault_class: FaultClass, orch: OrchestrationPattern, ckpt: bool) -> np.ndarray:
    z = np.zeros(_Z_DIM)
    z[CLASSES.index(fault_class)] = 1.0
    z[len(CLASSES) + ORCHS.index(orch)] = 1.0
    z[-2] = 1.0 if ckpt else 0.0
    z[-1] = 1.0
    return z


def _theta(h: str) -> np.ndarray:
    return np.array([*_CLASS_LOGIT[h], *_ORCH_LOGIT[h], _CKPT_LOGIT[h], _BIAS[h]])


THETA = {h: _theta(h) for h in CANDIDATE_IDS}


def success_probability_for(fault_class: FaultClass, orch: OrchestrationPattern, ckpt: bool, h: str) -> float:
    return 1.0 / (1.0 + math.exp(-float(THETA[h] @ _z(fault_class, orch, ckpt))))


# Deskripsi fault: kata kunci kelas muncul secara alami, tetapi sebagian varian membawa
# kosakata kelas lain (distraktor) supaya kesamaan kosinus informatif namun tidak sempurna.
_DESCRIPTIONS = {
    FaultClass.TOOL_FAILURE: [
        "Pemanggilan tool gagal dengan error dan argumen tool tampaknya salah sehingga hasil tidak keluar",
        "Tool mengembalikan galat saat dipanggil, agen tidak mendapat hasil dari tool tersebut",
        "Eksekusi tool berhenti dengan kode error, perlu argumen lain atau tool alternatif",
    ],
    FaultClass.TIMEOUT: [
        "Langkah gagal karena timeout, tool tidak menjawab dalam batas waktu yang ditetapkan",
        "Terjadi timeout pada pemanggilan, langkah tertahan dan tidak pernah selesai",
        "Batas waktu terlewati (timeout) sehingga langkah agen dihentikan paksa",
    ],
    FaultClass.TOOL_OUTPUT_UNUSED: [
        "Keluaran tool tidak dipakai oleh agen berikutnya, konteks hasil tool hilang dari pesan",
        "Agen mengabaikan keluaran tool sehingga informasi penting tidak sampai ke langkah lanjutan",
        "Hasil tool sudah tersedia tetapi keluaran itu tidak dimanfaatkan dalam pesan berikutnya",
    ],
    FaultClass.HANDOFF_INCOMPLETE: [
        "Serah terima ke agen berikutnya tidak lengkap, konteks yang hilang membuat pesan tidak utuh",
        "Pesan serah terima antar agen terpotong dan kehilangan konteks yang dibutuhkan",
        "Serah terima ke agen lain tidak lengkap, sebagian state tidak ikut dikirim",
    ],
    FaultClass.PLAN_ERROR: [
        "Rencana orchestrator keliru, langkah rencana tidak sesuai tujuan tugas dan perlu diperbarui",
        "Rencana yang disusun salah arah sehingga agen mengerjakan langkah yang tidak relevan",
        "Terjadi kesalahan pada rencana tugas, urutan langkah dalam rencana tidak masuk akal",
    ],
    FaultClass.INSUFFICIENT_VERIFICATION: [
        "Jawaban diserahkan tanpa bukti yang cukup, pemeriksaan jawaban kurang sebelum diserahkan",
        "Verifikasi tidak memadai: jawaban akhir belum didukung bukti yang bisa diperiksa",
        "Agen menyerahkan jawaban tanpa memeriksa bukti, verifikasi hasil terlewat",
    ],
}
_DISTRACTORS = [
    "Ada juga indikasi masalah pada rencana", "Sebelumnya tool sempat lambat", "Konteks pesan terakhir sedikit janggal",
    "Jawaban sementara belum diperiksa", "Langkah sebelumnya sempat dijalankan ulang",
]
_SUMMARIES = [
    "orchestrator meminta agen mengerjakan sub-tugas lalu menunggu hasil",
    "agen terakhir melaporkan progres sebagian dan menunggu langkah berikutnya",
    "pesan terakhir berisi ringkasan hasil pencarian dan rencana lanjutan",
]
_TOOLS = ["web_search", "python_exec", "file_reader", "calculator"]
_ARTIFACTS = ["page.html", "search.json", "trace.log"]
_ERROR_CODES = {FaultClass.TOOL_FAILURE: ["HTTP_500", "BAD_ARGS", "TOOL_CRASH"], FaultClass.TIMEOUT: ["TIMEOUT"]}
_ORCH_ACCESS = {  # peluang orchestrator dapat diakses (prasyarat h3)
    OrchestrationPattern.CENTRALIZED: 1.0, OrchestrationPattern.SEQUENTIAL: 0.7,
    OrchestrationPattern.CONCURRENT: 0.8, OrchestrationPattern.DECENTRALIZED: 0.4,
}


@dataclass(frozen=True)
class SyntheticIncident:
    task_id: str
    index: int
    fault_class: FaultClass
    orchestration: OrchestrationPattern
    checkpoint_id: str | None
    checkpoint_restorable: bool
    step_repeatable: bool
    orchestrator_accessible: bool
    available_artifacts: tuple[str, ...]
    tool_name: str | None
    tool_error_code: str | None
    tool_duration_ms: int | None
    budget_remaining_cost: float
    time_remaining_ms: int
    fault_description: str
    last_messages_summary: str
    step_index: int
    step_total_estimate: int
    occurred_at: datetime


@dataclass(frozen=True)
class Draw:
    success: bool
    cost: float
    latency_ms: int


def _stable_rng(*parts: object) -> random.Random:
    # hashlib, bukan hash(): hash() str diacak per proses (PYTHONHASHSEED) dan akan
    # merusak determinisme lintas run dan lintas mode (online vs outcome matrix).
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


class SyntheticWorld:
    def __init__(self, seed: int, n_tasks: int) -> None:
        self.seed = seed
        self.n_tasks = n_tasks
        rng = random.Random(seed)
        self.incidents: list[SyntheticIncident] = [self._make(rng, i) for i in range(n_tasks)]
        self.oracle: dict[str, str] = {i.task_id: "PASS" for i in self.incidents}

    @staticmethod
    def _make(rng: random.Random, i: int) -> SyntheticIncident:
        fc = rng.choice(CLASSES)
        orch = rng.choice(ORCHS)
        restorable = rng.random() < 0.6
        # checkpoint ada tetapi tidak dapat dipulihkan (10%): gate harus tetap menolak h6.
        has_ckpt_id = restorable or rng.random() < 0.1
        tool_class = fc in (FaultClass.TOOL_FAILURE, FaultClass.TIMEOUT)
        with_tool = tool_class or fc is FaultClass.TOOL_OUTPUT_UNUSED or rng.random() < 0.3
        tool_name = rng.choice(_TOOLS) if with_tool else None
        error = rng.choice(_ERROR_CODES[fc]) if tool_class else None
        desc = rng.choice(_DESCRIPTIONS[fc])
        if rng.random() < 0.25:
            desc += ". " + rng.choice(_DISTRACTORS)
        step = rng.randint(1, 12)
        return SyntheticIncident(
            task_id=f"task-{i:05d}",
            index=i,
            fault_class=fc,
            orchestration=orch,
            checkpoint_id=f"ckpt-{i:05d}" if has_ckpt_id else None,
            checkpoint_restorable=restorable,
            step_repeatable=rng.random() < (0.6 if fc is FaultClass.PLAN_ERROR else 0.85),
            orchestrator_accessible=rng.random() < _ORCH_ACCESS[orch],
            available_artifacts=tuple(a for a in _ARTIFACTS if rng.random() < 0.5),
            tool_name=tool_name,
            tool_error_code=error,
            tool_duration_ms=rng.randint(100, 30_000) if tool_name else None,
            budget_remaining_cost=round(rng.uniform(1.0, 3.0), 2),
            time_remaining_ms=rng.randint(600_000, 1_800_000),
            fault_description=desc,
            # 10% ringkasan kosong: STATE_SUMMARY_AVAILABLE gagal sehingga h4 tersaring gate.
            last_messages_summary="" if rng.random() < 0.1 else rng.choice(_SUMMARIES),
            step_index=step,
            step_total_estimate=step + rng.randint(1, 8),
            occurred_at=_BASE_TIME + timedelta(seconds=i),
        )

    def success_prob(self, inc: SyntheticIncident, candidate_id: str) -> float:
        return success_probability_for(inc.fault_class, inc.orchestration, inc.checkpoint_restorable, candidate_id)

    def draw(self, inc: SyntheticIncident, candidate_id: str) -> Draw:
        """Hasil eksekusi (insiden, kandidat) yang deterministik: RNG hanya bergantung
        pada (seed dunia, task_id, kandidat), bukan pada riwayat kebijakan."""
        rng = _stable_rng(self.seed, inc.task_id, candidate_id)
        success = rng.random() < self.success_prob(inc, candidate_id)
        spec = _SPECS[candidate_id]
        cost = round(spec.max_cost * rng.uniform(0.4, 0.95), 4)
        latency = max(1, int(spec.max_latency_ms * rng.uniform(0.2, 0.8)))
        return Draw(success, cost, latency)
