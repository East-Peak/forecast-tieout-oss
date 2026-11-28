"""Keyed random streams.

Every random quantity belongs to one entity (a lead, a deal, a person, a
campaign-day) and is drawn from a stream keyed by (seed, entity key). Adding,
removing or delaying other entities never shifts it, which is what lets a paired
counterfactual share random numbers with its base run: an agent the intervention
does not touch draws exactly the fates it drew before.
"""

import zlib
from math import exp

import numpy as np


def _part(x: int | str) -> int:
    return x if isinstance(x, int) else zlib.crc32(x.encode())


class Streams:
    def __init__(self, seed: int):
        self.seed = seed

    def rng(self, *key: int | str) -> np.random.Generator:
        spawn_key = tuple(_part(x) for x in key)
        return np.random.default_rng(
            np.random.SeedSequence(self.seed, spawn_key=spawn_key)
        )


def poisson_quantile(u: float, lam: float) -> int:
    """Inverse CDF of Poisson(lam): a count that never falls as lam or u rise (a coupling)."""
    if lam <= 0:
        return 0
    k, p = 0, exp(-lam)
    cumulative = p
    while u > cumulative and k < 10_000:
        k += 1
        p *= lam / k
        cumulative += p
    return k
