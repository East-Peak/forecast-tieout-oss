import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

// The images `npm run screenshots` writes: the README's pictures and the Open Graph image.
const frontend = resolve(__dirname, "../..");
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
    expect(images).toEqual(["og-forecast-sapling.png", "og-forecast-sapling.png"]);
    expect(pngSize(resolve(publicDir, "og-forecast-sapling.png"))).toEqual([1200, 630]);
  });
});
