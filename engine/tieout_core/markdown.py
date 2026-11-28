"""Render the report dict as Markdown. Presentation only: no calculation here."""

from __future__ import annotations

from decimal import Decimal

from .plan import NEXT_12 as NEXT
from .plan import REST_OF_FY as REST


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
            f"Profile `{i['profile']}`. Fit: {i['fit']}. Ranges from {i['simulation']['draws']} "
            f"simulated draws, seed {i['simulation']['seed']}, drawing {i['ranges']}."
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
    if "roster_capacity" in r:
        out += _roster_capacity(r["roster_capacity"])
        out += _productivity(r["quota_productivity"])
        out += _required(r["required_pipeline"])
        if "plan" in r:
            out += _plan(r["plan"])
        out += _actions(r["actions"])
        out += _driver_actions(r["driver_actions"])
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
    out += [f"Months: {fr['by_window_label']}.", ""]
    out += [f"- {h}: {v['status']}" for h, v in fr["horizons"].items()] + (
        [""] if fr["horizons"] else []
    )
    out += _table(
        ["Month", "Median", "80% range", "95% range"],
        [
            (w, _usd(v["median"]), _rng(v["range80"]), _rng(v["range95"]))
            for w, v in fr["by_window"].items()
        ]
        + [
            (f"{h} ({v['label_short']}; 95%: {v['label95']})", _usd(v["median"]),
             _rng(v["range80"]), _rng(v["range95"]))
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


def _labeled(label) -> str:
    return "" if label is None else f", {label}"


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
            f"(80%: {_rng(fy['expected_range80'])}{_labeled(fy.get('label_short'))}; "
            f"95%: {_rng(fy['expected_range95'])}{_labeled(fy.get('label95'))}), "
            f"gap **{_usd(fy['gap'])}**."
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
    out += _lever("Pipeline to meet the fiscal-year total, spread evenly", s["lever"])
    out += _lever(
        "Pipeline to meet the next-twelve-months targets, spread evenly",
        s["lever_next_twelve_months"],
    )
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
    c = s["candidates"]["recency"]
    out += [
        (
            f"Recency candidate ({c['candidate']}) against the Goal 1 fit ({c['incumbent']}), "
            f"same folds. Rule: {c['rule']}."
        ),
        "",
    ]
    out += _table(
        ["Horizon", "Folds", c["incumbent"], c["candidate"]],
        [
            (h, c["folds"][h], _usd(v[c["incumbent"]]), _usd(v[c["candidate"]]))
            for h, v in c["mean_absolute_error"].items()
        ],
    )
    out += [
        (
            f"**{'Adopted' if c['adopted'] else 'Not adopted'}**: {c['reason']}. "
            f"The forecast, rates, ranges and verdict use the {c['fit_in_use']} fit."
        ),
        "",
    ]
    return out + _stretch(s["candidates"]["ranges"])


def _stretch(c: dict) -> list[str]:
    """Ranges stretched by past misses: the rule, the decision and, per horizon, the evidence."""
    out = [
        f"Ranges stretched by the model's own past misses. Rule: {c['rule']}.",
        "",
    ]
    out += _table(
        [
            "Horizon",
            "Eligible folds",
            "Scored folds",
            "Simulated 80% coverage",
            "Stretched 80% coverage",
            "Median 80% width, simulated",
            "Median 80% width, stretched",
            "Lower factor",
            "Upper factor",
        ],
        [
            (
                f"{h['horizon_months']} mo",
                h["eligible_folds"],
                h["scored_folds"],
                f"{h['inside_simulated']} of {h['scored_folds']} ({_pct(h['coverage_simulated'])})",
                f"{h['inside_stretched']} of {h['scored_folds']} ({_pct(h['coverage_stretched'])})",
                _usd(h["median_width80_simulated"]),
                _usd(h["median_width80_stretched"]),
                "n/a" if h["lower_factor"] is None else h["lower_factor"],
                "n/a" if h["upper_factor"] is None else h["upper_factor"],
            )
            for h in c["horizons"]
        ],
    )
    out += [f"**{c['decision'].capitalize()}**: {c['reason']}.", ""]
    if c["acceptance"] is not None:
        out += [f"What the rule accepted: {c['acceptance']['sentence']}", ""]
    return out + [f"Method: {c['method']}", ""]


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


def _roster_capacity(s: dict) -> list[str]:
    d, ro = s["decision"], s["roster"]
    out = ["## 8. Roster and capacity", ""]
    out += [
        f"**Capacity term: {d['outcome']}.** {d['reason']}.",
        "",
        f"Scored on {d['scored_on']}. {_up(d['label'])}.",
        f"Declared rule: {d['declared_rule']}.",
        f"The forecast, gap, plan and actions use the {d['forecast_uses']}. {d['association']}",
        "",
    ]
    if d["horizons"]:
        out += _table(
            ["Horizon", "Folds", "Flat trailing rate, mean abs. error", "Capacity rate, mean abs. error", "Improvement"],
            [
                (f"{h['horizon_months']} mo", h["folds"], _usd(h["mean_absolute_error_flat"]),
                 _usd(h["mean_absolute_error_capacity"]), f"{float(h['improvement']):.1%}")
                for h in d["horizons"]
            ],
        )  # fmt: skip
    if d["staffing_variation"] is not None:
        out += [
            (
                f"Ramped AE-months varied {float(d['staffing_variation']):.0%} across the scored "
                f"period ({' to '.join(d['scored_period'] or [])})."
            ),
            "",
        ]
    if "unavailable" in ro:
        out += [f"Roster unavailable: {ro['unavailable']}.", ""]
    else:
        out += [
            (
                f"Roster: {ro['rows']} rows; {ro['quota_carrying_rows']} quota-carrying people on file, "
                f"{ro['heads_at_as_of']} employed at the as-of date, "
                f"{ro['ramped_equivalents_at_as_of']} ramped equivalents, against a headcount target of "
                f"{ro['headcount_target_this_month']} this month ({ro['headcount_target_note']}). "
                f"{ro['departed_to_date']} have left to date; {len(ro['signed_hires'])} signed hires."
            ),
            "",
        ]
        if ro["other_roles_counted_no_capacity"]:
            counts = ", ".join(
                f"{k} {v}" for k, v in ro["other_roles_counted_no_capacity"].items()
            )
            out += [f"Counted, carrying no capacity: {counts}.", ""]
        if ro["excluded"]:
            out += ["Excluded rows:", ""]
            out += _table(
                ["Id", "Role", "Reason"],
                [(e["id"], e["role"], e["reason"]) for e in ro["excluded"]],
            )
    if "ramp" in s:
        rp, at, cr = s["ramp"], s["attrition"], s["creation_rate"]
        out += [
            f"**Ramp ({rp['source']}):** {rp['sample']}. {rp['definition']}; {rp['after']}."
            + (
                f" Not fitted because {rp['why_not_fitted']}."
                if rp["why_not_fitted"]
                else ""
            )
            + (
                f" Fitted through: {rp['fitted_through']}."
                if rp["fitted_through"]
                else ""
            )
            + (
                f" {_up(rp['deals_left_out']['why'])}."
                if rp["deals_left_out"]["why"]
                else ""
            )
            + (f" Limit: {rp['limitation']}." if rp["limitation"] else ""),
            "",
        ]
        out += _table(
            ["Tenure month", "Weight", "95% range"],
            [
                (
                    w["tenure_month"],
                    w["weight"],
                    " to ".join(w["range95"]) if w["range95"] else "",
                )
                for w in rp["weights"]
            ],
        )
        out += [
            f"**Attrition ({at['source']}):** {at['monthly_rate']} per AE-month, {at['sample']}"
            + (f" (95%: {' to '.join(at['range95'])})" if at["range95"] else "")
            + (
                f"; not fitted because {at['why_not_fitted']}"
                if at["why_not_fitted"]
                else ""
            )
            + f". Forward: {at['forward']}.",
            "",
            (
                f"**Created deals per ramped AE-month:** {cr['deals_per_ramped_ae_month']} "
                f"({cr['trailing_deals']} deals over {cr['trailing_ramped_ae_months']} ramped AE-months, "
                f"{cr['window']})."
            ),
            "",
        ]
    if "months" in s:
        with_plan = any(m["heads_with_plan"] is not None for m in s["months"])
        out += [
            "Heads, ramped equivalents and departures by month (forward months are expectations):",
            "",
        ]
        out += _table(
            ["Month", "", "Heads", "Ramped", "Departures", "Headcount target"]
            + (["Heads with plan"] if with_plan else []),
            [
                [m["month"], m["kind"], m["heads"], m["ramped"], m["departures"],
                 "" if m["headcount_target"] is None else m["headcount_target"]]
                + ([m["heads_with_plan"] or ""] if with_plan else [])
                for m in s["months"]
            ],
        )  # fmt: skip
    if "diagnostic" in s:
        g = s["diagnostic"]
        out += [
            f"**Capacity projection, a diagnostic ({g['label']}):** bookings if capacity drove the "
            + "forecast: "
            + "; ".join(
                f"{h} {_usd(v)}"
                for h, v in g["bookings_with_capacity_projection"].items()
            )
            + "; the forecast actually shown, at the flat rate: "
            + "; ".join(
                f"{h} {_usd(v)}" for h, v in g["bookings_with_flat_rate"].items()
            )
            + f". Hiring action: {g['hiring_action']}.",
            "",
        ]
    out += ["Limits:", ""] + [f"- {x}" for x in s["limitations"]] + [""]
    return out


def _productivity(s: dict) -> list[str]:
    out = ["## 9. Quota against observed productivity", ""]
    if "unavailable" in s:
        return out + [f"Unavailable: {s['unavailable']}.", ""]
    out += [
        f"{_up(s['definition'])} ({s['window']}). Observed, never model output.",
        "",
    ]
    rows = [
        (name, b["reps"], _usd(b["prorated_quota"]), _usd(b["wins_credited"]),
         _pct_str(b["attainment"]), _spread(b["spread_across_reps"]))
        for name, b in [*s["by_segment"].items(), ("all reps", s["all_reps"])]
    ]  # fmt: skip
    out += _table(
        [
            "Segment",
            "Reps",
            "Prorated quota",
            "Wins credited",
            "Attainment",
            f"Across reps employed {s['spread_min_days']}+ days (min / p25 / median / p75 / max)",
        ],
        rows,
    )
    t = s["total_quota"]
    out += [
        (
            f"Wins in the window {_usd(s['wins_in_window'])}: credited {_usd(s['wins_credited'])}, "
            f"unattributed {_usd(s['wins_unattributed'])} ({s['unattributed_note']})."
        ),
        "",
        (
            f"Total quota {_usd(t['annual_quota_of_people_employed_at_as_of'])} for {t['people']} people "
            f"over a target of {_usd(t['fiscal_year_target'])}: **{t['quota_over_target']}x** ({t['note']})."
        ),
        "",
        "Limits:",
        "",
    ]
    out += [f"- {x}" for x in s["limits"]] + [""]
    return out


def _up(text: str) -> str:
    return text[:1].upper() + text[1:]


def _pct_str(x) -> str:
    return "n/a" if x is None else f"{float(x):.0%}"


def _spread(x) -> str:
    return (
        "n/a"
        if x is None
        else " / ".join(
            f"{float(x[k]):.0%}" for k in ("min", "p25", "median", "p75", "max")
        )
    )


def _times(x: str | None) -> str:
    return "n/a" if x is None else f"{float(x):.2f}x"


def _share(x: str) -> str:
    return f"{float(x):.1%}"


def _required(s: dict) -> list[str]:
    out = ["## 10. Required against expected pipeline, by quarter", ""]
    if "unavailable" in s:
        return out + [
            f"Unavailable: the fitted forecast is unavailable ({s['unavailable']}).",
            "",
        ]
    out += [
        (
            f"{_up(s['method'])}. Forward function: {s['forward_function']}. Cap: "
            f"{_usd(s['cap'])} ({s['cap_rule']})."
        ),
        "",
    ]
    out += ["**The requirement.**", ""]
    out += _table(
        ["Quarter", "Target", "Actual", "Created between", "Result", "Cents booked in the quarter per dollar created",
         "Bookings without own pipeline", "Bookings under the completed schedule", "Surplus over target"],
        [
            (q["quarter"] + ("" if q["in_fiscal_year"] else " (next year)"), _usd(q["target"]),
             _usd(q["actual"]), " to ".join(q["created_between"]), q["headline"],
             f"{q['cents_booked_in_quarter_per_dollar']}c",
             _usd(q["bookings_without_own_pipeline"]), _usd(q["bookings_under_completed_schedule"]),
             _usd(q["surplus_over_target"]))
            for q in s["quarters"]
        ],
    )  # fmt: skip
    label = s["per_ramped_ae_month_label"]
    out += [
        "**Against the team's record.** Everything created in the span includes what earlier quarters were assigned.",
        "",
    ]
    out += _table(
        ["Quarter", "Extra pipeline required", "Expected created", "Earlier quarters' assignments in the span",
         "Total created in the span", "Per day", "Against the team's best per day",
         f"Per ramped AE-month ({label})", "Against the team's best per ramped AE-month", "Too late, and why"],
        [
            (q["quarter"], _usd(q["required_extra_pipeline"]), _usd(q["expected_created_pipeline"]),
             _usd(q["earlier_assigned_in_span"]), _usd(q["total_created_in_span"]),
             _usd(q["per_day"]["required_total"]), _times(q["per_day"]["required_against_team_best"]),
             _usd(q["per_ramped_ae_month"]["required_total"]),
             _times(q["per_ramped_ae_month"]["required_against_team_best"])
             + ("" if q["per_ramped_ae_month"]["decides"] else " (diagnostic)"),
             ("too late: " + "; ".join(q["too_late"]["legs"])) if q["too_late"]["applies"] else "no")
            for q in s["quarters"]
        ],
    )  # fmt: skip
    rule = s["per_rep_rule"]
    out += [
        (
            f"Too late, as a rule: {s['too_late_rule']}. Per-ramped-AE-month comparison "
            f"{'applies' if rule['applies'] else 'does not apply'}: {rule['why']}."
        ),
        "",
    ]
    for q in s["quarters"]:
        late = q["too_late"]
        for note in late["diagnostics"]:
            out += [f"{q['quarter']}: {note}.", ""]
        if not late["applies"]:
            continue
        op = late["open_pipeline"]
        out += [
            (
                f"**{q['quarter']}: {late['label']}.** Why: {'; '.join(late['reasons'])}. The open pipeline "
                f"({_usd(op['open_arr'])}) is expected to book {_usd(op['expected_contribution'])} inside the quarter; "
                f"{op['statement']}."
            ),
            "",
        ]
    lt = s["lead_time"]
    out += [
        f"**Lead time: {lt['question']}** (created {' to '.join(lt['created_between'])}; {lt['basis']}).",
        "",
    ]
    out += _table(
        ["Quarter", "Cents booked inside the quarter", "Cents booked by its end"],
        [
            (q["quarter"], f"{q['cents_booked_in_quarter']}c", f"{q['cents_booked_by_quarter_end']}c")
            for q in lt["quarters"]
        ]
        + [("After the fourth quarter", f"{lt['cents_booked_later']}c", "")],
    )  # fmt: skip
    co = lt["count_outcome"]
    out += [
        (
            f"Count outcome, {co['meaning']}: {_share(co['win_within_horizon'])} expected to win "
            f"within the horizon, {_share(co['do_not_win'])} not."
        ),
        "",
    ]
    fy, h = s["fiscal_year"], s["team_history"]
    out += [
        (
            f"Fiscal year, {fy['name']}: **{fy['headline']}**. Section 5's {fy['single_spread']['name']}: "
            f"{fy['single_spread']['headline']}. {fy['why_they_differ']}"
        ),
        "",
        (
            f"The team's own record ({h['quarters']} complete quarters, {h['unit']}): median "
            f"{_usd(h['median'])}, best four-quarter average {_usd(h['best_four_quarter_average'])}; best "
            f"four-quarter average of total created pipeline {_usd(h['best_four_quarter_average_per_day'])} a day. {h['note']}."
        ),
        "",
        f"_{_up(s['meaning'])}. {_up(s['expected_basis'])}._",
        "",
    ]
    return out


def _plan(s: dict) -> list[str]:
    out = ["## 11. The plan", ""]
    if "unavailable" in s:
        return out + [
            f"Unavailable: the fitted forecast is unavailable ({s['unavailable']}).",
            "",
        ]
    out += [
        f"Plan file `{s['file']}`. {_up(s['order'])}. Baseline: {s['baseline_definition']}.",
        "",
    ]
    rows = []
    for i in s["items"]:
        c = i["contribution"]
        rows.append(
            [i["label"], i["detail"], i.get("note", "valued"),
             _usd(c[REST]) if c else "not valued", _usd(c[NEXT]) if c else "not valued",
             "no cost entered" if i["kind"] == "actions"
             else _cost(i["cash_cost_in_twelve_months"])]
        )  # fmt: skip
    out += _table(
        [
            "Item",
            "What",
            "",
            f"Adds, {REST}",
            f"Adds, {NEXT}",
            "Cash cost in twelve months",
        ],
        rows,
    )
    out += _table(
        ["Bookings", REST, NEXT],
        [
            ("Baseline", _usd(s["baseline"][REST], True), _usd(s["baseline"][NEXT], True)),
            ("With the plan", _usd(s["with_plan"][REST], True), _usd(s["with_plan"][NEXT], True)),
            ("Difference", _usd(s["difference"][REST], True), _usd(s["difference"][NEXT], True)),
            ("Sum of the contributions", _usd(s["contributions_total"][REST], True),
             _usd(s["contributions_total"][NEXT], True)),
        ],
    )  # fmt: skip
    fy, t = s["gap"]["fiscal_year"], s["gap"]["next_twelve_months"]
    out += [
        (
            f"Fiscal-year gap: {_usd(fy['baseline_gap'])} before the plan, **{_usd(fy['gap_with_plan'])}** "
            f"with it (target {_usd(fy['target'])}, actual to date {_usd(fy['actual_to_date'])})."
        ),
        "",
    ]
    if t is not None:
        out += [
            f"Twelve-month gap ({t['note']}): {_usd(t['baseline_gap'])} before, **{_usd(t['gap_with_plan'])}** with the plan.",
            "",
        ]
    out += [
        f"Cash cost of the plan in the twelve months: {_cost(s['cash_cost_in_twelve_months'])} ({s['cost_note']}).",
        "",
    ]
    r = s["ranges"]
    out += [
        f"Bookings with the plan, simulated ({r['status']}; {r['draws']} draws, drawing {r['what_is_drawn']}):",
        "",
    ]
    out += _table(
        ["Window", "Median", "80% range", "95% range"],
        [
            (h, _usd(v["median"]), _rng(v["range80"]), _rng(v["range95"]))
            for h, v in r["bookings_in_window"].items()
        ],
    )
    out += [
        f"Fiscal-year expected with the plan, 80% range: {_rng(r['fiscal_year_expected_range80'])}.",
        "",
    ]
    return out


def _cost(x) -> str:
    return "cost not entered" if x is None else _usd(x)


def _actions(s: dict) -> list[str]:
    if "unavailable" in s:
        return [
            "## 12. Two actions, compared",
            "",
            f"Unavailable: the fitted forecast is unavailable ({s['unavailable']}).",
            "",
        ]
    out = [
        "## 12. Two actions, compared",
        "",
        f"{s['definition']} Program shape: {s['program_shape']}.",
        "",
    ]
    rows = []
    for a in s["comparison"]:
        if a["status"] != "valued":
            rows.append([a["action"], a["status"], "", "", "", "", ""])
            continue
        g = a["bookings_gained"]
        rows.append(
            [a["action"], a.get("rank") or ("not ranked: " + a["not_ranked_because"] if a["not_ranked_because"] else ""),
             _usd(g[REST]), _usd(g[NEXT]), a["starts_paying"] or "never inside the window",
             _cost(a["cash_cost_in_twelve_months"]),
             "n/a" if a["gain_per_dollar"] is None else a["gain_per_dollar"]]
        )  # fmt: skip
    out += _table(
        [
            "Action",
            "Rank",
            f"Gains, {REST}",
            f"Gains, {NEXT}",
            "Starts paying",
            "Cash cost inside the twelve months",
            "Gain per dollar",
        ],
        rows,
    )
    c = s["close_the_fiscal_year_gap"]
    out += [
        f"Closing the fiscal-year gap of {_usd(c['fiscal_year_gap'])}: {c['basis']}.",
        "",
    ]
    h, p = c["hires"], c["program"]
    if h["count"] is None and "bound" not in h:
        out += [f"- **Hires:** {h['outcome']}: {h['note']}."]
    elif h["outcome"] == "feasible":
        out += [
            (
                f"- **Hires:** {h['count']} whole hires starting together close it, overshooting by "
                f"{_usd(h['overshoot'])} (fiscal-year bookings {_usd(h['fiscal_year_bookings_with'])}; one "
                f"fewer gives {_usd(h['fiscal_year_bookings_one_fewer'])}); cash cost "
                f"{_cost(h['cash_cost_in_twelve_months'])} in twelve months. Bound {h['bound']}: "
                f"{h['bound_basis']}."
            )
        ]
    elif h["outcome"] == "already covered":
        out += ["- **Hires:** already covered: no hires needed."]
    else:
        out += [
            (
                f"- **Hires:** unreachable within the bound of {h['bound']} ({h['bound_basis']}); "
                f"the best case gives {_usd(h['fiscal_year_bookings_with'])}."
            )
        ]
    if p["outcome"] == "feasible":
        out += [
            (
                f"- **Program pipeline:** feasible: {_usd(p['dollars'], True)} of created pipeline closes "
                f"it (overshoot {_usd(p['overshoot'], True)}); cash cost "
                f"{_cost(p['cash_cost_in_twelve_months'])}; {_pct_str(p['share_booking_in_fiscal_year'])} "
                "of those dollars book by the fiscal-year end."
            )
        ]
    elif p["outcome"] == "already covered":
        out += ["- **Program pipeline:** already covered: nothing needed."]
    else:
        over = (
            f"; it would take {_usd(p['needed_but_over_the_cap'], True)}"
            if p["needed_but_over_the_cap"]
            else ""
        )
        out += [
            f"- **Program pipeline:** unreachable within the cap of {_usd(p['cap'])} ({p['cap_rule']}){over}."
        ]
    out += ["", f"_{_up(s['meaning'])}._", ""]
    return out


def _rate(x: str) -> str:
    return f"{float(x):.2%}"


def _driver_actions(s: dict) -> list[str]:
    if "unavailable" in s:
        return [
            "## 13. Driver actions",
            "",
            f"Unavailable: the fitted forecast is unavailable ({s['unavailable']}).",
            "",
        ]
    if not s["items"]:
        return []
    out = ["## 13. Driver actions", "", s["definition"], ""]
    out += _table(
        ["Action", "Slice", "Starts", "Ramp (months)", "Target", f"{s['removal_label']}, {REST}",
         f"{s['removal_label']}, {NEXT}"],
        [
            (i["name"], i["slice"]["label"], i["start"], i["ramp_months"],
             _rate(i["target"]), _usd(i["removal_value"][REST], True),
             _usd(i["removal_value"][NEXT], True))
            for i in s["items"]
        ],
    )  # fmt: skip
    out += [s["removal_note"], ""]
    for i in s["items"]:
        e = i["evidence"]
        out += [
            (
                f"- **{i['name']}:** {i['affects']} Pooled baseline {_rate(e['baseline_rate'])}, "
                f"{e['change_points']} points, resulting {_rate(e['resulting_rate'])}: "
                f"{e['label']}."
            )
        ]
    out += [""]
    j, rec = s["joint_gain"], s["reconciliation"]
    out += _table(
        ["Gain of all the actions together", REST, NEXT],
        [
            ("Joint gain", _usd(j[REST], True), _usd(j[NEXT], True)),
            ("Joint gain less the sum of the removal values",
             _usd(rec["values"][REST], True), _usd(rec["values"][NEXT], True)),
        ],
    )  # fmt: skip
    out += [rec["sentences"][REST], "", s["rounding_note"], ""]
    wo, wi = s["without_actions"], s["with_actions"]
    out += [
        "The same plan without its driver actions, against with them:",
        "",
    ]
    out += _table(
        ["", "Without", "With"],
        [
            ("Expected fiscal year", _usd(wo["expected_fiscal_year"], True),
             _usd(wi["expected_fiscal_year"], True)),
            (f"Bookings, {REST}", _usd(wo["bookings"][REST], True), _usd(wi["bookings"][REST], True)),
            (f"Bookings, {NEXT}", _usd(wo["bookings"][NEXT], True), _usd(wi["bookings"][NEXT], True)),
            *(
                (f"{a['quarter']} expected", _usd(a["expected"], True), _usd(b["expected"], True))
                for a, b in zip(wo["quarters"], wi["quarters"])
            ),
        ],
    )  # fmt: skip
    out += [s["range_note"], ""]
    return out
