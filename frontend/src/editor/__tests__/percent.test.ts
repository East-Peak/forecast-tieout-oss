import { describe, expect, it } from "vitest";
import { percentText, probabilityOf } from "../percent";

describe("a target typed as a percent becomes the probability the core reads, by moving the point, never by calculating", () => {
  it.each([
    ["26", "0.26"],
    ["26.5", "0.265"],
    ["5", "0.05"],
    ["0", "0.00"],
    ["100", "1.00"],
    ["0.5", "0.005"],
    [" 22.2 ", "0.222"],
    ["22.", "0.22"],
    [".5", "0.005"],
  ])("%s percent is %s", (typed, probability) => {
    expect(probabilityOf(typed)).toBe(probability);
  });

  it.each(["", "abc", "1e2", "-3", "2 6", "1,5"])("%j is passed on as it was typed, for the core to refuse in its own words", (typed) => {
    expect(probabilityOf(typed)).toBe(typed.trim());
  });
});

describe("a probability shown as the percent the visitor types", () => {
  it.each([
    ["0.26", "26"],
    ["0.2600", "26"],
    ["0.2193", "21.93"],
    ["0.005", "0.5"],
    ["0.05", "5"],
    ["1", "100"],
    ["1.00", "100"],
    ["0", "0"],
    ["0.0", "0"],
    [".5", "50"],
  ])("%s is %s percent", (probability, shown) => {
    expect(percentText(probability)).toBe(shown);
  });

  it("shows a value that is not a plain decimal as it is", () => {
    expect(percentText("abc")).toBe("abc");
    expect(percentText(0.26)).toBe("26");
  });

  it("round-trips what a visitor types", () => {
    for (const typed of ["26", "26.5", "5", "0.5", "100", "0"]) expect(percentText(probabilityOf(typed))).toBe(typed);
  });
});
