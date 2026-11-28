"""Counterexamples from the adversarial review of tranche 2a. Each test names the wrong number it once allowed."""

import pytest

from engine.harness.catalog import load_catalog
from engine.harness.evidence import load
from engine.harness.query import (
    ESTIMATORS,
    PROVIDERS,
    Estimate,
    query,
    records,
    register_estimator,
    register_provider,
)
from engine.harness.tests.test_evidence_support import (
    lead,
    lh,
    ohist,
    opp,
    write_extract,
)
from engine.harness.tests.test_query_dimensions import account
from engine.harness.tests.test_query_support import D, by_key, catalog_text, values

W = (D("2025-01-01"), D("2025-06-30"))
T = D("2025-06-30")


def ask(estate, cat, metric, group_by=(), window=W, as_of=T, **kw):
    return query(
        estate, cat, metric, group_by, kw.pop("filters", None), window, as_of, **kw
    )


def build(
    root,
    opps=(),
    ohists=(),
    accounts=(),
    leads=(),
    lhists=(),
    ofhs=(),
    when="2025-06-30T23:00:00Z",
):
    objects = {
        "Opportunity": list(opps), "OpportunityHistory": list(ohists), "OpportunityFieldHistory": list(ofhs),
        "Lead": list(leads), "LeadHistory": list(lhists), "Account": list(accounts), "Campaign": [], "CampaignMember": [],
    }  # fmt: skip
    return load([write_extract(root, when, "salesforce", objects)])


# 1 ---- nothing after T -----------------------------------------------------------------------------------


def test_bookings_without_a_window_stop_at_t(estate, cat):
    # the March 31 view of estate A used to include April's deal: 3,900,000
    (cell,) = query(estate, cat, "bookings", [], None, None, D("2025-03-31"))
    assert cell.value == 2_400_000
    assert (
        ask(estate, cat, "won_deals", window=None, as_of=D("2025-03-31"))[0].value == 1
    )


def test_a_cohort_outcome_counts_only_when_it_closed_by_t(estate, cat):
    no_maturity = load_catalog(
        catalog_text().replace("    maturity_days: 90\n    min_denominator: 1\n", "")
    )
    (cell,) = ask(
        estate,
        no_maturity,
        "win_rate",
        window=(D("2025-01-01"), D("2025-03-31")),
        as_of=D("2025-03-31"),
    )
    # O2 won on 04-25 and O3 lost on 05-12, both after T: only O1 (03-14) was decided
    assert (cell.numerator, cell.denominator) == (1, 1)


# 2 ---- a cleared amount is cleared -----------------------------------------------------------------------


def test_a_cleared_amount_does_not_resurrect_the_previous_value(tmp_path, cat):
    deal = opp("006N1", StageName="Proposal", Amount=None, CloseDate="2025-09-30")
    history = [
        ohist(
            "008N1", "006N1", "Discovery", 1000.0, "2025-09-30", "2025-01-05T09:00:00Z"
        ),
        ohist("008N2", "006N1", "Proposal", None, "2025-09-30", "2025-02-01T09:00:00Z"),
    ]
    estate = build(tmp_path, [deal], history)
    (cents,) = query(
        estate, cat, "open_pipeline_cents", [], None, None, D("2025-03-01")
    )
    assert (
        cents.value == 0
        and cents.contract.completeness == "incomplete"
        and cents.contract.bound == "lower_bound"
    )
    (deals,) = query(
        estate, cat, "open_pipeline_deals", [], None, None, D("2025-03-01")
    )
    assert deals.value == 1


# 3 ---- the conversion is the lead's, not the opportunity's creation ---------------------------------------


def conversion_estate(root):
    deal = opp("006C1", CreatedDate="2025-02-03T09:00:00Z", AccountId="001C1")
    converted = lead(
        "00QC1", MQL_Date__c="2025-01-25", IsConverted=True, ConvertedDate="2025-06-01",
        ConvertedOpportunityId="006C1", CreatedDate="2025-01-02T09:00:00Z",
    )  # fmt: skip
    history = [
        lh("00hC1", "00QC1", "MQL_Date__c", None, "2025-01-25", "2025-01-25T09:00:00Z")
    ]
    return build(root, [deal], [ohist("008C1", "006C1", "Discovery", 1000.0, "2025-09-30", "2025-02-03T09:00:00Z")],
                 [account("001C1", "Tier 1", "2025-01-01T09:00:00Z")], [converted], history)  # fmt: skip


