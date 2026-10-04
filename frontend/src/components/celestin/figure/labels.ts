/**
 * Labels over a figure. The SVG draws the geometry; every text a figure writes
 * sits in an HTML layer above it (`label-layer.tsx`), so a `$…$` label is
 * typeset by KaTeX like the rest of the board. Nothing here measures the DOM:
 * widths are the same generous estimate the tool's capacity rule uses
 * (`backend/app/services/tools/figures.py`, `text_px`), pinned by the shared
 * case table `__tests__/capacity.json`.
 */

export type Dir = [number, number];

/** A piece of a label: our TeX (a point's name), the model's text (RichText), or our plain text. */
export type LabelPart = { kind: "tex" | "rich" | "plain"; text: string };

/** A label pinned at a point and pushed off it in a screen direction (y down). */
export type PlacedLabel = {
  key: string;
  x: number;
  y: number;
  dir: Dir;
  parts: LabelPart[];
  /** A colour class from our code (`text-chart-1`…), never from the model. */
  className?: string;
};

/** Elements flowing in a box, as flex-wrap packs them (a zone of a diagram of sets). */
export type Flow = {
  key: string;
  left: number;
  top: number;
  width: number;
  height: number;
  items: string[];
  /** One per row, top to bottom (a ring of nested sets). */
  column?: boolean;
};

export const CHAR_PX = 7;
export const GLYPH_PX = 9;
export const GAP_PX = 6;
/** The height a one-line 12 px label is given when it is kept inside the drawing. */
export const LABEL_H = 16;

/**
 * Whitespace as RichText reads it (JavaScript's `\s`), spelled out so the
 * backend's `text_px` can use the very same class: Python's `\s` differs.
 */
const WS =
  "\\t\\n\\v\\f\\r \\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000\\ufeff";
// The same delimiters as the board's RichText.
const MATH_PART = new RegExp(`\\$\\$[\\s\\S]+?\\$\\$|\\$(?![${WS}])[^$]*?(?<![${WS}])\\$`, "g");
const SILENT = new RegExp(`[{}^_\\\\${WS}]`, "g");

/** Characters as Python counts them (code points), so 𝔻 is one, not two. */
const count = (text: string) => [...text].length;

/**
 * A generous width for 12 px text on the board: 7 px a prose character, 9 px a
 * glyph of maths, where a `\command` is one glyph and braces, `^`, `_` and
 * spaces are none. « Diviseurs de 12 » is 105, `$\frac{1}{3}$` is 27.
 */
export function textPx(text: string): number {
  let width = 0;
  let last = 0;
  for (const part of text.matchAll(MATH_PART)) {
    const at = part.index ?? 0;
    width += CHAR_PX * count(text.slice(last, at));
    const tex = part[0].replace(/^\$+|\$+$/g, "").replace(/\\[A-Za-z]+/g, "#");
    width += GLYPH_PX * count(tex.replace(SILENT, ""));
    last = at + part[0].length;
  }
  return width + CHAR_PX * count(text.slice(last));
}

/** A label as plain words, for an aria-label: its `$` dropped. */
export function visibleText(text: string): string {
  return text.replace(/\$/g, "").trim();
}

const round1 = (v: number) => Math.round(v * 10) / 10;

/**
 * The CSS transform that puts a label's box beside its anchor, on the side `dir`
 * points to: (1, 0) to the right and vertically centred, (0, −1) above. A zero
 * or non-finite direction centres the box on the anchor.
 */
export function anchorTransform([dx, dy]: Dir): string {
  const m = Math.max(Math.abs(dx), Math.abs(dy));
  if (!Number.isFinite(m) || m < 1e-6) return "translate(-50%, -50%)";
  return `translate(${round1(-50 + (50 * dx) / m)}%, ${round1(-50 + (50 * dy) / m)}%)`;
}

