"""Pencocokan jawaban gaya GAIA (quasi exact match).

Ini aproksimasi dari scorer resmi GAIA, ditulis dari ingatan dan belum diverifikasi
baris per baris terhadap kode resmi. Sebelum eksperimen utama, bandingkan dengan
scorer resmi pada jawaban validasi dan ganti bila ada perbedaan.
"""

from __future__ import annotations

import re
import string

_LIST_SPLIT = re.compile(r"[,;]")


def _as_number(s: str) -> float | None:
    cleaned = s.replace("$", "").replace("%", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _normalize_text(s: str) -> str:
    s = s.lower().strip()
    s = s.translate(str.maketrans("", "", string.punctuation))
    return " ".join(s.split())


def _match_scalar(pred: str, truth: str) -> bool:
    t_num = _as_number(truth)
    if t_num is not None:
        p_num = _as_number(pred)
        return p_num is not None and p_num == t_num
    return _normalize_text(pred) == _normalize_text(truth)


def answers_match(pred: str | None, truth: str) -> bool:
    if pred is None:
        return False
    if _LIST_SPLIT.search(truth):
        p_items = [x.strip() for x in _LIST_SPLIT.split(pred)]
        t_items = [x.strip() for x in _LIST_SPLIT.split(truth)]
        # Urutan elemen daftar dianggap bermakna, mengikuti GAIA.
        return len(p_items) == len(t_items) and all(_match_scalar(p, t) for p, t in zip(p_items, t_items))
    return _match_scalar(pred, truth)
