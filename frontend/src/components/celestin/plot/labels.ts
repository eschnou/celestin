import { m } from "@/paraglide/messages";
/**
 * Text on a plot: how a label reads aloud, how wide it is, and where it goes.
 * Labels are HTML spans over the SVG (KaTeX for their maths), so their size is
 * estimated here and the layout keeps them clear of what is drawn.
 */

export type Box = { left: number; top: number; width: number; height: number };
/** A placed text box, and which of its sides is pinned when the real text is wider. */
export type Anchored = Box & { align: "left" | "right" };

const FORMATTING = new Set([
  "mathcal",
  "mathrm",
  "mathbf",
  "mathit",
  "mathbb",
  "mathscr",
  "boldsymbol",
  "text",
  "textrm",
  "operatorname",
  "left",
  "right",
  "displaystyle",
  "quad",
  "qquad",
]);

/**
 * A label or title as a screen reader should say it, in the interface language: no `$`, `_a` as
 * « indice a », `^a` as « exposant a », formatting commands dropped, a Greek letter by its name.
 * `$\mathcal{C}_f$` is « C indice f », `$v$ (m/s)` is « v (m/s) ».
 */
export function plainText(text: string): string {
  // A script's argument: {…}, a command, or one character.
  const argument = String.raw`\s*(\{[^{}]*\}|\\[A-Za-z]+|[^\s{}\\])`;
  return text
    .replace(/\$/g, "")
    .replace(/\{,\}/g, ",")
    .replace(/\\[,;:! ]/g, " ")
    .replace(
      new RegExp(`_${argument}`, "g"),
      (_, sub: string) => ` ${m.describe_plot_word_subscript()} ${sub} `,
    )
    .replace(
      new RegExp(String.raw`\^${argument}`, "g"),
      (_, sup: string) => ` ${m.describe_plot_word_superscript()} ${sup} `,
    )
    .replace(/\\([A-Za-z]+)/g, (_, name: string) => (FORMATTING.has(name) ? "" : ` ${name} `))
    .replace(/[{}~_^\\]/g, " ")
    .replace(/\s+([),.;:])/g, "$1")
    .replace(/([(])\s+/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

/** How many characters of maths show: commands as one glyph, no braces or markers. */
function mathGlyphs(tex: string): number {
  const shown = tex
    .replace(/\\[,;:! ]/g, "")
    .replace(/\\([A-Za-z]+)/g, (_, name: string) => (FORMATTING.has(name) ? "" : "x"))
    .replace(/[{}_^\s]/g, "");
  return shown.length;
}

export const LABEL_HEIGHT = 20;
const PROSE_PX = 7.8; // 14 px Lato
const MATH_PX = 9.5; // 14 px KaTeX italic
const PADDING_PX = 4;

/**
 * A label's box size at 14 px (`scale` 12/14 for the 12 px titles). An estimate:
 * maths between `$` (or `$$`) counted by its glyphs, prose by its characters.
 */
export function labelSize(text: string, coords: string | null = null, scale = 1) {
  let width = PADDING_PX;
  text.split(/\$\$?/).forEach((part, i) => {
    width += i % 2 === 1 ? mathGlyphs(part) * MATH_PX : part.length * PROSE_PX;
  });
  if (coords) width += (coords.length + (text ? 1 : 0)) * PROSE_PX;
  return { width: Math.ceil(width * scale), height: LABEL_HEIGHT };
}

const CELL = 2;

/**
 * What is drawn, on a grid of 2 px cells: curves, marks, axes, tick labels and
 * the labels already placed. A label goes where it covers none of it.
 */
export class Occupancy {
  readonly cols: number;
  readonly rows: number;
  readonly cells: Uint8Array;

  constructor(width: number, height: number) {
    this.cols = Math.max(1, Math.ceil(width / CELL));
    this.rows = Math.max(1, Math.ceil(height / CELL));
    this.cells = new Uint8Array(this.cols * this.rows);
  }

  mark(x: number, y: number): void {
    const c = Math.floor(x / CELL);
    const r = Math.floor(y / CELL);
    if (c >= 0 && r >= 0 && c < this.cols && r < this.rows) this.cells[r * this.cols + c] = 1;
  }

  markBox(b: Box): void {
    for (let y = b.top; y <= b.top + b.height; y += CELL) {
      for (let x = b.left; x <= b.left + b.width; x += CELL) this.mark(x, y);
    }
    this.mark(b.left + b.width, b.top + b.height);
  }

  /** A polyline, one mark every `step` px along it. */
  markPath(points: readonly (readonly [number, number])[], step = 3): void {
    for (let i = 0; i < points.length; i += 1) {
      const [x, y] = points[i] as readonly [number, number];
      this.mark(x, y);
      const next = points[i + 1];
      if (!next) continue;
      const length = Math.hypot(next[0] - x, next[1] - y);
      const n = Math.min(10_000, Math.ceil(length / step));
      for (let k = 1; k < n; k += 1)
        this.mark(x + ((next[0] - x) * k) / n, y + ((next[1] - y) * k) / n);
    }
  }

  /** No marked cell under the box, less 1 px on each side. */
  free(b: Box): boolean {
    const c0 = Math.max(0, Math.floor((b.left + 1) / CELL));
    const c1 = Math.min(this.cols - 1, Math.floor((b.left + b.width - 1) / CELL));
    const r0 = Math.max(0, Math.floor((b.top + 1) / CELL));
    const r1 = Math.min(this.rows - 1, Math.floor((b.top + b.height - 1) / CELL));
    for (let r = r0; r <= r1; r += 1) {
      for (let c = c0; c <= c1; c += 1) if (this.cells[r * this.cols + c]) return false;
    }
    return true;
  }
}

export type Area = { width: number; height: number };
export type LabelRequest = {
  candidates: readonly (readonly [number, number])[];
  width: number;
  height: number;
};

const GAP = 6;
const PAD = 2;

const overlaps = (a: Box, b: Box) =>
  a.left < b.left + b.width + PAD &&
  b.left < a.left + a.width + PAD &&
  a.top < b.top + b.height + PAD &&
  b.top < a.top + a.height + PAD;

const inside = (b: Box, area: Area) =>
  b.left >= 0 && b.top >= 0 && b.left + b.width <= area.width && b.top + b.height <= area.height;

/** The box clamped into the area; a box wider than the area starts at its left. */
export function clampBox(b: Box, area: Area): Box {
  const width = Math.min(b.width, area.width);
  return {
    left: Math.max(0, Math.min(b.left, area.width - width)),
    top: Math.max(0, Math.min(b.top, area.height - b.height)),
    width,
    height: b.height,
  };
}

/**
 * Each request's box, in order: at the first candidate, then the next, whose
 * north-east, north-west, south-east or south-west box (6 px off) lies in the
 * area, clear of the boxes already placed and of everything drawn. Otherwise the
 * first candidate's north-east box, clamped into the area. Placed boxes are
 * marked, so later labels avoid them.
 */
export function placeLabels(
  requests: readonly LabelRequest[],
  area: Area,
  occupancy: Occupancy,
  taken: Box[] = [],
): Anchored[] {
  return requests.map(({ candidates, width, height }) => {
    const around = ([x, y]: readonly [number, number]): Anchored[] => [
      { left: x + GAP, top: y - GAP - height, width, height, align: "left" },
      { left: x - GAP - width, top: y - GAP - height, width, height, align: "right" },
      { left: x + GAP, top: y + GAP, width, height, align: "left" },
      { left: x - GAP - width, top: y + GAP, width, height, align: "right" },
    ];
    let chosen: Anchored | undefined;
    for (const candidate of candidates) {
      chosen = around(candidate).find(
        (b) => inside(b, area) && !taken.some((t) => overlaps(b, t)) && occupancy.free(b),
      );
      if (chosen) break;
    }
    const first = candidates[0] ?? [0, height + GAP];
    const box: Anchored = chosen ?? { ...clampBox(around(first)[0] as Box, area), align: "left" };
    taken.push(box);
    occupancy.markBox(box);
    return box;
  });
}