/** Where the translated box's top-left corner lands, as a fraction of its size. */
function offset([dx, dy]: Dir): [number, number] {
  const m = Math.max(Math.abs(dx), Math.abs(dy));
  if (!Number.isFinite(m) || m < 1e-6) return [-0.5, -0.5];
  return [-0.5 + (0.5 * dx) / m, -0.5 + (0.5 * dy) / m];
}

export type Box = { x0: number; y0: number; x1: number; y1: number };

/** The box a label of w × h covers once `anchorTransform(dir)` has placed it. */
export function labelBox(x: number, y: number, dir: Dir, w: number, h: number): Box {
  const [fx, fy] = offset(dir);
  return { x0: x + fx * w, y0: y + fy * h, x1: x + fx * w + w, y1: y + fy * h + h };
}

/** Whether two boxes overlap (touching edges do not). */
export function overlaps(a: Box, b: Box): boolean {
  return a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1;
}

/**
 * The anchor moved just enough that the label's box (w × h, placed by
 * `anchorTransform(dir)`) stays inside the drawing [0, W] × [0, H].
 */
export function clampAnchor(
  x: number,
  y: number,
  dir: Dir,
  w: number,
  h: number,
  W: number,
  H: number,
): [number, number] {
  const [fx, fy] = offset(dir);
  const shift = (at: number, size: number, max: number, f: number) => {
    const start = at + f * size;
    if (size >= max) return at - start;
    if (start < 0) return at - start;
    if (start + size > max) return at - (start + size - max);
    return at;
  };
  const cx = shift(Number.isFinite(x) ? x : 0, w, W, fx);
  const cy = shift(Number.isFinite(y) ? y : 0, h, H, fy);
  return [cx, cy];
}

/**
 * Centres for labels in one row, each as close to where it wants to be as the
 * others allow: overlapping labels are grouped and each group is centred on
 * its members' wishes, then kept inside [lo, hi]. Two labels end ≥ `gap` apart.
 */
export function spreadRow(
  items: { centre: number; width: number }[],
  lo: number,
  hi: number,
  gap: number,
): number[] {
  type Member = { index: number; centre: number; width: number };
  type Cluster = { members: Member[]; left: number; width: number };
  const fit = (members: Member[]): Cluster => {
    const width =
      members.reduce((sum, m) => sum + m.width, 0) + gap * Math.max(0, members.length - 1);
    // Centred on the mean of the wished centres, so the row reads evenly.
    const wish = members.reduce((sum, m) => sum + m.centre, 0) / Math.max(1, members.length);
    const left = Math.min(Math.max(wish - width / 2, lo), Math.max(lo, hi - width));
    return { members, left, width };
  };
  const sorted = items
    .map((item, index) => ({ index, centre: item.centre, width: item.width }))
    .sort((a, b) => a.centre - b.centre);
  const clusters: Cluster[] = [];
  for (const member of sorted) {
    let next = fit([member]);
    // Merge back while the newest cluster overlaps the one before it.
    let before = clusters.at(-1);
    while (before && before.left + before.width + gap > next.left) {
      clusters.pop();
      next = fit([...before.members, ...next.members]);
      before = clusters.at(-1);
    }
    clusters.push(next);
  }
  const centres = new Array<number>(items.length).fill(0);
  for (const c of clusters) {
    let x = c.left;
    for (const m of c.members) {
      centres[m.index] = x + m.width / 2;
      x += m.width + gap;
    }
  }
  return centres;
}

/**
 * Rows a greedy left-to-right flow of `widths` takes in `slot` px, as flex-wrap
 * packs them with a 6 px gap, or null when one is wider than the slot. The same
 * function as the backend's `flow_rows`.
 */
export function flowRows(widths: number[], slot: number): number | null {
  let rows = 0;
  let used = slot + 1;
  for (const w of widths) {
    if (w > slot) return null;
    if (used + GAP_PX + w > slot) {
      rows += 1;
      used = w;
    } else {
      used += GAP_PX + w;
    }
  }
  return rows;
}
