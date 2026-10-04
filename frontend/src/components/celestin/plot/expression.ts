/**
 * The expressions a plot draws: the browser's half of `app/domain/expression.py`.
 * Same grammar, same refusal codes, same NaN-where-undefined values; both pass
 * `__tests__/expression_cases.json` (a byte-identical copy of the backend's
 * table). Change one parser, change the other and the table. Model text is
 * parsed, never run.
 */
export type ExprNode =
  | { k: "num"; v: number }
  | { k: "var" }
  | { k: "neg"; a: ExprNode }
  | { k: "bin"; op: "+" | "-" | "*" | "/" | "^"; a: ExprNode; b: ExprNode }
  | { k: "call"; f: FunctionName; a: ExprNode };
export type ExprErrorCode =
  | "syntax"
  | "unknown_name"
  | "latex"
  | "comma"
  | "equation"
  | "scientific"
  | "ambiguous"
  | "variables"
  | "depth";
export type Parsed = { ok: true; node: ExprNode } | { ok: false; code: ExprErrorCode };

const FUNCTIONS = {
  sqrt: Math.sqrt,
  cbrt: Math.cbrt,
  abs: Math.abs,
  exp: Math.exp,
  ln: Math.log,
  log: Math.log10,
  sin: Math.sin,
  cos: Math.cos,
  tan: Math.tan,
} as const;
type FunctionName = keyof typeof FUNCTIONS;
const CONSTANTS: Record<string, number> = { pi: Math.PI, π: Math.PI, e: Math.E };
export const CURVE_VARIABLES: readonly string[] = ["x", "t"];
export const SEQUENCE_VARIABLES: readonly string[] = ["n"];
// Levels of nesting (parentheses, calls, signs, exponents): the backend's MAX_DEPTH.
export const MAX_DEPTH = 24;
const ALIASES: Record<string, string> = { "−": "-", "·": "*", "×": "*", "⋅": "*" };
const SPACES = " \t\n\r\u00a0\u202f";
const isDigit = (c: string | undefined) =>
  c !== undefined && c.length === 1 && c >= "0" && c <= "9";
const isLetter = (c: string | undefined) => c !== undefined && /^[A-Za-z]$/.test(c);
// Own properties only: `"toString" in FUNCTIONS` is true through the prototype.
const own = (o: object, k: string) => Object.prototype.hasOwnProperty.call(o, k);

class Refused extends Error {
  code: ExprErrorCode;
  constructor(code: ExprErrorCode) {
    super(code);
    this.code = code;
  }
}
type Token = { kind: "num" | "name" | "op" | "end"; text: string };

function tokens(src: string): Token[] {
  const out: Token[] = [];
  let i = 0;
  while (i < src.length) {
    const raw = src[i] as string;
    const c = own(ALIASES, raw) ? (ALIASES[raw] as string) : raw;
    if (SPACES.includes(c)) i += 1;
    else if (isDigit(c)) {
      let j = i;
      while (isDigit(src[j])) j += 1;
      if (src[j] === ".") {
        if (!isDigit(src[j + 1])) throw new Refused("syntax");
        j += 1;
        while (isDigit(src[j])) j += 1;
      }
      // 1e-3, 6.67e-11, 2E5: scientific notation would otherwise read as 1·e − 3.
      if (
        (src[j] === "e" || src[j] === "E") &&
        (isDigit(src[j + 1]) || (["+", "-", "−"].includes(src[j + 1] ?? "") && isDigit(src[j + 2])))
      )
        throw new Refused("scientific");
      out.push({ kind: "num", text: src.slice(i, j) });
      i = j;
    } else if (c === "π") {
      out.push({ kind: "name", text: c });
      i += 1;
    } else if (isLetter(c)) {
      let j = i + 1;
      while (isLetter(src[j])) j += 1;
      out.push({ kind: "name", text: src.slice(i, j) });
      i = j;
    } else if ("+-*/^()".includes(c)) {
      out.push({ kind: "op", text: c });
      i += 1;
    } else if ("\\${}".includes(c)) throw new Refused("latex");
    else if (c === ",") throw new Refused("comma");
    else if (c === "=") throw new Refused("equation");
    else throw new Refused("syntax"); // |, ², ³, anything else
  }
  out.push({ kind: "end", text: "" });
  return out;
}

