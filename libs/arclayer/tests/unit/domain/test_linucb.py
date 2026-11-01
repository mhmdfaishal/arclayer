import numpy as np
import pytest

from arclayer.domain.models import ArmFeatures
from arclayer.domain.policies.linucb import DisjointLinUCB
from tests.factories import make_event

IDS = ("a", "b", "c")


def _arms(xs: dict[str, np.ndarray]):
    return tuple(ArmFeatures(candidate_id=k, x=tuple(v), cosine=0.0) for k, v in xs.items())


def test_init_A_is_lambda_I_and_b_is_zero():
    pol = DisjointLinUCB(IDS, d=4, alpha=0.5, lam=0.45)
    st_ = pol.export_state()
    for h in IDS:
        assert np.allclose(np.array(st_["A"][h]), 0.45 * np.eye(4))
        assert np.allclose(np.array(st_["b"][h]), 0.0)


def test_score_matches_closed_form_with_explicit_inverse():
    rng = np.random.default_rng(0)
    pol = DisjointLinUCB(IDS, d=4, alpha=0.7, lam=0.45)
    for _ in range(10):
        x = rng.random(4)
        pol.update("a", x, float(rng.random()))
    x = rng.random(4)
    est, bonus, score = pol.score("a", x)
    A = np.array(pol.export_state()["A"]["a"])
    b = np.array(pol.export_state()["b"]["a"])
    A_inv = np.linalg.inv(A)
    theta = A_inv @ b
    assert est == pytest.approx(theta @ x)
    assert bonus == pytest.approx(0.7 * np.sqrt(x @ A_inv @ x))
    assert score == pytest.approx(est + bonus)


def test_only_chosen_arm_is_updated():
    pol = DisjointLinUCB(IDS, d=3, alpha=0.5, lam=1.0)
    before = pol.export_state()
    pol.update("b", np.array([1.0, 0.5, 1.0]), 1.0)
    after = pol.export_state()
    assert after["A"]["a"] == before["A"]["a"] and after["A"]["c"] == before["A"]["c"]
    assert after["b"]["a"] == before["b"]["a"]
    assert after["A"]["b"] != before["A"]["b"]
    assert after["n"]["b"] == 1


def test_bonus_shrinks_after_repeated_same_context():
    pol = DisjointLinUCB(IDS, d=3, alpha=1.0, lam=1.0)
    x = np.array([1.0, 0.0, 1.0])
    _, b0, _ = pol.score("a", x)
    for _ in range(5):
        pol.update("a", x, 0.0)
    _, b1, _ = pol.score("a", x)
    assert b1 < b0


def test_select_returns_argmax_with_score_breakdown():
    pol = DisjointLinUCB(IDS, d=2, alpha=0.0, lam=1.0)
    for _ in range(5):
        pol.update("b", np.array([1.0, 1.0]), 1.0)
    rng = np.random.default_rng(1)
    sel = pol.select(_arms({h: np.array([1.0, 1.0]) for h in IDS}), make_event(), rng)
    assert sel.candidate_id == "b"
    assert {s.candidate_id for s in sel.scores} == set(IDS)


def test_tie_break_is_seeded_and_not_always_first():
    arms = _arms({h: np.array([1.0, 1.0]) for h in IDS})
    picks = {DisjointLinUCB(IDS, 2, 0.5, 1.0).select(arms, make_event(), np.random.default_rng(s)).candidate_id for s in range(30)}
    assert len(picks) > 1
    a = DisjointLinUCB(IDS, 2, 0.5, 1.0).select(arms, make_event(), np.random.default_rng(7)).candidate_id
    b = DisjointLinUCB(IDS, 2, 0.5, 1.0).select(arms, make_event(), np.random.default_rng(7)).candidate_id
    assert a == b


def test_select_only_among_given_arms():
    pol = DisjointLinUCB(IDS, d=2, alpha=0.5, lam=1.0)
    for _ in range(10):
        pol.update("a", np.array([1.0, 1.0]), 1.0)
    sel = pol.select(_arms({"c": np.array([1.0, 1.0])}), make_event(), np.random.default_rng(0))
    assert sel.candidate_id == "c"


def test_frozen_policy_ignores_update():
    pol = DisjointLinUCB(IDS, d=2, alpha=0.5, lam=1.0, frozen=True)
    before = pol.export_state()
    assert pol.update("a", np.array([1.0, 1.0]), 1.0) is False
    assert pol.export_state() == before


def test_state_roundtrip_is_exact():
    rng = np.random.default_rng(3)
    pol = DisjointLinUCB(IDS, d=3, alpha=0.5, lam=0.45)
    for _ in range(20):
        pol.update(IDS[rng.integers(3)], rng.random(3), float(rng.normal()))
    clone = DisjointLinUCB.from_state(pol.export_state())
    x = rng.random(3)
    for h in IDS:
        assert clone.score(h, x) == pol.score(h, x)


def test_from_state_rejects_dimension_mismatch():
    state = DisjointLinUCB(IDS, d=3, alpha=0.5, lam=1.0).export_state()
    with pytest.raises(ValueError):
        DisjointLinUCB.from_state(state, expected_d=4)


def _linear_bandit(seed: int, T: int) -> tuple[float, float, float]:
    """Kembalikan (reward LinUCB, reward acak, proporsi pilihan optimal pada 200 langkah terakhir)."""
    rng = np.random.default_rng(seed)
    d = 5
    theta = {h: rng.normal(size=d) for h in IDS}
    pol = DisjointLinUCB(IDS, d=d, alpha=0.5, lam=1.0)
    pol_rng = np.random.default_rng(seed + 1)
    lin, rnd, optimal = 0.0, 0.0, []
    for _ in range(T):
        x = rng.random(d)
        mean = {h: float(theta[h] @ x) for h in IDS}
        sel = pol.select(_arms({h: x for h in IDS}), make_event(), pol_rng)
        pol.update(sel.candidate_id, x, mean[sel.candidate_id] + rng.normal(scale=0.1))
        lin += mean[sel.candidate_id]
        rnd += mean[IDS[rng.integers(3)]]
        optimal.append(sel.candidate_id == max(mean, key=mean.get))
    return lin, rnd, float(np.mean(optimal[-200:]))


def test_learns_better_than_random_on_linear_bandit():
    """Sanity, bukan bukti tesis. Klaim 'selalu menang untuk setiap seed pada horizon
    tetap' TIDAK benar secara teori (hypothesis menemukan seed 1605: LinUCB sempat terkunci
    pada arm suboptimal karena skala reward >> bonus alpha), jadi yang diuji adalah klaim
    statistik pada himpunan seed tetap."""
    runs = [_linear_bandit(s, 600) for s in range(30)]
    assert np.mean([lin > rnd for lin, rnd, _ in runs]) >= 0.9
    assert np.mean([opt for *_, opt in runs]) > 0.8


def test_hard_instance_eventually_converges():
    # Seed 1605: kalah dari acak pada T=600, tetapi pada horizon lebih panjang LinUCB
    # keluar dari arm suboptimal. Memastikan kegagalan awal itu bukan bug pembaruan.
    lin, rnd, opt = _linear_bandit(1605, 3000)
    assert lin > rnd and opt > 0.9
