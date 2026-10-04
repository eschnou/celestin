import type { FlowchartBlock, FlowNode, FlowNodeKind } from "@/lib/tutor/types";

/** A node with its exits as [target, label] pairs. */
function N(
  id: string,
  text: string,
  kind: FlowNodeKind = "step",
  next: [string, string | null][] = [],
): FlowNode {
  return { id, text, kind, next: next.map(([to, label]) => ({ to, label })) };
}

const chart = (nodes: FlowNode[], extra: Partial<FlowchartBlock> = {}): FlowchartBlock => ({
  type: "flowchart",
  nodes,
  ...extra,
});

/** Chapter 1, 6.3.1: the pack gives no « ni SA ni SG », so the last question has one answer. */
export const METHOD = chart([
  N("diff", "Calculer les différences entre termes consécutifs", "step", [["d1", null]]),
  N("d1", "Sont-elles égales ?", "decision", [
    ["sa", "oui"],
    ["quot", "non"],
  ]),
  N("sa", "C'est une SA"),
  N("quot", "Calculer les quotients entre termes consécutifs", "step", [["d2", null]]),
  N("d2", "Sont-ils égaux ?", "decision", [["sg", "oui"]]),
  N("sg", "C'est une SG"),
]);

export const LOOP = chart([
  N("debut", "Début", "start", [["lire", null]]),
  N("lire", "Lire $n$", "io", [["init", null]]),
  N("init", "$S \\leftarrow 0$ ; $i \\leftarrow 1$", "step", [["test", null]]),
  N("test", "$i \\leqslant n$ ?", "decision", [
    ["ajout", "oui"],
    ["afficher", "non"],
  ]),
  N("ajout", "$S \\leftarrow S + u_i$", "step", [["incr", null]]),
  N("incr", "$i \\leftarrow i + 1$", "step", [["test", null]]),
  N("afficher", "Afficher $S$", "io", [["fin", null]]),
  N("fin", "Fin", "end"),
]);

export const NESTED = chart([
  N("calc", "Calculer $\\Delta$", "step", [["d1", null]]),
  N("d1", "$\\Delta > 0$ ?", "decision", [
    ["two", "oui"],
    ["d2", "non"],
  ]),
  N("two", "Deux solutions"),
  N("d2", "$\\Delta = 0$ ?", "decision", [
    ["one", "oui"],
    ["zero", "non"],
  ]),
  N("one", "Une solution"),
  N("zero", "Pas de solution"),
]);

/** An « if » whose « oui » branch is two steps long: the « non » edge gets passages. */
export const MERGE = chart([
  N("a", "Lire $x$", "io", [["d", null]]),
  N("d", "$x \\geqslant 0$ ?", "decision", [
    ["b", "oui"],
    ["e", "non"],
  ]),
  N("b", "Calculer $\\sqrt{x}$", "step", [["c", null]]),
  N("c", "Arrondir au dixième", "step", [["e", null]]),
  N("e", "Afficher le résultat", "io"),
]);

/** A loop that leaves from a question: « non » goes back up. */
export const REPEAT = chart([
  N("s", "Début", "start", [["body", null]]),
  N("body", "Lancer le dé", "step", [["t", null]]),
  N("t", "A-t-on un six ?", "decision", [
    ["body", "non"],
    ["f", "oui"],
  ]),
  N("f", "Fin", "end"),
]);

export const VARTYPE = chart(
  [
    N("a", "Choisir le graphique", "step", [["d", null]]),
    N("d", "Variable qualitative ?", "decision", [
      ["q", "oui"],
      ["d2", "non"],
    ]),
    N("q", "Diagramme en barres ou circulaire"),
    N("d2", "Variable discrète ?", "decision", [
      ["b", "oui"],
      ["h", "non"],
    ]),
    N("b", "Diagramme en bâtons"),
    N("h", "Histogramme"),
  ],
  { caption: "Quel graphique pour quelle variable ?" },
);

/** A question, then a row holding an io box beside a second question. */
export const DEC_STEP_ROW = chart([
  N("a", "Lire $x$", "io", [["d", null]]),
  N("d", "$x > 0$ ?", "decision", [
    ["b", "oui"],
    ["d2", "non"],
  ]),
  N("b", "Afficher « positif »", "io", [["f", null]]),
  N("d2", "Les quotients sont-ils égaux ?", "decision", [
    ["g", "oui"],
    ["f", "non"],
  ]),
  N("g", "C'est une SG", "step", [["f", null]]),
  N("f", "Fin", "end"),
]);

