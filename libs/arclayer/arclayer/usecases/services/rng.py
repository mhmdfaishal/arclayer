"""RNG per policy instance yang statenya dipersistenkan, supaya tie-break dan baseline
acak tetap reproducible walau proses dimulai ulang di tengah aliran insiden."""

from __future__ import annotations

from typing import Any

import numpy as np


def new_rng_state(seed: int) -> dict[str, Any]:
    return np.random.Generator(np.random.PCG64(seed)).bit_generator.state


def restore(state: dict[str, Any]) -> np.random.Generator:
    g = np.random.Generator(np.random.PCG64())
    g.bit_generator.state = state
    return g


def dump(g: np.random.Generator) -> dict[str, Any]:
    return g.bit_generator.state
