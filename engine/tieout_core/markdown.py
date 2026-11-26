"""Render the report dict as Markdown. Presentation only: no calculation here."""

from __future__ import annotations

from decimal import Decimal


def render(r: dict) -> str:
    i = r["inputs"]
    out = [
        f"# Forecast tieout: {i['data']}",
        "",
        (
            f"As of **{i['as_of']}**, fiscal year {i['fiscal_year']} ({i['fiscal_year_start']} to "
            f"{i['fiscal_year_end']}). One money measure throughout: {i['measure']}."
        ),
        (
            f"Profile `{i['profile']}`. Ranges from {i['simulation']['draws']} simulated draws, seed "
            f"{i['simulation']['seed']}."
        ),
        "",
    ]
    out += _reconciliation(r["reconciliation"])
    out += _history(r["history"])
    out += _forecasts(r["forecasts"])
    out += _rates(r["rates"])
    out += _gap(r["gap"])
    out += _backtest(r["backtest"])
    out += _verdicts(r["verdicts"])
    return "\n".join(out).rstrip() + "\n"


def _usd(x, cents=False) -> str:
    if x is None:
        return "n/a"
    v = Decimal(x)
    return (
        f"-${-v:,.2f}"
        if v < 0 and cents
        else (f"${v:,.2f}" if cents else (f"-${-v:,.0f}" if v < 0 else f"${v:,.0f}"))
    )


def _table(headers, rows) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return lines + [""]


def _reconciliation(s: dict) -> list[str]:
    out = ["## 1. Reconciliation", ""]
    out += [
        (
            f"{s['source_rows']} rows in `deals.csv` (ARR {_usd(s['source_arr_total'], True)}); "
            f"{s['included_rows']} new-business rows included, {len(s['exclusions'])} excluded."
        ),
        "",
        f"New-business bookings fiscal year to date: **{_usd(s['bookings_fytd'], True)}**.",
        "",
    ]
    out += _table(
        ["Month", "Bookings"],
        [(m, _usd(v, True)) for m, v in s["bookings_by_month"].items()],
    )
    out += ["Pipeline flow, fiscal-year start to as-of (current amounts):", ""]
    out += _table(
        ["", "Deals", "ARR"],
        [(k, v["count"], _usd(v["arr"], True)) for k, v in s["pipeline_flow"].items()],
    )
    if s["excluded_motions"]:
        out += ["Other motions, reconciled separately and excluded:", ""]
        out += _table(
            ["Motion", "Rows", "ARR", "Won FYTD"],
            [
                (k, v["rows"], _usd(v["arr"], True), _usd(v["won_fytd_arr"], True))
                for k, v in s["excluded_motions"].items()
            ],
        )
    out += _checks(s["checks"])
    if s["exclusions"]:
        reasons = {}
        for e in s["exclusions"]:
            reasons[e["reason"]] = reasons.get(e["reason"], 0) + 1
        out += ["Excluded rows by reason:", ""]
        out += _table(["Reason", "Rows"], sorted(reasons.items()))
        out += ["<details><summary>Every excluded row</summary>", ""]
        out += _table(
            ["Row", "Deal", "Reason", "ARR"],
            [
                (e["row"], e["deal_id"], e["reason"], _usd(e["arr"], True))
                for e in s["exclusions"]
            ],
        )
        out += ["</details>", ""]
    return out


def _checks(checks) -> list[str]:
    return _table(
        ["Check", "Result", "Detail"],
        [
            (c["name"], "pass" if c["passed"] else "**FAIL**", c["detail"])
            for c in checks
        ],
    )


def _history(s: dict) -> list[str]:
    f = s["facts"]
    out = ["## 2. What the history can support", ""]
    out += [
        (
            f"{f['new_business_deals']} new-business deals, first created {f['first_deal_created']} "
            f"({f['months_of_history']} months before the as-of date); {f['closed_outcomes']} closed outcomes; "
            f"{f['matured_snapshots']} monthly snapshots old enough to score a full horizon."
        ),
        "",
        "What cannot be reconstructed or relied on:",
        "",
    ]
    out += [f"- {x}" for x in s["limitations"]] + [""]
    return out


def _forecasts(s: dict) -> list[str]:
    out = ["## 3. Three forecasts, side by side", ""]
    if not s["windows"]:
        return out + ["No months follow the as-of date.", ""]
    methods = s["methods"]
    rows = []
    for m in methods:
        if not m["available"]:
            rows.append(
                [m["method"], "total"]
                + ["n/a"] * len(s["windows"])
                + [f"unavailable: {m['unavailable_reason']}"]
            )
            continue
        for part, values in m["components"].items():
            rows.append(
                [m["method"], part]
                + [_usd(values[w]) for w in s["windows"]]
                + [_usd(sum(Decimal(v) for v in values.values()))]
            )
    out += _table(["Method", "Part", *s["windows"], "Total"], rows)
    spans = s["horizon_windows"]
    out += ["Two windows:", ""]
    out += _table(
        ["Method"] + [f"{h} ({' to '.join(spans[h]) or 'no months'})" for h in spans],
        [
            [m["method"]]
            + [_usd(m["horizons"][h]) if m["available"] else "n/a" for h in spans]
            for m in methods
        ],
    )
    fr = s["fitted_ranges"]
    out += [f"Fitted-model ranges ({fr['status']}):", ""]
    out += _table(
        ["Month", "Median", "80% range", "95% range"],
        [
            (w, _usd(v["median"]), _rng(v["range80"]), _rng(v["range95"]))
            for w, v in fr["by_window"].items()
        ]
        + [
            (f"{h} ({v['status'].split(':')[0]})", _usd(v["median"]), _rng(v["range80"]),
             _rng(v["range95"]))
            for h, v in fr["horizons"].items()
        ],
    )  # fmt: skip
    out += ["Assumptions:", ""]
    for m in methods:
        out += [
            f"- **{m['method']}**: "
            + "; ".join(m["assumptions"] or [m["unavailable_reason"]])
        ]
    return out + [""]


