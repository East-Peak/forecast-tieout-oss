"""Keyed random streams: the basis of common random numbers across paired runs."""

from engine.harness.synth.rng import Streams, poisson_quantile


def test_a_stream_depends_only_on_seed_and_key():
    a, b = Streams(7), Streams(7)
    b.rng("lead", 1).random()  # drawing elsewhere must not move this stream
    assert a.rng("lead", 2).random() == b.rng("lead", 2).random()
    assert a.rng("lead", 2).random() != a.rng("lead", 3).random()
    assert a.rng("lead", 2).random() != Streams(8).rng("lead", 2).random()
    assert a.rng("x").random() != a.rng("y").random()


def test_poisson_quantile_is_monotone_in_both_arguments_and_has_the_right_mean():
    for u in (0.05, 0.4, 0.95):
        counts = [poisson_quantile(u, lam) for lam in (0.5, 1.0, 2.0, 4.0)]
        assert counts == sorted(counts)
    assert poisson_quantile(0.999999, 0.0) == 0
    rng = Streams(1).rng("mean")
    draws = [poisson_quantile(u, 3.0) for u in rng.random(20000)]
    assert abs(sum(draws) / len(draws) - 3.0) < 0.1