/** Formulas in the boxes, a fraction among them. */
export const FORMULAS = chart([
  N("a", "Calculer $u_2 - u_1$ et $u_3 - u_2$", "step", [["d", null]]),
  N("d", "$u_{n+1} - u_n$ est-elle constante ?", "decision", [
    ["x", "oui"],
    ["y", "non"],
  ]),
  N("x", "Suite arithmétique de raison $r$", "step", [["z", null]]),
  N("y", "Calculer $\\frac{u_{n+1}}{u_n}$", "step", [["z2", null]]),
  N("z", "Afficher $r$", "io"),
  N("z2", "Afficher $q$", "io"),
]);

/** A loop back to the first box: its bar runs above the first row. */
export const BACK_TO_ROOT = chart([
  N("lire", "Lire $x$", "io", [["d", null]]),
  N("d", "$x > 0$ ?", "decision", [
    ["afficher", "oui"],
    ["lire", "non"],
  ]),
  N("afficher", "Afficher $\\sqrt{x}$", "io"),
]);

/** A question whose two answers both go back up: a lane on each side. */
export const TWO_LOOPS = chart([
  N("a", "Lire $n$", "io", [["b", null]]),
  N("b", "Calculer $n^2$", "step", [["c", null]]),
  N("c", "Afficher $n^2$", "io", [["d", null]]),
  N("d", "Encore ?", "decision", [
    ["a", "oui"],
    ["b", "même $n$"],
  ]),
]);

/**
 * Two « tant que » loops one after the other: t1's loop and t2's loop meet in
 * the gap between them, so they take two lanes (one lane read as one line that
 * forks, and no one could tell which loop goes back to which test).
 */
export const TWO_WHILES = chart([
  N("a", "Début", "start", [["t1", null]]),
  N("t1", "$u_n < 10$ ?", "decision", [
    ["s1", "oui"],
    ["m", "non"],
  ]),
  N("t2", "$S < 100$ ?", "decision", [
    ["s2", "oui"],
    ["f", "non"],
  ]),
  N("s2", "$S \\leftarrow S + u_n$", "step", [["t2", null]]),
  N("s1", "$n \\leftarrow n + 1$", "step", [["t1", null]]),
  N("m", "Afficher $n$", "io", [["t2", null]]),
  N("f", "Fin", "end"),
]);

/**
 * A layout case, not a method: d1's « non » runs down past two rows, and at
 * 400 px and up its passage comes down where d3's bar goes down into d3. The
 * passage's bar takes the higher track, so the two verticals never share a stretch.
 */
export const LONG_EDGE = chart([
  N("debut", "Début", "start", [["lire", null]]),
  N("lire", "Lire la suite", "step", [["d1", null]]),
  N("d1", "Termes connus ?", "decision", [
    ["d2", "oui"],
    ["revoir", "non"],
  ]),
  N("d2", "$r$ constante ?", "decision", [
    ["sa", "oui"],
    ["d3", "non"],
  ]),
  N("revoir", "Revoir l'énoncé"),
  N("sa", "Suite arithmétique", "step", [["r", null]]),
  N("d3", "Quotients égaux ?", "decision", [["revoir", "oui"]]),
  N("r", "Donner $r$"),
]);

export const HIDDEN = { ...METHOD, hidden: ["quot"] } satisfies FlowchartBlock;
export const SECRET = "Calculer les quotients entre termes consécutifs";

export const PATH = {
  ...LOOP,
  path: ["debut", "lire", "init", "test", "ajout", "incr", "test"],
} satisfies FlowchartBlock;

export const FIXTURES = {
  METHOD,
  LOOP,
  NESTED,
  MERGE,
  REPEAT,
  VARTYPE,
  DEC_STEP_ROW,
  FORMULAS,
  BACK_TO_ROOT,
  TWO_LOOPS,
  TWO_WHILES,
  LONG_EDGE,
  HIDDEN,
  PATH,
} satisfies Record<string, FlowchartBlock>;
