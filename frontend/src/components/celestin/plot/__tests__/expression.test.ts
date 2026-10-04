import { describe, expect, it } from "vitest";
import {
  compileExpression,
  CURVE_VARIABLES,
  evaluate,
  MAX_DEPTH,
  MAX_EXPRESSION,
  parseExpression,
  SEQUENCE_VARIABLES,
} from "../expression";
import table from "./expression_cases.json";

/**
 * The same table as the backend's `tests/fixtures/expression_cases.json` (the
 * backend checks the two copies are byte-identical): both parsers agree on every
 * value and every refusal.
 */
type Case =
  | { src: string; vars: string[]; at: [number, number | null][] }
  | { src: string; vars: string[]; error: string };

const CASES = table.cases as Case[];

describe("the shared expression table", () => {
  it("has every case the backend runs", () => {
    expect(CASES.length).toBeGreaterThanOrEqual(96);
  });

  it.each(CASES.map((c) => [c.src, c] as const))("%j", (_, c) => {
    const parsed = parseExpression(c.src, c.vars);
    if ("error" in c) {
      expect(parsed).toEqual({ ok: false, code: c.error });
      return;
    }
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    for (const [v, expected] of c.at) {
      const got = evaluate(parsed.node, v);
      if (expected === null) expect(Number.isFinite(got)).toBe(false);
      else
        expect(Math.abs(got - expected)).toBeLessThanOrEqual(
          1e-9 * Math.max(1, Math.abs(expected)),
        );
    }
  });
});

describe("compileExpression", () => {
  it("compiles a curve and a sequence", () => {
    expect(compileExpression("x^2-4", CURVE_VARIABLES)?.(3)).toBe(5);
    expect(compileExpression("2+3(n-1)", SEQUENCE_VARIABLES)?.(6)).toBe(17);
  });

  it("refuses what the backend refuses, and what is not a string", () => {
    expect(compileExpression("1/2x", CURVE_VARIABLES)).toBeNull();
    expect(compileExpression("2x-1", SEQUENCE_VARIABLES)).toBeNull();
    expect(compileExpression(42, CURVE_VARIABLES)).toBeNull();
    expect(compileExpression(null, CURVE_VARIABLES)).toBeNull();
    expect(compileExpression({ toString: () => "x" }, CURVE_VARIABLES)).toBeNull();
  });

  it("refuses an expression longer than the model may write, before it can nest too deep", () => {
    const long = Array.from({ length: 5000 }, () => "x").join("+");
    expect(compileExpression(long, CURVE_VARIABLES)).toBeNull();
    expect(compileExpression("x".padEnd(MAX_EXPRESSION, " "), CURVE_VARIABLES)).not.toBeNull();
    expect(compileExpression("x".padEnd(MAX_EXPRESSION + 1, " "), CURVE_VARIABLES)).toBeNull();
  });

  it("never looks names up through the prototype chain", () => {
    for (const name of [
      "toString(x)",
      "constructor",
      "__proto__",
      "hasOwnProperty(x)",
      "valueOf",
    ]) {
      expect(compileExpression(name, CURVE_VARIABLES)).toBeNull();
    }
  });
});

describe("evaluate", () => {
  it("never throws, and is NaN where the expression is undefined", () => {
    for (const c of CASES) {
      const parsed = parseExpression(c.src, c.vars);
      if (!parsed.ok) continue;
      for (const v of [-1e308, -800, -1, 0, 1, 800, 1e308, Number.NaN]) {
        expect(() => evaluate(parsed.node, v)).not.toThrow();
      }
    }
    const f = compileExpression("1/x", CURVE_VARIABLES);
    expect(f?.(0)).toBeNaN();
  });

  it.each([
    ["parentheses", (k: number) => "(".repeat(k) + "x" + ")".repeat(k)],
    ["calls", (k: number) => "sqrt(".repeat(k) + "x" + ")".repeat(k)],
    ["signs", (k: number) => "-".repeat(k) + "x"],
    ["exponents", (k: number) => "2^".repeat(k) + "x"],
  ] as const)("parses %s nested exactly 24 deep and refuses 25", (_, nest) => {
    // The backend's limit too (test_expression.py): what the tool accepts, the board draws.
    expect(MAX_DEPTH).toBe(24);
    expect(parseExpression(nest(MAX_DEPTH), CURVE_VARIABLES).ok).toBe(true);
    expect(parseExpression(nest(MAX_DEPTH + 1), CURVE_VARIABLES)).toEqual({
      ok: false,
      code: "depth",
    });
  });

  it("never throws when parsing hostile input", () => {
    const deep = "(".repeat(10_000) + "x" + ")".repeat(10_000);
    expect(parseExpression(deep, CURVE_VARIABLES)).toEqual({ ok: false, code: "depth" });
    expect(() => parseExpression("-".repeat(10_000) + "x", CURVE_VARIABLES)).not.toThrow();
  });
});
