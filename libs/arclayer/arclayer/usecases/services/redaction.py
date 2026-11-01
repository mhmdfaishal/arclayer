"""Redaksi data sensitif sebelum embedding, penyimpanan, dan audit.

Urutan pola penting: pola yang lebih spesifik (API key bertipe) dijalankan sebelum pola
umum. Penanda keluaran `[REDACTED:<tipe>]` sengaja tidak cocok dengan pola mana pun
sehingga redaksi idempoten.
"""

from __future__ import annotations

import re
from dataclasses import replace

from arclayer.domain.models import FaultEvent

# Grup bernama `keep` (opsional) adalah prefiks yang dipertahankan; sisanya diganti.
# Dipakai alih-alih look-behind karena look-behind Python wajib lebar tetap.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("api_key", re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("bearer", re.compile(r"(?i)(?P<keep>bearer )[A-Za-z0-9._\-~+/=]{8,}")),
    ("url_secret", re.compile(r"(?i)(?P<keep>[?&](?:token|key|apikey|api_key|secret|password|sig)=)[^&\s#]+")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    ("home_path", re.compile(r"(?:/Users|/home)/[^/\s]+")),
]


def redact(text: str) -> str:
    for name, pat in _PATTERNS:
        marker = f"[REDACTED:{name}]"
        text = pat.sub(lambda m, mk=marker: (m.groupdict().get("keep") or "") + mk, text)
    return text


def redact_event(event: FaultEvent, max_len: int = 4000) -> FaultEvent:
    # Truncation deterministik (potong di akhir), bukan acak, agar replay identik.
    return replace(
        event,
        fault_description=redact(event.fault_description)[:max_len],
        last_messages_summary=redact(event.last_messages_summary)[:max_len],
        available_artifacts=tuple(redact(a) for a in event.available_artifacts),
    )
