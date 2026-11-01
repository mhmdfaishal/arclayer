"""Menegakkan arsitektur berlapis. Dependensi hanya boleh mengarah ke dalam:

    delivery (pemetaan kontrak, klien in-process) -> usecases -> domain
    infrastructure (DB, config, runtime)          -> usecases -> domain
    bootstrap (composition root)                  -> semua lapisan + apiclients
    api (kelas ArcLayer untuk pengguna library)   -> bootstrap, delivery, host, contracts
    apiclients (panggilan keluar ke model embedding) -> tidak ke mana-mana

`arclayer.contracts` dan `arclayer.host` adalah permukaan yang dilihat host: keduanya tidak
boleh mengimpor internal ArcLayer (domain, usecases, infrastructure).

Project ini hanya berisi lapisan kendali eksternal sebagai library. Host, harness eksperimen,
dan analisis ada di project terpisah (projects/evaluation) dan tidak boleh kembali ke sini.

Parser memakai AST, jadi impor di dalam fungsi (impor malas) dan `import x as y` ikut terperiksa.
Setiap berkas paket wajib tercakup satu aturan; package baru tanpa aturan membuat test gagal
supaya tidak lolos tanpa pagar.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

# libs/arclayer/tests/unit/test_architecture.py -> parents[2] = libs/arclayer, parents[4] = root repo
LIB = pathlib.Path(__file__).resolve().parents[2]
REPO = LIB.parents[1]
PACKAGE = LIB / "arclayer"
LOCAL_ROOTS = {"arclayer"}

# Bentuk akhir yang harus ada dan bentuk lama yang harus hilang (relatif ke root repo).
REQUIRED_PATHS = [
    "libs/arclayer/pyproject.toml",
    "libs/arclayer/configs/candidates/default.yaml",
    "libs/arclayer/tests/unit",
    "libs/arclayer/tests/unit/host",
    "libs/arclayer/arclayer/domain",
    "libs/arclayer/arclayer/usecases/incidents.py",
    "libs/arclayer/arclayer/usecases/candidates.py",
    "libs/arclayer/arclayer/usecases/policies.py",
    "libs/arclayer/arclayer/usecases/ports.py",
    "libs/arclayer/arclayer/usecases/errors.py",
    "libs/arclayer/arclayer/usecases/services",
    "libs/arclayer/arclayer/delivery/inprocess.py",
    "libs/arclayer/arclayer/delivery/mappers.py",
    "libs/arclayer/arclayer/infrastructure/persistence",
    "libs/arclayer/arclayer/infrastructure/config",
    "libs/arclayer/arclayer/infrastructure/runtime",
    "libs/arclayer/arclayer/apiclients/embedding/hashing.py",
    "libs/arclayer/arclayer/apiclients/embedding/sentence_transformer.py",
    "libs/arclayer/arclayer/contracts/schemas.py",
    "libs/arclayer/arclayer/host/protocols.py",
    "libs/arclayer/arclayer/host/runtime.py",
    "libs/arclayer/arclayer/bootstrap.py",
    "libs/arclayer/arclayer/api.py",
    "cookbook/README.md",
]
LEGACY_PATHS = [
    # susunan datar sebelum libs/
    "src", "configs", "tests", "pytest.ini", "requirements.txt",
    # nama lapis lama
    "libs/arclayer/arclayer/application",
    "libs/arclayer/arclayer/interfaces",
    "libs/arclayer/arclayer/infrastructure/embeddings",
    # dipindah ke projects/evaluation
    "libs/arclayer/arclayer/hosts", "libs/arclayer/arclayer/experiments", "libs/arclayer/arclayer/analysis",
    "libs/arclayer/arclayer/apiclients/llm", "libs/arclayer/arclayer/apiclients/controlplane.py",
    # nama pustaka sebelum arclayer
    "libs/rcl", "libs/rcl_contracts", "libs/rcl_sdk",
    # digabung ke satu pustaka
    "libs/arclayer_contracts", "libs/arclayer_sdk",
    # apiclients bagian dari paket arclayer, bukan paket tersendiri
    "libs/arclayer/apiclients",
    # keputusan 2026-11-01: library saja, tanpa lapisan HTTP, API key, atau entrypoint server
    "main.py",
    "libs/arclayer/arclayer/delivery/http",
    "libs/arclayer/arclayer/host/http_client.py",
    "libs/arclayer/tests/integration",
    "libs/arclayer/tests/system/test_http_synthetic_host.py",
    "libs/arclayer/tests/system/test_main_entrypoint.py",
]

# Paket lokal yang BOLEH diimpor, per area (awalan jalur berkas relatif ke libs/arclayer).
# Aturan paling spesifik menang.
LOCAL_ALLOWED: dict[str, set[str]] = {
    "arclayer/__init__.py": {"arclayer.api", "arclayer.host", "arclayer.contracts"},
    "arclayer/domain/": {"arclayer.domain"},
    "arclayer/usecases/": {"arclayer.domain", "arclayer.usecases"},
    "arclayer/infrastructure/config/": {
        "arclayer.domain", "arclayer.usecases", "arclayer.infrastructure", "arclayer.contracts",
    },
    "arclayer/infrastructure/": {"arclayer.domain", "arclayer.usecases", "arclayer.infrastructure"},
    "arclayer/delivery/": {
        "arclayer.domain", "arclayer.usecases", "arclayer.delivery", "arclayer.bootstrap", "arclayer.contracts",
    },
    "arclayer/apiclients/": {"arclayer.apiclients"},
    "arclayer/bootstrap.py": {
        "arclayer.domain", "arclayer.usecases", "arclayer.infrastructure", "arclayer.bootstrap", "arclayer.apiclients",
    },
    "arclayer/contracts/": {"arclayer.contracts"},
    "arclayer/host/": {"arclayer.host", "arclayer.contracts"},
    "arclayer/api.py": {
        "arclayer.api", "arclayer.bootstrap", "arclayer.contracts", "arclayer.delivery", "arclayer.host",
        "arclayer.usecases.errors", "arclayer.domain.errors",
    },
}

# Pustaka pihak ketiga yang hanya boleh muncul di area tertentu (awalan jalur berkas).
CONFINED: dict[str, tuple[str, ...]] = {
    # semua panggilan keluar ke aplikasi/model eksternal hidup di arclayer/apiclients
    "httpx": ("arclayer/apiclients/",),
    "requests": ("arclayer/apiclients/",),
    "aiohttp": ("arclayer/apiclients/",),
    "urllib3": ("arclayer/apiclients/",),
    "google": ("arclayer/apiclients/",),
    "openai": ("arclayer/apiclients/",),
    "anthropic": ("arclayer/apiclients/",),
    "sentence_transformers": ("arclayer/apiclients/",),
    "torch": ("arclayer/apiclients/",),
    "transformers": ("arclayer/apiclients/",),
    # tanpa web framework di mana pun: ArcLayer adalah library yang dipanggil langsung oleh host
    "fastapi": (),
    "starlette": (),
    "uvicorn": (),
    "pydantic_settings": (),
    "sqlalchemy": ("arclayer/infrastructure/persistence/",),
    # lapisan inti bebas dari kerangka validasi
    "pydantic": ("arclayer/contracts/", "arclayer/delivery/", "arclayer/infrastructure/config/"),
}


def _src_files() -> list[pathlib.Path]:
    return sorted(p for p in PACKAGE.rglob("*.py") if "__pycache__" not in p.parts)


def _rel(p: pathlib.Path) -> str:
    return p.relative_to(LIB).as_posix()


def _imports(path: pathlib.Path) -> list[tuple[str, int]]:
    """(modul absolut, nomor baris) untuk setiap impor, termasuk yang ada di dalam fungsi.
    Impor relatif di-resolve ke nama absolut supaya tidak lolos dari aturan lapisan."""
    pkg = path.relative_to(LIB).with_suffix("").parts[:-1]  # paket tempat berkas berada
    out: list[tuple[str, int]] = []
    for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(n, ast.Import):
            out += [(a.name, n.lineno) for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            base = list(pkg[: len(pkg) - (n.level - 1)]) if n.level else []
            out.append((".".join(base + ([n.module] if n.module else [])), n.lineno))
    return out


def _matches(mod: str, allowed: set[str]) -> bool:
    return any(mod == a or mod.startswith(a + ".") for a in allowed)


def _rule_for(rel: str) -> tuple[str, set[str]] | None:
    best = None
    for prefix, allowed in LOCAL_ALLOWED.items():
        if (rel == prefix or rel.startswith(prefix)) and (best is None or len(prefix) > len(best[0])):
            best = (prefix, allowed)
    return best


@pytest.mark.parametrize("rel", REQUIRED_PATHS)
def test_target_layout_exists(rel):
    assert (REPO / rel).exists(), f"{rel} belum ada"


@pytest.mark.parametrize("rel", LEGACY_PATHS)
def test_legacy_layout_is_gone(rel):
    assert not (REPO / rel).exists(), f"{rel} seharusnya sudah dipindah"


def test_every_source_file_is_covered_by_a_rule():
    uncovered = [_rel(f) for f in _src_files() if _rule_for(_rel(f)) is None]
    assert uncovered == []


def test_local_imports_follow_the_dependency_rule():
    offenders = []
    for f in _src_files():
        rule = _rule_for(_rel(f))
        if rule is None:
            continue
        area, allowed = rule
        for mod, ln in _imports(f):
            if mod.split(".")[0] in LOCAL_ROOTS and not _matches(mod, allowed):
                offenders.append(f"{_rel(f)}:{ln} [{area}] -> {mod}")
    assert offenders == []


def test_third_party_libraries_stay_in_their_layer():
    offenders = []
    for f in _src_files():
        rel = _rel(f)
        for mod, ln in _imports(f):
            top = mod.split(".")[0]
            if top in CONFINED and not rel.startswith(CONFINED[top]):
                offenders.append(f"{rel}:{ln} -> {mod}  (hanya boleh di {', '.join(CONFINED[top])})")
    assert offenders == []
