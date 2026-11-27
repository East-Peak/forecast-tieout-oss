"""Goal 2D wording: the two lengths of label, both built from one structured basis. The short
one is for cards and opened quarter rows (no dates, about eight words); the full one is for the
"how far to trust the ranges" line and the checks section, in plain sentences. Thin evidence is
said to be thin and never given as a bare "held 0 of 1"."""

from datetime import date

from engine.tieout_core.stretch_report import Basis, label95, label_full, label_short


def basis(**kw):
    base = {
        "factor_horizon_months": 6, "held": 0, "scored": 1, "stretched_side": "lower",
        "window_start": date(2026, 8, 31), "window_end": date(2027, 1, 31),
        "extrapolated_because": "not_the_tested_shape", "floored80": False, "floored95": False,
    }  # fmt: skip
    return Basis(**{**base, **kw})


def test_the_short_label_says_which_side_was_stretched_in_about_eight_words():
    assert label_short(basis()) == "Stretched on the low side by past misses"
    assert (
        label_short(basis(stretched_side="upper"))
        == "Stretched on the high side by past misses"
    )
    assert (
        label_short(basis(stretched_side="both"))
        == "Stretched on both sides by past misses"
    )
    for b in (basis(), basis(stretched_side="both", floored80=True)):
        assert len(label_short(b).split()) <= 10 and not any(
            c.isdigit() for c in label_short(b)
        )


def test_the_short_label_says_when_the_lower_edge_was_floored_at_zero():
    assert (
        label_short(basis(floored80=True))
        == "Stretched on the low side by past misses; floored at zero"
    )


def test_the_ninety_five_label_says_it_is_the_same_stretch_and_not_separately_tested():
    assert label95(basis()) == "Stretched the same way; not separately tested"
    assert (
        label95(basis(floored95=True))
        == "Stretched the same way; not separately tested; floored at zero"
    )


def test_the_full_label_calls_one_scored_forecast_thin_and_never_prints_held_zero_of_one():
    text = label_full(basis())
    assert text == (
        "Stretched by the model's own past misses, using what six-month forecasts needed. "
        "Evidence at this length is thin: 1 past six-month forecast could be scored, and the "
        "stretched range did not hold it. This window (Aug 31, 2026 to Jan 31, 2027) is not "
        "exactly the six-month forecast that was tested."
    )
    assert "held 0 of 1" not in text and "2026-08-31" not in text


def test_thin_evidence_gives_the_counts_in_words():
    assert (
        "1 past six-month forecast could be scored, and the stretched range held it."
        in label_full(basis(held=1))
    )
    three = label_full(basis(factor_horizon_months=3, held=2, scored=3))
    assert (
        "3 past three-month forecasts could be scored, and the stretched range held 2 of them."
        in three
    )
    assert "thin" in three
    zero = label_full(basis(scored=0, held=0))
    assert "No past six-month forecast could be scored yet" in zero


def test_with_six_or_more_scored_it_says_held_n_of_m():
    text = label_full(
        basis(factor_horizon_months=3, held=7, scored=7, extrapolated_because=None)
    )
    assert "The stretched range held 7 of 7 past three-month forecasts." in text
    assert "thin" not in text
    assert (
        "not exactly" not in text and "longer than" not in text
    )  # a tested shape says nothing more


def test_a_window_longer_than_six_months_says_it_uses_the_six_month_factors():
    text = label_full(
        basis(
            extrapolated_because="longer_than_six_months", window_end=date(2027, 8, 31)
        )
    )
    assert (
        "This window (Aug 31, 2026 to Aug 31, 2027) is longer than six months, so it uses the six-month factors."
        in text
    )


def test_a_floored_lower_edge_is_said_in_the_full_label_too():
    assert label_full(basis(floored80=True)).endswith(
        "The lower edge of this range was floored at zero."
    )
