import numpy as np
import pytest

from arclayer.usecases.services.redaction import redact
from arclayer.apiclients.embedding.hashing import HashingEmbeddingProvider


@pytest.mark.parametrize(
    "text,secret",
    [
        ("Authorization: Bearer abc.def.ghi123456", "abc.def.ghi123456"),
        ("key sk-ant-api03-AAAAAAAAAAAAAAAAAAAA", "sk-ant-api03-AAAAAAAAAAAAAAAAAAAA"),
        ("openai sk-proj-ABCDEFGHIJKLMNOPQRST", "sk-proj-ABCDEFGHIJKLMNOPQRST"),
        ("mail me at faishal@example.com", "faishal@example.com"),
        ("GET https://x.io/api?token=s3cr3t&q=1", "s3cr3t"),
        ("file /Users/mhmdfaishal/secret.txt", "/Users/mhmdfaishal"),
        ("aws AKIAABCDEFGHIJKLMNOP", "AKIAABCDEFGHIJKLMNOP"),
    ],
)
def test_redacts_secrets(text, secret):
    out = redact(text)
    assert secret not in out
    assert "[REDACTED:" in out


def test_redaction_is_idempotent_and_keeps_plain_text():
    t = "search tool returned HTTP 500 for query 'gaia'"
    assert redact(t) == t
    s = redact("Bearer abcdefghijklmnop1234")
    assert redact(s) == s


def test_hashing_embedder_is_deterministic_and_normalized():
    e = HashingEmbeddingProvider(dim=64)
    a = e.embed(["tool failed with timeout", "tool failed with timeout"])
    assert a.shape == (2, 64)
    assert np.allclose(a[0], a[1])
    assert np.isclose(np.linalg.norm(a[0]), 1.0)
    assert e.model_id == "hashing-64"


def test_hashing_embedder_similarity_reflects_token_overlap():
    e = HashingEmbeddingProvider(dim=256)
    v = e.embed(["retry failed tool step", "retry the failed tool step", "update orchestrator plan"])
    assert v[0] @ v[1] > v[0] @ v[2]
