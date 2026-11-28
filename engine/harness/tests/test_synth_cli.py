"""The command line, and determinism by hashing."""

import pytest

from engine.harness.synth.cli import HELD_OUT_SEEDS, main, tree_hash, verify


def test_two_small_runs_hash_identically_and_a_different_seed_does_not():
    assert verify("capacity_constrained", 5)


def test_the_command_line_writes_extracts_and_truth_and_refuses_held_out_seeds(
    tmp_path, capsys
):
    assert (
        main(
            [
                "--small",
                "--variant",
                "demand_limited",
                "--seed",
                "7",
                "--out",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert (tmp_path / "truth" / "manifest.json").exists()
    assert "bookings" in capsys.readouterr().out
    other = tmp_path / "other"
    assert (
        main(
            [
                "--small",
                "--variant",
                "demand_limited",
                "--seed",
                "8",
                "--out",
                str(other),
            ]
        )
        == 0
    )
    assert tree_hash(tmp_path / "truth") != tree_hash(other / "truth")
    with pytest.raises(SystemExit):
        main(
            ["--small", "--seed", str(HELD_OUT_SEEDS[0]), "--out", str(tmp_path / "x")]
        )
    assert not (tmp_path / "x").exists()
