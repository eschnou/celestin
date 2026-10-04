import type { CleanPlot } from "./sanitise";

/**
 * The colour key. A function given in pieces reads as one function: solid curves,
 * sequences and solid lines that share a label (or share having none) share one
 * colour and one label on the board. Dashed layers are construction lines
 * (asymptotes, reading lines) in the muted ink, and are never grouped.
 *
 * chart-3 and chart-7 are left out: under 3:1 on the card, too light for a line.
 */
export const SERIES = [1, 4, 2, 5, 6, 8].map((i) => `var(--chart-${i})`);
export const MUTED = "var(--muted-foreground)";

export type Group = {
  /** The label as written, or null for the unlabelled group. */
  label: string | null;
  colour: string;
  curves: number[];
  sequences: number[];
  lines: number[];
};

export type Colours = {
  groups: Group[];
  /** Per layer, in declared order: the group index, or null for a dashed layer. */
  curve: (number | null)[];
  sequence: number[];
  line: (number | null)[];
};

export function colourGroups(plot: CleanPlot): Colours {
  const groups: Group[] = [];
  const byKey = new Map<string, number>();
  const join = (label: string | null): number => {
    const key = label?.trim() ?? "";
    const found = byKey.get(key);
    if (found !== undefined) return found;
    const index = groups.length;
    groups.push({
      label: key || null,
      colour: SERIES[index % SERIES.length] as string,
      curves: [],
      sequences: [],
      lines: [],
    });
    byKey.set(key, index);
    return index;
  };
  const curve = plot.curves.map((c, i) => {
    if (c.dashed) return null;
    const g = join(c.label);
    groups[g]?.curves.push(i);
    return g;
  });
  const sequence = plot.sequences.map((s, i) => {
    const g = join(s.label);
    groups[g]?.sequences.push(i);
    return g;
  });
  const line = plot.lines.map((l, i) => {
    if (l.dashed) return null;
    const g = join(l.label);
    groups[g]?.lines.push(i);
    return g;
  });
  return { groups, curve, sequence, line };
}

/** A layer's colour: its group's, or the muted ink when it is dashed. */
export function colourOf(colours: Colours, group: number | null): string {
  return group === null ? MUTED : (colours.groups[group]?.colour ?? MUTED);
}
