"""Kriteria penerimaan Subbab 8.1: pada host sintetis LinUCB harus mengungguli B1, B2, B3
secara rata-rata antar seed. Kegagalan di sini berarti ada bug sebelum host nyata."""

from __future__ import annotations

from statistics import mean

import pytest

from tests.support.synthetic_host import SyntheticWorld
from tests.support.synthetic_run import run_policy, split_calibration

SEEDS = (11, 23, 37)
KINDS = ("B1", "B2", "B3", "P")


def _evaluate(kind: str, seed: int, world: SyntheticWorld) -> float:
    calibration, evaluation = split_calibration(world, seed)
    # P mulai dari snapshot kalibrasi; baseline tidak belajar, jadi hanya dievaluasi.
    state = run_policy("P", seed, world, calibration)[1] if kind == "P" else None
    return run_policy(kind, seed, world, evaluation, init_state=state)[0]


@pytest.fixture(scope="module")
def mean_reward():
    world = SyntheticWorld(seed=20260101, n_tasks=1500)
    out = {k: mean(_evaluate(k, s, world) for s in SEEDS) for k in KINDS}
    print("\nreward rata-rata per insiden: " + ", ".join(f"{k}={v:.4f}" for k, v in out.items()))
    return out


@pytest.mark.slow
def test_linucb_beats_static_random_and_retry(mean_reward):
    for base in ("B2", "B3", "B1"):
        assert mean_reward["P"] > mean_reward[base], (base, mean_reward)


@pytest.mark.slow
def test_b2_beats_random_so_the_world_rewards_domain_knowledge(mean_reward):
    # Sanity dunia: jika B3 >= B2 maka peta statis tidak informatif dan perbandingan P vs B2 tak berarti.
    assert mean_reward["B2"] > mean_reward["B3"]