/** The expression's tree, or the refusal code. Never throws. */
export function parseExpression(source: string, variables: readonly string[]): Parsed {
  try {
    const ts = tokens(source);
    let i = 0;
    let depth = 0;
    let seen: string | null = null;
    const peek = () => ts[i] as Token;
    const isOp = (s: string) => peek().kind === "op" && s.includes(peek().text);
    const enter = () => {
      depth += 1;
      if (depth > MAX_DEPTH) throw new Refused("depth");
    };
    const close = () => {
      if (!isOp(")")) throw new Refused("syntax");
      i += 1;
    };
    const sum = (): ExprNode => {
      let node = prod();
      while (isOp("+-")) {
        const op = (ts[i++] as Token).text as "+" | "-";
        node = { k: "bin", op, a: node, b: prod() };
      }
      return node;
    };
    const prod = (): ExprNode => {
      let node = unary();
      let afterDivision = false;
      for (;;) {
        const t = peek();
        if (isOp("*/")) {
          i += 1;
          node = { k: "bin", op: t.text as "*" | "/", a: node, b: unary() };
          afterDivision = t.text === "/";
        } else if (t.kind === "name" || isOp("(")) {
          if (afterDivision) throw new Refused("ambiguous");
          node = { k: "bin", op: "*", a: node, b: power() };
        } else return node;
      }
    };
    const unary = (): ExprNode => {
      if (!isOp("+-")) return power();
      const op = (ts[i++] as Token).text;
      enter();
      const a = unary();
      depth -= 1;
      return op === "-" ? { k: "neg", a } : a;
    };
    const power = (): ExprNode => {
      const base = atom();
      if (!isOp("^")) return base;
      i += 1;
      enter();
      const b = unary();
      depth -= 1;
      return { k: "bin", op: "^", a: base, b };
    };
    const atom = (): ExprNode => {
      const t = peek();
      if (t.kind === "num") {
        i += 1;
        return { k: "num", v: Number(t.text) };
      }
      if (isOp("(")) {
        i += 1;
        enter();
        const a = sum();
        depth -= 1;
        close();
        return a;
      }
      if (t.kind !== "name") throw new Refused("syntax");
      i += 1;
      if (own(FUNCTIONS, t.text)) {
        if (!isOp("(")) throw new Refused("syntax");
        i += 1;
        enter();
        const a = sum();
        depth -= 1;
        close();
        return { k: "call", f: t.text as FunctionName, a };
      }
      if (own(CONSTANTS, t.text)) return { k: "num", v: CONSTANTS[t.text] as number };
      if (variables.includes(t.text)) {
        if (seen !== null && seen !== t.text) throw new Refused("variables");
        seen = t.text;
        return { k: "var" };
      }
      throw new Refused("unknown_name");
    };
    if (peek().kind === "end") throw new Refused("syntax");
    const node = sum();
    if (peek().kind !== "end") throw new Refused("syntax");
    return { ok: true, node };
  } catch (error) {
    if (error instanceof Refused) return { ok: false, code: error.code };
    return { ok: false, code: "syntax" }; // never throw into React (a stack overflow, say)
  }
}

const fin = (v: number) => (Number.isFinite(v) ? v : NaN);

/** The expression at `v`, NaN where it is undefined. Never throws. */
export function evaluate(node: ExprNode, v: number): number {
  switch (node.k) {
    case "num":
      return node.v;
    case "var":
      return v;
    case "neg":
      return -evaluate(node.a, v);
    case "call": {
      const a = evaluate(node.a, v);
      return Number.isNaN(a) ? NaN : fin(FUNCTIONS[node.f](a));
    }
    case "bin": {
      const a = evaluate(node.a, v);
      const b = evaluate(node.b, v);
      if (Number.isNaN(a) || Number.isNaN(b)) return NaN;
      switch (node.op) {
        case "+":
          return fin(a + b);
        case "-":
          return fin(a - b);
        case "*":
          return fin(a * b);
        case "/":
          return b === 0 ? NaN : fin(a / b);
        case "^":
          return fin(Math.pow(a, b));
      }
    }
  }
}

/** The model's limit on an expression (`Expr` in `app/domain/plot.py`). */
export const MAX_EXPRESSION = 120;

/**
 * A function of one number, or null when the expression is refused. A stored
 * expression longer than the model may write is refused too: a long enough
 * `x+x+…` would nest `evaluate` deeper than the stack.
 */
export function compileExpression(
  source: unknown,
  variables: readonly string[],
): ((v: number) => number) | null {
  if (typeof source !== "string" || source.length > MAX_EXPRESSION) return null;
  const parsed = parseExpression(source, variables);
  return parsed.ok ? (v: number) => evaluate(parsed.node, v) : null;
}
