import { describe, expect, it } from "vitest";
import { UnboundPath, resolvePointer } from "../pointer";

const doc = {
  gap: { fiscal_year: { expected: "6119924.84", range80: ["5000000.00", "7000000.00"] } },
  horizons: { "rest of fiscal year": { status: "ok" } },
  methods: [
    { method: "run-rate", by_window: { "2026-09": "1.00" } },
    { method: "fitted model", by_window: { "2026-09": "2.00" } },
  ],
  odd: { "a/b": 1, "c~d": 2 },
  none: null,
};

describe("resolvePointer", () => {
  it("walks objects and array indexes", () => {
    expect(resolvePointer(doc, "/gap/fiscal_year/expected")).toBe("6119924.84");
    expect(resolvePointer(doc, "/gap/fiscal_year/range80/1")).toBe("7000000.00");
  });
  it("reads keys with spaces and the escapes ~1 and ~0", () => {
    expect(resolvePointer(doc, "/horizons/rest of fiscal year/status")).toBe("ok");
    expect(resolvePointer(doc, "/odd/a~1b")).toBe(1);
    expect(resolvePointer(doc, "/odd/c~0d")).toBe(2);
  });
  it("selects an array element by a property, not by its position", () => {
    expect(resolvePointer(doc, "/methods/{method=fitted model}/by_window/2026-09")).toBe("2.00");
    expect(resolvePointer(doc, "/methods/{method=run-rate}/by_window/2026-09")).toBe("1.00");
  });
  it("returns a null the report really holds", () => {
    expect(resolvePointer(doc, "/none")).toBeNull();
  });
  it("throws for a path the report does not have, never a quiet undefined", () => {
    expect(() => resolvePointer(doc, "/gap/fiscal_year/expectd")).toThrow(UnboundPath);
    expect(() => resolvePointer(doc, "/methods/{method=nope}/by_window")).toThrow(UnboundPath);
    expect(() => resolvePointer(doc, "/gap/fiscal_year/range80/5")).toThrow(UnboundPath);
    expect(() => resolvePointer(doc, "/none/x")).toThrow(UnboundPath);
  });
  it("a null the file holds makes what is below it null only when asked to", () => {
    expect(() => resolvePointer(doc, "/none/0")).toThrow(UnboundPath);
    expect(resolvePointer(doc, "/none/0", { nullBelowNull: true })).toBeNull();
    // still an error where the file has no such key at all
    expect(() => resolvePointer(doc, "/gap/nothing/0", { nullBelowNull: true })).toThrow(UnboundPath);
  });
  it("refuses a pointer that does not start at the root", () => {
    expect(() => resolvePointer(doc, "gap")).toThrow(/start with/);
  });
});
