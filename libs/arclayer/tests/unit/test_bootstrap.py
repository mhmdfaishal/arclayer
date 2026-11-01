"""Composition root: satu-satunya tempat yang merangkai use case dengan adapter konkret."""

import pathlib

import pytest

from arclayer.bootstrap import (
    build_inmemory_control_plane,
    build_sql_services,
    make_embedder,
    seed_candidates,
)
from tests.factories import table6_candidates

CANDIDATES_YAML = pathlib.Path(__file__).resolve().parents[2] / "configs" / "candidates" / "default.yaml"


# ---------- make_embedder ----------

def test_make_embedder_hashing_uses_the_default_dimension():
    assert make_embedder("hashing").model_id == "hashing-384"


def test_make_embedder_rejects_unknown_spec():
    with pytest.raises(ValueError, match="embedding tidak dikenal"):
        make_embedder("word2vec")
    with pytest.raises(ValueError, match="embedding tidak dikenal"):
        make_embedder("st:")  # nama model kosong


def test_make_embedder_st_builds_the_sentence_transformer_provider(monkeypatch):
    from arclayer.apiclients.embedding import sentence_transformer as st_mod

    class _Fake:
        def __init__(self, model: str) -> None:
            self.model = model

    monkeypatch.setattr(st_mod, "SentenceTransformerEmbeddingProvider", _Fake)
    assert make_embedder("st:org/model").model == "org/model"


# ---------- build_inmemory_control_plane ----------

def test_inmemory_control_plane_records_audit_of_what_the_services_do():
    cp = build_inmemory_control_plane(embedding_dim=64)
    assert cp.services.list_candidates.execute() == []
    assert cp.store.audit_records == []
    cp.services.register_candidate.execute(table6_candidates()[0])
    assert len(cp.services.list_candidates.execute()) == 1
    assert len(cp.store.audit_records) > 0


def test_inmemory_control_planes_are_isolated_from_each_other():
    a, b = build_inmemory_control_plane(), build_inmemory_control_plane()
    a.services.register_candidate.execute(table6_candidates()[0])
    assert b.services.list_candidates.execute() == []


# ---------- seed_candidates ----------

def test_seed_candidates_loads_the_yaml_once():
    svc = build_inmemory_control_plane().services
    seed_candidates(svc, CANDIDATES_YAML)
    n = len(svc.list_candidates.execute())
    assert n == 6
    seed_candidates(svc, CANDIDATES_YAML)  # restart pada registri terisi tidak boleh menggandakan
    assert len(svc.list_candidates.execute()) == n


# ---------- build_sql_services ----------

def test_sql_services_persist_across_instances(tmp_path):
    url = f"sqlite:///{tmp_path / 'arclayer.db'}"
    first = build_sql_services(url, embedding="hashing", censor_ttl_s=3600)
    first.register_candidate.execute(table6_candidates()[0])
    second = build_sql_services(url, embedding="hashing", censor_ttl_s=3600)
    assert len(second.list_candidates.execute()) == 1