def test_a_late_conversion_into_an_old_opportunity_is_not_a_nine_day_conversion(
    tmp_path, cat
):
    estate = conversion_estate(tmp_path)
    (rate,) = ask(estate, cat, "mql_to_opportunity")
    assert (rate.numerator, rate.denominator) == (
        0,
        1,
    )  # converted on 06-01, 127 days after the MQL
    (lag,) = ask(estate, cat, "mql_to_opportunity_lag")
    assert lag.value is None and lag.denominator == 0


def test_rate_rows_contribute_one_each_and_lag_rows_carry_days(estate, cat):
    (rate,) = ask(estate, cat, "mql_to_opportunity")
    assert [r.value for r in records(estate, cat, rate, "numerator")] == [1, 1]
    (lag,) = ask(estate, cat, "mql_to_opportunity_lag")
    assert sorted(r.value for r in records(estate, cat, lag)) == [4, 9]


# 4 ---- applicability never hides rows -------------------------------------------------------------------


def applicability_estate(root):
    leads = [
        lead("00QA1", LeadSource="Outbound", MQL_Date__c="2025-02-01"),
        lead("00QA2", LeadSource="Web", MQL_Date__c="2025-02-02"),
    ]
    history = [lh("00hA1", "00QA1", "MQL_Date__c", None, "2025-02-01", "2025-02-01T09:00:00Z"), lh("00hA2", "00QA2", "MQL_Date__c", None, "2025-02-02", "2025-02-02T09:00:00Z")]  # fmt: skip
    return build(root, leads=leads, lhists=history)


def test_mqls_in_an_inapplicable_member_still_reconcile(tmp_path):
    cat = load_catalog(catalog_text())
    estate = applicability_estate(tmp_path)
    (whole,) = ask(estate, cat, "mqls")
    cells = by_key(ask(estate, cat, "mqls", ["source"]))
    assert whole.value == 2
    assert sum(c.value for c in cells.values() if c.value is not None) == 2
    hit = cells[("BDR Outbound",)]
    assert (
        hit.applicability == "not_applicable"
        and hit.value == 1
        and "reconciliation" in hit.contract.flags
    )
    assert (
        cells[("Partner",)].value is None
    )  # no rows: no business meaning, nothing to reconcile
    (filtered,) = ask(estate, cat, "mqls", filters={"source": ["BDR Outbound"]})
    assert filtered.applicability == "not_applicable" and filtered.value == 1


# 5 ---- completeness is not a bound -------------------------------------------------------------------------


def test_win_rate_with_an_unknown_type_is_incomplete_not_a_lower_bound(tmp_path, cat):
    won = opp(
        "006W1",
        CreatedDate="2025-01-05T09:00:00Z",
        StageName="Closed Won",
        Amount=1000.0,
        CloseDate="2025-02-10",
    )
    lost = opp(
        "006W2",
        CreatedDate="2025-01-06T09:00:00Z",
        StageName="Closed Lost",
        Amount=1000.0,
        CloseDate="2025-02-11",
    )
    history = [
        ohist("008W1", "006W1", "Closed Won", 1000.0, "2025-02-10", "2025-02-10T09:00:00Z"),
        ohist("008W2", "006W2", "Closed Lost", 1000.0, "2025-02-11", "2025-02-11T09:00:00Z"),
        ohist("008W3", "006W3", "Closed Lost", 1000.0, "2025-02-12", "2025-02-12T09:00:00Z"),
    ]  # fmt: skip
    estate = build(
        tmp_path, [won, lost], history
    )  # 006W3 is known from its history alone: its Type was never seen
    (rate,) = ask(estate, cat, "win_rate")
    assert (rate.numerator, rate.denominator) == (1, 2)
    assert rate.contract.completeness == "incomplete" and rate.contract.bound is None
    assert rate.contract.incomplete == {"unknown_membership": 1}
    (bookings,) = ask(estate, cat, "bookings")
    assert (
        bookings.contract.bound == "exact"
        and bookings.contract.completeness == "complete"
    )


# 6 ---- rollups over the whole member by period population ------------------------------------------------------


def test_a_rollup_member_with_no_bookings_averages_zero_over_the_eligible_periods(
    estate, cat
):
    cells = by_key(
        ask(
            estate,
            cat,
            "bookings_monthly_average",
            ["segment"],
            window=(D("2025-01-15"), T),
        )
    )
    enterprise = cells[("Enterprise",)]
    assert (
        enterprise.value == 0
        and enterprise.denominator == 5
        and enterprise.availability == "measured"
    )
    assert enterprise.contract.excluded == {
        "partial_period": 1
    }  # January starts on the 15th
    assert cells[("SMB",)].value == pytest.approx(3_200_000 / 5)


