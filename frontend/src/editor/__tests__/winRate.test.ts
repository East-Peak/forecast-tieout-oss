import { describe, expect, it } from "vitest";
import * as files from "../../screens/__tests__/files";
import { driverReading, winRateReading } from "../winRate";

describe("what a draft action starts from, read from the worksheet", () => {
  it("is the pooled rate and the worksheet's high setting, as the report writes them", () => {
    const r = files.fixture("../fixtures/your-plan-actions/report.json");
    expect(winRateReading(r)).toEqual({ present: true, baseline: "0.2193", favorable: "0.2220" });
  });

  it("is nothing where the worksheet cannot be built", () => {
    const r = structuredClone(files.report("sapling-industries", "as-signed"));
    (r as { worksheet: unknown }).worksheet = { unavailable: "no worksheet" };
    expect(winRateReading(r)).toEqual({ present: false, baseline: null, favorable: null });
  });

  it("has a baseline but no favorable end where the history offers no settings", () => {
    const r = structuredClone(files.report("sapling-industries", "as-signed"));
    const sheet = r.worksheet as { drivers: Array<{ driver: string; historical: unknown }> };
    sheet.drivers.find((d) => d.driver === "win_rate")!.historical = null;
    const got = winRateReading(r);
    expect(got.present).toBe(true);
    expect(got.baseline).not.toBeNull();
    expect(got.favorable).toBeNull();
  });
});

describe("the same reading for the other drivers an action can change", () => {
  const r = files.fixture("../fixtures/your-plan-three-drivers/report.json");

  it("is each driver's pooled value and worksheet high, as the report writes them", () => {
    expect(driverReading(r, "win_rate")).toEqual({ present: true, baseline: "0.2193", favorable: "0.2220" });
    expect(driverReading(r, "won_arr")).toMatchObject({ present: true, baseline: "413835.73", favorable: "605308.57" });
    expect(driverReading(r, "productivity")).toMatchObject({ present: true, baseline: "2.0662", favorable: "2.4056" });
  });

  it("is nothing where the worksheet cannot be built", () => {
    const none = structuredClone(r);
    (none as { worksheet: unknown }).worksheet = { unavailable: "no worksheet" };
    expect(driverReading(none, "won_arr")).toEqual({ present: false, baseline: null, favorable: null });
  });
});
