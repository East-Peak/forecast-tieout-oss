import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

// The images `npm run screenshots` writes: the README's pictures and the Open Graph image.
const frontend = resolve(__dirname, "../..");
const repo = resolve(frontend, "..");
const docsDir = resolve(repo, "docs/screenshots");
const publicDir = resolve(frontend, "public/docs/screenshots");
const read = (path: string) => readFileSync(path, "utf8");
const pngSize = (file: string) => {
  const b = readFileSync(file);
  return [b.readUInt32BE(16), b.readUInt32BE(20)];
};
const named = (text: string) => [...text.matchAll(/docs\/screenshots\/([\w.-]+\.png)/g)].map((m) => m[1]);

describe("screenshots and the Open Graph image", () => {
  it("the Open Graph and Twitter images are the 1200 x 630 capture of Forecast", () => {
    const html = read(resolve(frontend, "index.html"));
    const images = named(html);
    expect(images).toEqual(["og-plan-sapling.png", "og-plan-sapling.png"]);
    expect(pngSize(resolve(publicDir, "og-plan-sapling.png"))).toEqual([1200, 630]);
  });

  it("every picture the README shows exists, and the site serves the same bytes", () => {
    const shown = named(read(resolve(repo, "README.md")));
    expect(shown.length).toBeGreaterThan(0);
    for (const file of shown) {
      expect(readdirSync(docsDir)).toContain(file);
      expect(readFileSync(resolve(publicDir, file)).equals(readFileSync(resolve(docsDir, file)))).toBe(true);
    }
  });
});
