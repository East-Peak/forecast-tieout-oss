"""Keyed random streams.

Every random quantity belongs to one entity (a lead, a deal, a person, a
campaign-day) and is drawn from a stream keyed by (seed, entity key). Adding,
removing or delaying other entities never shifts it, which is what lets a paired
counterfactual share random numbers with its base run: an agent the intervention
does not touch draws exactly the fates it drew before.
"""

import hashlib
import zlib
from math import exp

import numpy as np


def _part(x: int | str) -> int:
    return x if isinstance(x, int) else zlib.crc32(x.encode())


class Streams:
    """Keyed streams. With a `fork_day`, anything created on or after that day (the call passes
    its creation `day`) is re-keyed by `replicate`: the company is identical before the fork and
    an independent draw after it, which is what an expected-effect benchmark averages over."""

    def __init__(self, seed: int, replicate: int = 0, fork_day: int | None = None):
        self.seed, self.replicate, self.fork_day = seed, replicate, fork_day

    def rng(self, *key: int | str, day: int | None = None) -> np.random.Generator:
        if self.fork_day is not None and day is not None and day >= self.fork_day:
            key = (*key, "replicate", self.replicate)
        spawn_key = tuple(_part(x) for x in key)
        return np.random.default_rng(
            np.random.SeedSequence(self.seed, spawn_key=spawn_key)
        )

    def uniform(self, *key: int | str, day: int | None = None) -> float:
        """One uniform from the entity's stream, much cheaper than building a Generator."""
        if self.fork_day is not None and day is not None and day >= self.fork_day:
            key = (*key, "replicate", self.replicate)
        text = "|".join(map(str, (self.seed, *key)))
        return (
            int.from_bytes(
                hashlib.blake2b(text.encode(), digest_size=8).digest(), "big"
            )
            / 2**64
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
