import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

// The product is written in American English. The forbidden spellings are built from fragments so this
// file does not contain them; the core has the same check on the reports and its own text.
const BRITISH = new RegExp(
  [
    "\\bprogram" + "me",
    "\\brealis(e|ed|es|ing|ation)\\b",
    "\\bla" + "belled\\b",
    "\\bla" + "belling\\b",
    "\\bcent" + "re",
    "\\bdefen" + "ce\\b",
    "\\bfav" + "our",
    "\\bjudge" + "ment",
    "\\b(normalis|serialis|summaris|organis|recognis|prioritis|standardis|minimis|maximis|utilis|catalogu)(e|ed|es|ing|ation)\\b",
    "\\banalys(e|ed|es|ing)\\b",
    "\\bemphasis(e|ed|es|ing)\\b",
    "\\boptimis(e|ed|es|ing|ation)\\b",
    "\\bbehav" + "iour",
    "\\bcol" + "our",
    "\\bhon" + "our",
    "\\bcheque",
    "\\bgrey\\b",
    "\\bwhilst\\b",
    "\\bamongst\\b",
    "\\bper cent\\b",
    "\\bageing\\b",
    "\\benrol(s|led|ment)?\\b",
    "\\bfulfil(s|ment)?\\b",
    "\\bskilful\\b",
    "\\bcancel" + "led\\b",
    "\\bmodel" + "l(ed|ing)\\b",
    "\\btravel" + "l(ed|ing)\\b",
    "\\blicen" + "ce\\b",
  ].join("|"),
  "i",
);

const frontend = resolve(__dirname, "../..");
const walk = (dir: string): string[] =>
  readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });

describe("American English", () => {
  it("frontend/src, the end-to-end tests and the committed reports contain no British spelling", () => {
    const files = [...walk(join(frontend, "src")), ...walk(join(frontend, "e2e")), ...walk(join(frontend, "public/data/reports"))].filter((f) =>
      /\.(tsx?|json|md|css)$/.test(f),
    );
    expect(files.length).toBeGreaterThan(50);
    const hits = files.flatMap((f) => (readFileSync(f, "utf8").match(new RegExp(BRITISH.source, "gi")) ?? []).map((w) => `${f.replace(frontend, "")}: ${w}`));
    expect(hits).toEqual([]);
  });

  it("the check would catch one", () => {
    expect(BRITISH.test("the " + "program" + "me")).toBe(true);
    expect(BRITISH.test("the program is centered; analysis; color; gray")).toBe(false);
  });
});
