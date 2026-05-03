/**
 * Shared snapshot fixtures for targetSetter lib tests.
 *
 * All fixtures are synthetic — no real customer data.
 * Calendar labels (Q1FY26, Q1FY27, etc.) are only used in test fixtures,
 * never in production module code.
 */
import type { Snapshot } from "../../../types/snapshot";

/** Minimal snapshot factory: months + quarter_by_month + overridable_quarters */
export const snap = (
  months: string[],
  quarterByMonth: string[],
  overridable: string[] = [],
): Snapshot =>
  ({
    scenario_building_blocks: {
      months,
      quarter_by_month: quarterByMonth,
      overridable_quarters: overridable,
    },
  } as any);

/**
 * Acme FY26 — 4-quarter, Feb-start fiscal year.
 * Q1FY26 is locked (not in overridable_quarters).
 */
export const acmeFY26 = (): Snapshot =>
  snap(
    [
      "2026-02-01", "2026-03-01", "2026-04-01",
      "2026-05-01", "2026-06-01", "2026-07-01",
      "2026-08-01", "2026-09-01", "2026-10-01",
      "2026-11-01", "2026-12-01", "2027-01-01",
    ],
    [
      "Q1FY26", "Q1FY26", "Q1FY26",
      "Q2FY26", "Q2FY26", "Q2FY26",
      "Q3FY26", "Q3FY26", "Q3FY26",
      "Q4FY26", "Q4FY26", "Q4FY26",
    ],
    ["Q2FY26", "Q3FY26", "Q4FY26"], // Q1FY26 locked
  );

/**
 * 5-quarter snapshot (Q4FY25 + Q1–Q4FY26).
 * Overridable: Q1FY26 through Q4FY26 (Q4FY25 is locked prior-year).
 */
export const fiveQuarterFixture = (): Snapshot =>
  snap(
    [
      "2025-11-01", "2025-12-01", "2026-01-01",
      "2026-02-01", "2026-03-01", "2026-04-01",
      "2026-05-01", "2026-06-01", "2026-07-01",
      "2026-08-01", "2026-09-01", "2026-10-01",
      "2026-11-01", "2026-12-01", "2027-01-01",
    ],
    [
      "Q4FY25", "Q4FY25", "Q4FY25",
      "Q1FY26", "Q1FY26", "Q1FY26",
      "Q2FY26", "Q2FY26", "Q2FY26",
      "Q3FY26", "Q3FY26", "Q3FY26",
      "Q4FY26", "Q4FY26", "Q4FY26",
    ],
    ["Q1FY26", "Q2FY26", "Q3FY26", "Q4FY26"],
  );

/**
 * Mighty Oak FY27 — 4-quarter, April-start fiscal year.
 * Q1FY27 = Apr-Jun 2026, Q2FY27 = Jul-Sep 2026, Q3FY27 = Oct-Dec 2026, Q4FY27 = Jan-Mar 2027.
 * Q1FY27 is locked.
 */
export const mightyOakFY27 = (): Snapshot =>
  snap(
    [
      "2026-04-01", "2026-05-01", "2026-06-01",
      "2026-07-01", "2026-08-01", "2026-09-01",
      "2026-10-01", "2026-11-01", "2026-12-01",
      "2027-01-01", "2027-02-01", "2027-03-01",
    ],
    [
      "Q1FY27", "Q1FY27", "Q1FY27",
      "Q2FY27", "Q2FY27", "Q2FY27",
      "Q3FY27", "Q3FY27", "Q3FY27",
      "Q4FY27", "Q4FY27", "Q4FY27",
    ],
    ["Q2FY27", "Q3FY27", "Q4FY27"], // Q1FY27 locked
  );
