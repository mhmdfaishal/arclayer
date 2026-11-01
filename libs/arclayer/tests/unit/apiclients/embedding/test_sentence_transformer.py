from __future__ import annotations

import numpy as np
import pytest

from arclayer.apiclients.embedding import sentence_transformer as st_mod
from arclayer.apiclients.embedding.sentence_transformer import SentenceTransformerEmbeddingProvider


class FakeModel:
    """Model palsu: vektor dari panjang teks, sengaja TIDAK ternormalisasi."""

    def __init__(self):
        self.calls: list[list[str]] = []

    def encode(self, texts, **kw):
        self.calls.append(list(texts))
        return np.array([[float(len(t)), 3.0, 4.0] for t in texts])


@pytest.fixture
def fake(monkeypatch):
    m = FakeModel()
    loads = []

    def loader(name, device):
        loads.append((name, device))
        return m

    monkeypatch.setattr(st_mod, "_load_model", loader)
    return m, loads


def test_model_id_and_default_name():
    p = SentenceTransformerEmbeddingProvider()
    assert p.model_id == "st:sentence-transformers/all-MiniLM-L6-v2"
    assert SentenceTransformerEmbeddingProvider("foo/bar").model_id == "st:foo/bar"


def test_lazy_load_on_first_embed_only(fake):
    m, loads = fake
    p = SentenceTransformerEmbeddingProvider(device="cpu")
    assert loads == []
    p.embed(["a"])
    p.embed(["b"])
    assert loads == [("sentence-transformers/all-MiniLM-L6-v2", "cpu")]


def test_rows_are_l2_normalized(fake):
    p = SentenceTransformerEmbeddingProvider()
    out = p.embed(["abc", "defgh"])
    assert out.shape == (2, 3)
    assert np.allclose(np.linalg.norm(out, axis=1), 1.0)


def test_cache_avoids_reencoding_and_keeps_order(fake):
    m, _ = fake
    p = SentenceTransformerEmbeddingProvider()
    first = p.embed(["aa", "b"])
    second = p.embed(["b", "cccc", "aa", "b"])
    assert m.calls == [["aa", "b"], ["cccc"]]  # hanya teks baru yang di-encode, tanpa duplikat
    assert np.array_equal(second[0], first[1]) and np.array_equal(second[2], first[0])
    assert np.array_equal(second[3], first[1])


def test_returned_array_is_not_a_view_of_cache(fake):
    p = SentenceTransformerEmbeddingProvider()
    a = p.embed(["x"])
    a[:] = 0
    assert np.linalg.norm(p.embed(["x"])) == pytest.approx(1.0)


def test_zero_vector_does_not_divide_by_zero(monkeypatch):
    class Zero:
        def encode(self, texts, **kw):
            return np.zeros((len(texts), 3))

    monkeypatch.setattr(st_mod, "_load_model", lambda n, d: Zero())
    out = SentenceTransformerEmbeddingProvider().embed(["x"])
    assert np.all(out == 0) and not np.isnan(out).any()


def test_empty_input(fake):
    out = SentenceTransformerEmbeddingProvider().embed([])
    assert out.shape[0] == 0


@pytest.mark.slow
def test_real_model_semantic_sanity():
    try:
        p = SentenceTransformerEmbeddingProvider()
        v = p.embed(["the tool returned an error", "tool failure error", "banana smoothie recipe"])
    except Exception as e:  # noqa: BLE001 - model tidak tersedia offline
        pytest.skip(f"model nyata tidak dapat dimuat: {e}")
    assert v.shape == (3, 384)
    assert np.allclose(np.linalg.norm(v, axis=1), 1.0, atol=1e-5)
    assert v[0] @ v[1] > v[0] @ v[2]
