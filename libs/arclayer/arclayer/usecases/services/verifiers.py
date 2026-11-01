"""Registri verifier keberhasilan (komponen S_t). Biaya, latensi, dan pelanggaran
dihitung terpisah oleh domain.verification.

`llm_judge` sengaja tidak diimplementasikan di sini: usulan hanya memakainya sebagai
analisis sensitivitas, bukan sumber reward jalur utama.
"""

from __future__ import annotations

from typing import Callable

from arclayer.domain.answer_matching import answers_match
from arclayer.domain.enums import Terminal
from arclayer.domain.models import ExecutionResult

SuccessVerifier = Callable[[ExecutionResult, str | None], bool]


def benchmark_task_pass(result: ExecutionResult, truth: str | None) -> bool:
    # Tanpa ground truth, keberhasilan tidak bisa diklaim (lebih aman gagal).
    if truth is None or result.terminal is not Terminal.TASK_COMPLETED:
        return False
    return answers_match(result.final_answer, truth)


def task_completed(result: ExecutionResult, truth: str | None) -> bool:
    """Verifier lokal tanpa ground truth: sukses bila rollout selesai tanpa error."""
    return result.terminal is Terminal.TASK_COMPLETED


DEFAULT_VERIFIERS: dict[str, SuccessVerifier] = {
    "benchmark_task_pass": benchmark_task_pass,
    "task_completed": task_completed,
}
