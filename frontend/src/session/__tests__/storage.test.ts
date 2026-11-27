import { afterEach, describe, expect, it, vi } from "vitest";
import { STORAGE_KEY, readStoredSelection, writeStoredSelection } from "../storage";

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("the remembered company and scenario", () => {
  it("uses a new key, not the old snapshot session's", () => {
    expect(STORAGE_KEY).toBe("forecast-tieout:report-session:v1");
    expect(STORAGE_KEY).not.toMatch(/snapshot|planning/i);
  });
  it("round-trips", () => {
    writeStoredSelection({ company: "a", scenario: "demo-plan" });
    expect(readStoredSelection()).toEqual({ company: "a", scenario: "demo-plan" });
  });
  it("reads nothing from damaged or foreign content", () => {
    localStorage.setItem(STORAGE_KEY, "{not json");
    expect(readStoredSelection()).toBeNull();
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ company: 3 }));
    expect(readStoredSelection()).toBeNull();
  });
  it("works without storage at all: reads null, writes nothing, throws nothing", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readStoredSelection()).toBeNull();
    expect(() => writeStoredSelection({ company: "a", scenario: "x" })).not.toThrow();
  });
});