def _rng(pair) -> str:
    return "n/a" if pair is None else f"{_usd(pair[0])} to {_usd(pair[1])}"


def _rates(rates) -> list[str]:
    out = [
        "## 4. Every rate once",
        "",
        "Each rate has one definition, used everywhere it appears.",
        "",
    ]
    out += _table(
        [
            "Rate",
            "Value",
            "Numerator / denominator",
            "Cohort",
            "Horizon",
            "n",
            "Source",
        ],
        [
            (
                f"`{r['name']}`",
                r["value"]
                + (
                    f" (95%: {r['range95'][0]}-{r['range95'][1]})"
                    if r["range95"]
                    else ""
                ),
                f"{r['numerator']} / {r['denominator']}"
                if r["numerator"]
                else r["definition"],
                r["cohort"],
                r["horizon"],
                r["sample_size"],
                r["source"],
            )
            for r in rates
        ],
    )
    return out


def _gap(s: dict) -> list[str]:
    out = [
        "## 5. The gap",
        "",
        f"Forecast: {s['forecast_method']}. Gap = target - actual - forecast (positive = short).",
        "",
    ]
    out += _table(
        [
            "Quarter",
            "Status",
            "Target",
            "Actual",
            "Forecast",
            "Expected",
            "Gap",
            "Expected 80% range",
        ],
        [
            (
                q["quarter"],
                q["status"],
                _usd(q["target"]),
                _usd(q["actual"]),
                _usd(q["forecast"]),
                _usd(q["expected"]),
                _usd(q["gap"]),
                _rng(q["expected_range80"]),
            )
            for q in s["quarters"]
        ],
    )
    fy = s["fiscal_year"]
    out += [
        (
            f"Fiscal year: target {_usd(fy['target'])}, actual to date {_usd(fy['actual_to_date'])}, "
            f"forecast rest of year {_usd(fy['forecast_rest_of_year'])}, expected **{_usd(fy['expected'])}** "
            f"(80%: {_rng(fy['expected_range80'])}; 95%: {_rng(fy['expected_range95'])}), gap **{_usd(fy['gap'])}**."
        ),
        "",
    ]
    t = s["next_twelve_months"]
    window = " to ".join(t["window"])
    if t["targets_through"]:
        out += [
            (
                f"Next twelve months ({window}): quarters with a target ending in the window "
                f"({', '.join(t['quarters'])}, through {t['targets_through']}): target {_usd(t['target'])}, "
                f"actual to date {_usd(t['actual'])}, forecast {_usd(t['forecast'])}, gap **{_usd(t['gap'])}**."
            ),
            "",
        ]
    u = t["untargeted"]
    if u["months"]:
        out += [
            f"{' to '.join([u['months'][0], u['months'][-1]])}: forecast {_usd(u['forecast'])} ({u['note']}).",
            "",
        ]
    out += _lever("Lever (fiscal year)", s["lever"])
    out += _lever("Lever (next twelve months)", s["lever_next_twelve_months"])
    return out


def _lever(title: str, lv: dict) -> list[str]:
    if lv["outcome"] in ("unavailable", "no target in this window"):
        return [f"**{title}, {lv['lever']}: {lv['outcome']}.** {lv['reason']}.", ""]
    gained = "; ".join(f"{h} {_usd(v)}" for h, v in lv["bookings_gained"].items())
    return [
        f"**{title}, {lv['lever']}: {lv['headline']}.** Schedule: {lv['schedule']}; cap {_usd(lv['cap'])} "
        f"({lv['cap_rule']}). Forecast without it {_usd(lv['forecast_without_lever'])}, with it "
        f"{_usd(lv['forecast_with_lever'])}, against {_usd(lv['target'])}. "
        f"Bookings gained at {lv['bookings_gained_at']}: {gained}."
        + (f" Note: {lv['note']}." if lv.get("note") else ""),
        f"_{lv['meaning'].capitalize()}._",
        "",
    ]


def _backtest(s: dict) -> list[str]:
    out = [
        "## 6. Back-test",
        "",
        f"Scoring (declared before building): {s['scoring']}.",
        "",
    ]
    rows = []
    for h in s["horizons"]:
        for method, mae in h["mean_absolute_error"].items():
            cov = (
                h["range_coverage"]
                if method == "fitted model"
                else {"80%": None, "95%": None}
            )
            rows.append(
                (
                    f"{h['horizon_months']} mo",
                    h["folds"],
                    method,
                    _usd(mae),
                    _usd(h["signed_bias"][method]),
                    _pct(cov["80%"]),
                    _pct(cov["95%"]),
                )
            )
    out += _table(
        [
            "Horizon",
            "Folds",
            "Method",
            "Mean abs. error",
            "Signed bias",
            "80% coverage",
            "95% coverage",
        ],
        rows,
    )
    out += [f"- {n}" for n in s["notes"]] + ([""] if s["notes"] else [])
    return out


def _pct(x) -> str:
    return "" if x is None else f"{x:.0%}"


def _verdicts(s: dict) -> list[str]:
    sc, fc = s["software_correct"], s["forecast_better_than_baselines"]
    out = ["## 7. Verdicts", ""]
    out += [
        f"**The software is correct: {sc['verdict']}.** {sc['summary']} ({sc['scope']}).",
        "",
    ]
    out += _checks(sc["checks"])
    out += [
        f"**The forecast is better than the baselines: {fc['verdict']}.** {fc['reason']}.",
        "",
    ]
    return out
