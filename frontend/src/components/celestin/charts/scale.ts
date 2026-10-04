/** A linear map from a domain to a range, the only scale the charts need. */
export function linear([d0, d1]: [number, number], [r0, r1]: [number, number]) {
  const span = d1 - d0 || 1;
  return (v: number) => r0 + ((v - d0) / span) * (r1 - r0);
}

export type Ticks = { lo: number; hi: number; ticks: number[] };

/**
 * Round ticks covering [min, max]: a step of 1, 2 or 5 × 10ᵏ, about `count` of
 * them, each rounded to the step's decimals so no `0.30000000000000004` reaches
 * an axis. A flat domain is widened to one step on each side.
 */
export function niceTicks(min: number, max: number, count = 5): Ticks {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return niceTicks(0, 1, count);
  if (!(max > min)) {
    const pad = Math.abs(min) > 0 ? Math.abs(min) / 2 : 1;
    return niceTicks(min - pad, max + pad, count);
  }
  const rough = (max - min) / count;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const normed = rough / magnitude;
  const step = (normed < 1.5 ? 1 : normed < 3 ? 2 : normed < 7 ? 5 : 10) * magnitude;
  const decimals = Math.max(0, -Math.floor(Math.log10(step)));
  const round = (v: number) => Number(v.toFixed(decimals));
  const lo = round(Math.floor(min / step) * step);
  const hi = round(Math.ceil(max / step) * step);
  const ticks: number[] = [];
  for (let i = 0; lo + i * step <= hi + step / 2; i += 1) ticks.push(round(lo + i * step));
  return { lo, hi, ticks };
}
