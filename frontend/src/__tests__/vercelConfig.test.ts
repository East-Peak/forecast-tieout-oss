import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const config = JSON.parse(readFileSync(resolve(__dirname, "../../vercel.json"), "utf8")) as {
  rewrites: Array<{ source: string; destination: string }>;
  headers?: Array<{ source: string; headers: Array<{ key: string; value: string }> }>;
};

describe("vercel.json and the plan editor's assets", () => {
  it("never answers a missing editor file with the app's page (a wrong answer would read as a corrupt download)", () => {
    const [{ source }] = config.rewrites;
    const catchAll = new RegExp(`^${source}$`);
    expect(catchAll.test("/editor/abc/pyodide/pyodide.asm.wasm")).toBe(false);
    expect(catchAll.test("/plan")).toBe(true);
  });

  it("lets the editor's files be cached for a year, because their folder is named by a hash of their contents", () => {
    const rule = config.headers?.find((h) => h.source === "/editor/(.*)");
    expect(rule?.headers).toContainEqual({ key: "Cache-Control", value: "public, max-age=31536000, immutable" });
  });
});
