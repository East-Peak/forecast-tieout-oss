import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";

/**
 * The gate for "the browser formats and draws; it calculates nothing" (design call 5). Three layers:
 *  1. types: the generated report types brand every decimal string (Money, Decimal) so that arithmetic on
 *     one is a compile error (tsc runs over this file: see the @ts-expect-error lines below);
 *  2. this test parses every source file outside the two approved modules and the tests and fails on any
 *     arithmetic expression, whatever the operands (so a JSON number such as a coverage cannot slip through);
 *  3. a text scan for ways round both: numeric conversion functions, Math, toFixed, BigInt, casts through any,
 *     decimalToNumber outside the chart adapter, and data-binding attributes written outside Bound.
 * What it does not catch: arithmetic written in a test file or the two approved modules (they are the point),
 * a value laundered through JSON.parse or an `any` and then combined by a function in an excluded file, and
 * business figures typed into the source by hand. The digit rule in the screen tests covers that last case at runtime.
 */
const ROOT = resolve(__dirname, "..");
const APPROVED = ["lib/format.ts", "binding/chartData.ts"];
const EXCLUDED = [/\/__tests__\//, /\/generated\//, /test-setup\.ts$/, /vite-env\.d\.ts$/];

function sourceFiles(): string[] {
  const config = ts.readConfigFile(resolve(ROOT, "../tsconfig.json"), ts.sys.readFile);
  const parsed = ts.parseJsonConfigFileContent(config.config, ts.sys, resolve(ROOT, ".."));
  return parsed.fileNames.filter(
    (f) => !EXCLUDED.some((pattern) => pattern.test(f)) && !APPROVED.some((a) => f.endsWith(`/src/${a}`)),
  );
}

const ARITHMETIC = new Set([
  ts.SyntaxKind.MinusToken, ts.SyntaxKind.AsteriskToken, ts.SyntaxKind.SlashToken, ts.SyntaxKind.PercentToken,
  ts.SyntaxKind.AsteriskAsteriskToken, ts.SyntaxKind.MinusEqualsToken, ts.SyntaxKind.AsteriskEqualsToken,
  ts.SyntaxKind.SlashEqualsToken, ts.SyntaxKind.PercentEqualsToken,
]);

function arithmeticIn(fileNames: string[]): string[] {
  const config = ts.readConfigFile(resolve(ROOT, "../tsconfig.json"), ts.sys.readFile);
  const options = ts.parseJsonConfigFileContent(config.config, ts.sys, resolve(ROOT, "..")).options;
  const program = ts.createProgram(fileNames, options);
  const checker = program.getTypeChecker();
  const found: string[] = [];
  const numeric = (node: ts.Node) => {
    const type = checker.getTypeAtLocation(node);
    return (type.flags & (ts.TypeFlags.NumberLike | ts.TypeFlags.BigIntLike)) !== 0;
  };
  for (const file of fileNames) {
    const source = program.getSourceFile(file)!;
    const visit = (node: ts.Node) => {
      const at = () => `${file.replace(`${ROOT}/`, "")}:${source.getLineAndCharacterOfPosition(node.getStart()).line + 1}: ${node.getText().slice(0, 60)}`;
      const line = source.text.split("\n")[source.getLineAndCharacterOfPosition(node.getStart()).line];
      if (line.includes("arithmetic-ok:")) {
        ts.forEachChild(node, visit);
        return;
      }
      if (ts.isBinaryExpression(node)) {
        const op = node.operatorToken.kind;
        if (ARITHMETIC.has(op)) found.push(at());
        else if ((op === ts.SyntaxKind.PlusToken || op === ts.SyntaxKind.PlusEqualsToken) && numeric(node.left) && numeric(node.right)) found.push(at());
      } else if (ts.isPrefixUnaryExpression(node) || ts.isPostfixUnaryExpression(node)) {
        const op = node.operator;
        const bad =
          op === ts.SyntaxKind.PlusToken || op === ts.SyntaxKind.PlusPlusToken || op === ts.SyntaxKind.MinusMinusToken;
        const negation = op === ts.SyntaxKind.MinusToken && !ts.isNumericLiteral((node as ts.PrefixUnaryExpression).operand);
        if (bad || negation) found.push(at());
      }
      ts.forEachChild(node, visit);
    };
    visit(source);
  }
  return found;
}

describe("no arithmetic in the browser outside the formatter and the chart adapter", () => {
  const files = sourceFiles();

  it("scans the app's source", () => {
    expect(files.length).toBeGreaterThan(20);
    expect(files.some((f) => f.endsWith("screens/forecast/ForecastScreen.tsx"))).toBe(true);
    expect(files.some((f) => f.endsWith("lib/format.ts"))).toBe(false);
  });

  it("has no arithmetic expression, of any operands", () => {
    expect(arithmeticIn(files)).toEqual([]);
  });

  it("the scan catches what it is for (a self-test on sample code)", () => {
    const sample = resolve(ROOT, "__tests__/__arithmetic_sample__.ts");
    const code = "export const a = (x: number, y: string) => [x * 2, x - 1, x / 3, +y, x % 2, -x, x + x];\n";
    const host = ts.createCompilerHost({});
    const original = host.getSourceFile.bind(host);
    host.getSourceFile = (name, lang, ...rest) =>
      name === sample ? ts.createSourceFile(name, code, lang) : original(name, lang, ...rest);
    const program = ts.createProgram([sample], { noEmit: true }, host);
    const checker = program.getTypeChecker();
    void checker;
    const found: string[] = [];
    const source = program.getSourceFile(sample)!;
    const walk = (n: ts.Node) => {
      if (ts.isBinaryExpression(n) && (ARITHMETIC.has(n.operatorToken.kind) || n.operatorToken.kind === ts.SyntaxKind.PlusToken)) found.push(n.getText());
      if (ts.isPrefixUnaryExpression(n) && (n.operator === ts.SyntaxKind.PlusToken || n.operator === ts.SyntaxKind.MinusToken)) found.push(n.getText());
      ts.forEachChild(n, walk);
    };
    walk(source);
    expect(found).toEqual(["x * 2", "x - 1", "x / 3", "+y", "x % 2", "-x", "x + x"]);
  });

  it("has no numeric conversion, rounding, Math, BigInt or cast-through-any outside the approved modules", () => {
    const banned = [
      /\bparseFloat\s*\(/, /\bparseInt\s*\(/, /\bNumber\s*\(/, /\.toFixed\s*\(/, /\bMath\./, /\bBigInt\b/,
      /\bas any\b/, /as unknown as number/, /<any>/, /\.toPrecision\s*\(/,
    ];
    const hits = files.flatMap((f) =>
      readFileSync(f, "utf8").split("\n").flatMap((line, i) =>
        !line.includes("arithmetic-ok:") && banned.some((re) => re.test(line.replace(/\/\/.*$/, ""))) ? [`${f.replace(`${ROOT}/`, "")}:${i + 1}: ${line.trim()}`] : [],
      ),
    );
    expect(hits).toEqual([]);
  });

  it("the exemptions are few, each says why, and none touches a report value", () => {
    const marked = files.flatMap((f) =>
      readFileSync(f, "utf8").split("\n").filter((line) => line.includes("arithmetic-ok:")).map((line) => `${f.replace(`${ROOT}/`, "")}: ${line.split("arithmetic-ok:")[1].trim()}`),
    );
    expect(marked).toEqual([
      "binding/pointer.ts: an array index from a pointer, not a report value",
      "session/sessionState.ts: a request counter, not a report value",
    ]);
  });

  it("only the chart adapter turns a report decimal into a number to plot", () => {
    const hits = files.filter((f) => /decimalToNumber/.test(readFileSync(f, "utf8")));
    expect(hits).toEqual([]);
  });

  it("only the binding component writes data-binding attributes", () => {
    const writers = files.filter((f) => /["']data-binding["']|data-binding=/.test(readFileSync(f, "utf8")));
    expect(writers.map((f) => f.replace(`${ROOT}/`, ""))).toEqual(["binding/Bound.tsx"]);
  });
});
