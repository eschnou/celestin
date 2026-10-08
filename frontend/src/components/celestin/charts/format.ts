import { useCourseLanguage, type CourseLanguage } from "@/lib/course-language";
import type { Closed, Measure } from "@/lib/tutor/types";

/**
 * Numbers as the course writes them (FWB): a decimal comma, a narrow no-break
 * space between thousands from five digits on (a year stays `2018`), a true
 * minus sign. Four decimals at most, which also absorbs float noise (`0.1 + 0.2`
 * is `0,3`).
 */
const NUMBER = new Intl.NumberFormat("fr-BE", {
  maximumFractionDigits: 4,
  // Intl.NumberFormat v3, not yet in TypeScript's lib. A browser without it reads
  // any string as `true` and groups every thousand: `2 018`, legible if not ideal.
  useGrouping: "min2" as unknown as boolean,
});

export function formatNumber(n: number): string {
  return NUMBER.format(n).replace("-", "−");
}

/** What a measure is called, as a table column. */
export const MEASURE_NAME: Record<Measure, string> = {
  effectif: "Effectif",
  frequence: "Fréquence",
  pourcentage: "Pourcentage",
};

/** The five numbers of a box plot, as the course names them: course vocabulary, French
 *  whatever the interface language, like `MEASURE_NAME`. */
export const BOX_STATS = ["Minimum", "Q1", "Médiane", "Q3", "Maximum"] as const;

/** A value with its measure's unit: `12,5 %` for a percentage, bare otherwise. */
export function formatValue(n: number, measure: Measure): string {
  return measure === "pourcentage" ? `${formatNumber(n)}\u00a0%` : formatNumber(n);
}

/** A pair of coordinates as the course writes them: `(2 ; −1,5)`. */
export function formatPair(x: number, y: number): string {
  return `(${formatNumber(x)} ; ${formatNumber(y)})`;
}

/**
 * An interval's end: a number, text already written (a number line's mark
 * label, `$\sqrt{2}$`), or null for an infinite end.
 */
export type Bound = number | string | null;

/** A bound as the course writes it, `infinity` (`−∞`, `+∞`) for an infinite end. */
export function formatBound(bound: Bound, infinity: string): string {
  if (bound === null) return infinity;
  return typeof bound === "number" ? formatNumber(bound) : bound;
}

/**
 * An interval in the course's notation: `[2 ; 5[`, `]−∞ ; 2]`, `]−∞ ; +∞[`.
 * The bracket turns away from an end the interval leaves out, and an infinite
 * end is always left out, whatever its closure says.
 */
export function formatInterval(
  a: Bound,
  b: Bound,
  closedLeft: boolean,
  closedRight: boolean,
): string {
  const open = closedLeft && a !== null ? "[" : "]";
  const close = closedRight && b !== null ? "]" : "[";
  return `${open}${formatBound(a, "−∞")} ; ${formatBound(b, "+∞")}${close}`;
}

/** A class in the course's interval notation: `[10 ; 20[` or `]10 ; 20]`. */
export function classLabel(a: number, b: number, closed: Closed): string {
  return formatInterval(a, b, closed === "left", closed === "right");
}

/* ------------------------------ per course language ------------------------------ */

/**
 * The board's notation, chosen by the course's language (spec 011 §5.2). The French row
 * is the functions above, by reference, so the French board cannot drift; the English one
 * is the common international convention: a decimal point, `12.5%`, `(a, b)` and `[a, b)`
 * intervals with `(−∞, 2]`, a point as `(2, −1.5)`, commas between thousands. Where a
 * course's material writes otherwise, Célestin's text follows the material and the board's
 * own formatter stays here.
 */
export type Notation = {
  number(n: number): string;
  value(n: number, measure: Measure): string;
  pair(x: number, y: number): string;
  /** `infinity` is the French sign for an infinite end (`−∞`, `+∞`): English writes `∞` on the right. */
  bound(bound: Bound, infinity: string): string;
  interval(a: Bound, b: Bound, closedLeft: boolean, closedRight: boolean): string;
  classLabel(a: number, b: number, closed: Closed): string;
  /** What a measure is called, as a table column. */
  measureName: Record<Measure, string>;
  /** The five numbers of a box plot, as the course names them. */
  boxStats: readonly [string, string, string, string, string];
  /** Between the members of a list of values or points. */
  separator: string;
};

export const FRENCH: Notation = {
  number: formatNumber,
  value: formatValue,
  pair: formatPair,
  bound: formatBound,
  interval: formatInterval,
  classLabel,
  measureName: MEASURE_NAME,
  boxStats: BOX_STATS,
  separator: " ; ",
};

const NUMBER_EN = new Intl.NumberFormat("en-GB", {
  maximumFractionDigits: 4,
  useGrouping: "min2" as unknown as boolean,
});

function englishNumber(n: number): string {
  return NUMBER_EN.format(n).replace("-", "−");
}

function englishBound(bound: Bound, infinity: string): string {
  if (bound === null) return infinity.replace("+", "");
  return typeof bound === "number" ? englishNumber(bound) : bound;
}

function englishInterval(a: Bound, b: Bound, closedLeft: boolean, closedRight: boolean): string {
  const open = closedLeft && a !== null ? "[" : "(";
  const close = closedRight && b !== null ? "]" : ")";
  return `${open}${englishBound(a, "−∞")}, ${englishBound(b, "+∞")}${close}`;
}

export const ENGLISH: Notation = {
  number: englishNumber,
  value: (n, measure) => (measure === "pourcentage" ? `${englishNumber(n)}%` : englishNumber(n)),
  pair: (x, y) => `(${englishNumber(x)}, ${englishNumber(y)})`,
  bound: englishBound,
  interval: englishInterval,
  classLabel: (a, b, closed) => englishInterval(a, b, closed === "left", closed === "right"),
  measureName: {
    effectif: "Frequency",
    frequence: "Relative frequency",
    pourcentage: "Percentage",
  },
  boxStats: ["Minimum", "Q1", "Median", "Q3", "Maximum"],
  separator: ", ",
};

// Dutch (Flemish): the Belgian-French notation by reference — decimal comma, `12,5 %`, `]a ; b[`, `(2 ; −1,5)`,
// grouping by a space — and the Dutch words (spec 017 §1 decision 1). If a convention turns out different, this
// is the one place on the board to change, with `notation_cases.json` and the Dutch subject prompts.
export const DUTCH: Notation = {
  ...FRENCH,
  measureName: {
    effectif: "Frequentie",
    frequence: "Relatieve frequentie",
    pourcentage: "Percentage",
  },
  boxStats: ["Minimum", "Q1", "Mediaan", "Q3", "Maximum"],
};

export const NOTATION: Record<CourseLanguage, Notation> = { fr: FRENCH, en: ENGLISH, nl: DUTCH };

export const notationFor = (language: CourseLanguage): Notation => NOTATION[language];

/** The notation of the course on screen (French outside a provider). */
export const useNotation = (): Notation => notationFor(useCourseLanguage());