# 7 ---- lineage pins what was used --------------------------------------------------------------------------------


def test_records_replay_the_pinned_versions_not_the_current_default(estate):
    text = catalog_text()
    two = text.replace("plan_grain:", """  - {id: bookings, version: "2", label: Bookings, unit: count, population: p, basis: period, kind: sum, measure: won_deals, aggregation: additive, dimensions: [month], favorable: up, owner: o, definition: d.}
plan_grain:""", 1)  # fmt: skip
    cat = load_catalog(two)
    (old,) = ask(estate, cat, "bookings", metric_version="1")
    pins = old.contract.lineage.handle
    assert pins["metric_version"] == "1" and pins["catalog_hash"] == cat.content_hash
    assert (
        sum(r.value for r in records(estate, cat, old)) == 5_900_000
    )  # not the version-2 count
    (rolled,) = ask(estate, cat, "bookings_monthly_average", metric_version=None)
    assert (
        rolled.contract.lineage.handle["dependencies"] == {"of": ["bookings", "2"]}
        or "dependencies" in rolled.contract.lineage.handle
    )


def test_records_refuse_when_the_catalog_changed_and_the_pin_is_gone(estate, cat):
    cell = ask(estate, cat, "bookings", ["segment"])[0]
    changed = load_catalog(
        catalog_text().replace(
            "version: v1\n          adopted_on: 2025-01-01",
            "version: v7\n          adopted_on: 2025-01-01",
        )
    )
    assert changed.content_hash != cat.content_hash
    with pytest.raises(ValueError, match="no longer present"):
        records(estate, changed, cell)
    assert records(estate, cat, cell) is not None


# 8 ---- an empty closed-period population is explicit --------------------------------------------------------------


def test_a_rollup_with_no_closed_period_reads_no_history(estate, cat):
    (cell,) = ask(
        estate,
        cat,
        "bookings_monthly_average",
        window=(D("2025-06-01"), D("2025-06-15")),
        as_of=D("2025-06-15"),
    )
    assert cell.value is None and cell.availability_reason == "no_closed_period"
    assert cell.contract.excluded == {"open_period": 1}
    assert records(estate, cat, cell) == []


# 9 ---- a known historical NULL is Unknown, not today's value ---------------------------------------------------------


def test_a_known_null_tier_is_unknown_not_the_current_tier(tmp_path, cat):
    deal = opp(
        "006K1",
        AccountId="001K1",
        CreatedDate="2025-01-05T09:00:00Z",
        StageName="Closed Won",
        Amount=1000.0,
        CloseDate="2025-02-10",
    )
    history = [
        ohist(
            "008K1", "006K1", "Closed Won", 1000.0, "2025-02-10", "2025-02-10T09:00:00Z"
        )
    ]
    first = write_extract(tmp_path, "2025-03-01T23:00:00Z", "salesforce", {
        "Opportunity": [deal], "OpportunityHistory": history, "OpportunityFieldHistory": [], "Lead": [], "LeadHistory": [],
        "Account": [account("001K1", None, "2024-12-01T09:00:00Z")]})  # fmt: skip
    second = write_extract(tmp_path, "2025-06-30T23:00:00Z", "salesforce", {
        "Opportunity": [deal], "OpportunityHistory": history, "OpportunityFieldHistory": [], "Lead": [], "LeadHistory": [],
        "Account": [account("001K1", "Tier 2", "2024-12-01T09:00:00Z")]})  # fmt: skip
    cells = by_key(ask(load([first, second]), cat, "bookings", ["segment"]))
    assert cells[("Unknown",)].value == 100_000 and cells[("Mid-Market",)].value == 0
    assert "attribute_fallback_current" not in cells[("Unknown",)].contract.flags


# 10 ---- estimators see the evidence's uncertainty --------------------------------------------------------------------

POOLED = """  - id: pooled_win_rate
    version: "1"
    label: Pooled win rate
    unit: ratio
    population: decided deals
    basis: cohort
    kind: estimator
    estimator: meta_rate
    inputs: {successes: cohort_won, trials: cohort_decided}
    aggregation: non_additive
    dimensions: [segment]
    favorable: up
    owner: Sales Operations
    definition: Pools the inputs.
  - id: win_rate
"""


