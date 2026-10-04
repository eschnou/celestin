import { niceTicks } from "../charts/scale";

/**
 * Graduations of a plot's axes. Every tick keeps its mark and its grid line;
 * labels thin out to a round multiple of the step, anchored at 0, so a crowded
 * axis reads 0 ; 0,5 ; 1 rather than every tenth.
 */

/** Where an axis sits, in the other axis's units, and whether it is the real one. */
export type AxisAt = { at: number; arrow: boolean };

/**
 * Through 0 when the window holds it: the axis, with its arrow. Otherwise on the
 * window's edge nearest 0, drawn as a graduated edge with no arrow: an arrowed
 * axis reads as the line x = 0 or y = 0.
 */
export function axisAt(min: number, max: number): AxisAt {
  if (min <= 0 && 0 <= max) return { at: 0, arrow: true };
  return { at: min > 0 ? min : max, arrow: false };
}

/** The decimals a step needs to be written exactly (at most 10). */
export function decimalsOf(step: number): number {
  for (let d = 0; d <= 10; d += 1) {
    const s = step * 10 ** d;
    if (Math.abs(Math.round(s) - s) < 1e-9 * Math.max(1, s)) return d;
  }
  return 10;
}

/**
 * A round step when Célestin gave none: about one tick every 56 px. On the n axis of
 * a sequence (`integer`), never less than 1.
 */
export function autoStep(min: number, max: number, lengthPx: number, integer: boolean): number {
  const count = Math.min(10, Math.max(2, Math.round(lengthPx / 56)));
  const { ticks } = niceTicks(min, max, count);
  const first = ticks[0] ?? 0;
  const second = ticks[1] ?? first + 1;
  const step = Number((second - first).toPrecision(12)) || 1;
  return integer ? Math.max(1, step) : step;
}

// A stored step is limited to 60 intervals; this only keeps a bad call bounded.
const MAX_TICKS = 200;

/** Every multiple of `step` in [min, max], without float noise. */
export function stepTicks(min: number, max: number, step: number): number[] {
  if (!(step > 0) || !Number.isFinite(min) || !Number.isFinite(max)) return [];
  const d = decimalsOf(step);
  const out: number[] = [];
  const from = Math.ceil(min / step - 1e-9);
  const to = Math.floor(max / step + 1e-9);
  for (let k = from; k <= to && out.length < MAX_TICKS; k += 1) {
    out.push(Number((k * step).toFixed(d)) || 0); // `|| 0`: no −0
  }
  return out;
}

/**
 * Every how many ticks a label is written: the first k from what the spacing
 * needs, up to twice that, whose k·step is 1, 2 or 5 × 10ᵐ; otherwise the need.
 */
export function labelEvery(step: number, spacingPx: number, needPx: number): number {
  if (!(spacingPx > 0)) return 1;
  const need = Math.max(1, Math.ceil(needPx / spacingPx - 1e-9));
  if (need === 1) return 1;
  for (let k = need; k <= 2 * need; k += 1) {
    const span = k * step;
    const magnitude = 10 ** Math.floor(Math.log10(span));
    const normed = span / magnitude;
    if ([1, 2, 5, 10].some((m) => Math.abs(normed - m) < 1e-6)) return k;
  }
  return need;
}

/** Whether tick `t` of an axis graduated by `step` carries a label (anchored at 0). */
export function labelled(t: number, step: number, every: number): boolean {
  return Math.round(t / step) % every === 0;
}