def test_estimators_receive_input_metadata_and_must_declare_completeness(
    estate, request
):
    cat = load_catalog(catalog_text().replace("  - id: win_rate\n", POOLED, 1))
    seen = {}

    def meta(inputs, params):
        seen.update(next(iter(inputs.values())))
        return {
            k: Estimate(
                0.5, 1, 2, "pooled", completeness="incomplete", provenance="test"
            )
            for k in inputs
        }

    register_estimator("meta_rate", meta)
    request.addfinalizer(lambda: ESTIMATORS.pop("meta_rate", None))
    cells = ask(estate, cat, "pooled_win_rate", ["segment"])
    assert (
        seen["successes"].completeness == "complete"
        and seen["trials"].excluded == {}
        and seen["trials"].counts == {}
    )
    assert {c.contract.completeness for c in cells} == {"incomplete"}
    assert (
        max(c.contract.eligible for c in cells) <= 5
    )  # overlapping inputs are not summed
    with pytest.raises(TypeError):
        Estimate(0.5)  # completeness and provenance are required


# 11 ---- providers get the requested horizon ----------------------------------------------------------------------------


def test_a_plan_request_keeps_its_horizon_and_the_resolved_versions(
    estate, cat, request
):
    got = []
    register_provider("plan", lambda req: got.append(req) or [])
    request.addfinalizer(lambda: PROVIDERS.pop("plan", None))
    ask(
        estate,
        cat,
        "bookings",
        ["segment"],
        window=(D("2026-01-01"), D("2026-12-31")),
        kind="plan",
        plan_version="FY26",
    )
    (req,) = got
    assert req.window == (D("2026-01-01"), D("2026-12-31"))
    assert req.metric_version == "1" and req.mapping_versions == {"segment": "v1"}


# 12 ---- the fiscal calendar ------------------------------------------------------------------------------------------------


def test_fiscal_quarters_and_years_follow_the_calendar_section(estate, cat):
    assert cat.calendar.fiscal_year_start_month == 2
    quarters = values(ask(estate, cat, "bookings", ["fiscal_quarter"]))
    assert quarters == {
        ("FY24-Q4",): 0,
        ("FY25-Q1",): 3_900_000,
        ("FY25-Q2",): 2_000_000,
    }
    years = values(ask(estate, cat, "bookings", ["fiscal_year"]))
    assert years == {("FY24",): 0, ("FY25",): 5_900_000}
    calendar = values(ask(estate, cat, "bookings", ["calendar_quarter"]))
    assert calendar == {("2025-Q1",): 2_400_000, ("2025-Q2",): 3_500_000}


def test_a_rollup_closes_fiscal_periods_by_the_calendar(estate, cat):
    (cell,) = ask(
        estate, cat, "bookings_quarterly_average", window=(D("2025-02-01"), T)
    )
    assert (
        cell.value == 3_900_000 and cell.denominator == 1
    )  # FY25-Q2 ends 07-31: still open
    assert cell.contract.excluded == {"open_period": 1}
    with pytest.raises(Exception, match="grain"):
        load_catalog(
            catalog_text().replace("grain: fiscal_quarter", "grain: fortnight")
        )


# 14 ---- the metrics the snapshot builder needs ------------------------------------------------------------------------------


def test_lost_deals_leads_created_and_demand_by_outcome_month(estate, cat):
    lost = values(ask(estate, cat, "lost_deals", ["month"]))
    assert {k: v for k, v in lost.items() if v} == {
        ("2025-05",): 1
    }  # O3; O8's April loss was reopened
    created = values(ask(estate, cat, "leads_created", ["month"]))
    assert (
        created[("2025-01",)] == 2
        and created[("2025-03",)] == 4
        and created[("2025-04",)] == 2
        and sum(created.values()) == 8
    )
    admitted = values(ask(estate, cat, "demand_admitted_by_outcome", ["month"]))
    assert {k: v for k, v in admitted.items() if v} == {
        ("2025-01",): 1,
        ("2025-02",): 1,
        ("2025-03",): 1,
        ("2025-04",): 1,
    }
    rejected = values(ask(estate, cat, "demand_rejected_by_outcome", ["month"]))
    expired = values(ask(estate, cat, "demand_expired_by_outcome", ["month"]))
    assert {k: v for k, v in rejected.items() if v} == {("2025-03",): 1}
    assert {k: v for k, v in expired.items() if v} == {("2025-04",): 1, ("2025-06",): 1}
