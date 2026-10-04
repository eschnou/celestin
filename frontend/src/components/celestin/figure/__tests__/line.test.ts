import { describe, expect, it } from "vitest";
import {
  bracketArms,
  complement,
  groupLabel,
  groupLabelLines,
  groupLanes,
  groups,
  intervalNotation,
  lineLayout,
  rowsBelow,
} from "../line";
import { classLabel, formatNumber } from "../../charts/format";
import { textPx } from "../labels";
import { sanitise, type CleanInterval, type CleanLine } from "../sanitise";
import { UNION } from "./fixtures";

const iv = (
  start: number | null,
  end: number | null,
  closed: CleanInterval["closed"],
  label: string | null = null,
): CleanInterval => ({ start, end, closed, label });

const line = (figure: object): CleanLine => {
  const fig = sanitise({ kind: "number_line", ...figure });
  if (fig?.kind !== "number_line") throw new Error("not a number line");
  return fig;
};

describe("intervalNotation", () => {
  it("writes the course's brackets, true minus and infinity", () => {
    expect(intervalNotation(iv(2, 5, "left"))).toBe("[2 ; 5[");
    expect(intervalNotation(iv(null, 2, "right"))).toBe("]−∞ ; 2]");
    expect(intervalNotation(iv(null, null, "neither"))).toBe("]−∞ ; +∞[");
    expect(intervalNotation(iv(0.5, 1, "left"))).toBe("[0,5 ; 1[");
    // The chart's classes and the number line write intervals with one helper.
    expect(intervalNotation(iv(10, 20, "left"))).toBe(classLabel(10, 20, "left"));
  });

  it("never closes an infinite end, even on a closure sanitise would have opened", () => {
    expect(intervalNotation(iv(null, 2, "both"))).toBe("]−∞ ; 2]");
    expect(intervalNotation(iv(5, null, "left"))).toBe("[5 ; +∞[");
  });

  it("writes a bound by its mark's label when one sits there", () => {
    expect(
      intervalNotation(iv(Math.SQRT2, 3, "right"), [{ x: Math.SQRT2, label: "$\\sqrt{2}$" }]),
    ).toBe("]$\\sqrt{2}$ ; 3]");
  });
});

describe("groups", () => {
  it("makes one set of the pieces sharing a label, written as one union", () => {
    const fig = line(UNION);
    const gs = groups(fig.intervals);
    expect(gs).toHaveLength(1);
    expect(groupLanes(gs)).toEqual([0]);
    const [g] = gs;
    expect(g && groupLabel(g, [], true)).toBe("S = ]−∞ ; 2] ∪ ]5 ; +∞[");
    expect(g && groupLabel(g, [], false)).toBe("S");
    const layout = lineLayout(fig, 294);
    expect(layout.groups).toHaveLength(1);
    expect(layout.groups[0]?.pieces).toHaveLength(2);
  });

  it("gives each labelled set its own lane, and lets disjoint unlabelled ones share", () => {
    expect(groupLanes(groups([iv(0, 1, "both", "A"), iv(2, 3, "both", "B")]))).toEqual([0, 1]);
    expect(groupLanes(groups([iv(0, 1, "both"), iv(2, 3, "both")]))).toEqual([0, 0]);
    expect(groupLanes(groups([iv(0, 3, "both"), iv(2, 5, "both")]))).toEqual([0, 1]);
  });

  it("gives each interval its own lane when its notation is written over it", () => {
    const layout = lineLayout(
      line({ intervals: [iv(0, 1, "both"), iv(2, 3, "left")], show_values: true }),
      294,
    );
    expect(layout.groups.map((g) => g.lane)).toEqual([0, 1]);
    expect(layout.groups.map((g) => g.labels.map((l) => l.text))).toEqual([
      ["[0 ; 1]"],
      ["[2 ; 3["],
    ]);
  });

  it("keeps a lane's label row clear of the next lane's band and brackets", () => {
    const layout = lineLayout(
      line({ intervals: [iv(-2, 5, "both", "A"), iv(0, 3, "both", "B")], show_values: true }),
      294,
    );
    const [a, b] = layout.groups;
    const [la] = a?.labels ?? [];
    const [lb] = b?.labels ?? [];
    if (!a || !b || !la || !lb) throw new Error("labels expected");
    const labelA = [la.y - 6, la.y + 6];
    const labelB = [lb.y - 6, lb.y + 6];
    const bracketsB = [b.y - 8, b.y + 8];
    const bracketsA = [a.y - 8, a.y + 8];
    const apart = ([p, q]: number[], [r, s]: number[]) =>
      (q ?? 0) < (r ?? 0) || (s ?? 0) < (p ?? 0);
    expect(apart(labelA, bracketsB)).toBe(true);
    expect(apart(labelA, bracketsA)).toBe(true);
    expect(apart(labelB, bracketsB)).toBe(true);
  });
});

describe("a notation wider than the board", () => {
  const FOUR = [
    iv(null, -3, "right", "$S$"),
    iv(-1, 1, "both", "$S$"),
    iv(2, 3, "left", "$S$"),
    iv(4, null, "neither", "$S$"),
  ];

  it("breaks before a « ∪ », never inside a piece or the label", () => {
    const [g] = groups(FOUR);
    if (!g) throw new Error("one set expected");
    const lines = groupLabelLines(g, [], true, 278);
    expect(lines.length).toBeGreaterThan(1);
    expect(lines.join(" ")).toBe(groupLabel(g, [], true));
    expect(lines[0]?.startsWith("$S$ = ]−∞ ; −3]")).toBe(true);
    for (const next of lines.slice(1)) expect(next.startsWith("∪ ")).toBe(true);
    for (const l of lines) expect(textPx(l)).toBeLessThanOrEqual(278);
    // Without values, only the label is written, on one line.
    expect(groupLabelLines(g, [], false, 278)).toEqual(["$S$"]);
    expect(groupLabelLines(g, [], true, 10_000)).toEqual([groupLabel(g, [], true)]);
  });

  it("breaks after « = » when even the first piece does not fit beside the label", () => {
    const [g] = groups([iv(-2.75, -1.25, "both", "$S$")]);
    if (!g) throw new Error("one set expected");
    expect(groupLabelLines(g, [], true, 90)).toEqual(["$S$ =", "[−2,75 ; −1,25]"]);
  });

  it.each([294, 250])(
    "keeps a 4-piece union inside a %i px drawing, lifting the lanes above it",
    (W) => {
      const fig = line({ intervals: FOUR.slice(0, 3), show_values: true });
      const wide = line({
        intervals: [...FOUR, iv(-2, 0, "both", "$T$")].slice(0, 4),
        show_values: true,
      });
      for (const f of [fig, wide]) {
        const layout = lineLayout(f, W);
        for (const g of layout.groups) {
          for (const l of g.labels) {
            expect(l.x).toBeGreaterThanOrEqual(layout.x0);
            expect(l.x + textPx(l.text)).toBeLessThanOrEqual(W);
          }
        }
      }
      const all = line({ intervals: FOUR, show_values: true });
      const layout = lineLayout(all, W);
      const [g] = layout.groups;
      expect(g?.labels.length).toBeGreaterThan(1);
      for (const l of g?.labels ?? []) {
        expect(l.x + textPx(l.text)).toBeLessThanOrEqual(W);
        expect(l.y).toBeGreaterThan(0);
      }
      // The lines stack upwards from the lane, 16 px apart, and stay clear of its brackets.
      const ys = (g?.labels ?? []).map((l) => l.y);
      expect(ys).toEqual([...ys].sort((a, b) => a - b));
      expect((ys[ys.length - 1] ?? 0) + 6).toBeLessThan((g?.y ?? 0) - 8);
    },
  );

  it("lifts the lane above a broken label by its extra lines", () => {
    const S = FOUR.slice(0, 3).map((i) => ({ ...i, label: "$S = T$ (ensemble solution)" }));
    const layout = lineLayout(
      line({ intervals: [...S, iv(0, 5, "both", "$B$")], show_values: true }),
      294,
    );
    const [s, b] = layout.groups;
    if (!s || !b) throw new Error("two sets expected");
    expect(s.labels.length).toBeGreaterThan(1);
    // b's brackets (±8) stay above s's top label line (±6).
    const topOfS = Math.min(...s.labels.map((l) => l.y)) - 6;
    expect(b.y + 8).toBeLessThan(topOfS);
    // And b's own label stays inside the drawing.
    for (const l of b.labels) expect(l.y - 6).toBeGreaterThanOrEqual(0);
  });
});

describe("rowsBelow", () => {
  it("opens another row rather than overlap two labels", () => {
    const items = [0, 1, 2, 3, 4].map((k) => ({ at: 100 + k * 5, width: 30 }));
    const rows = rowsBelow(items);
    expect(new Set(rows).size).toBe(5);
  });

  it("keeps every label of 4 intervals and the √2 encadrement apart at 294 px", () => {
    const layout = lineLayout(
      line({
        intervals: [
          iv(1, 2.75, "both"),
          iv(0.5, 1.25, "left"),
          iv(-1, 0.25, "right"),
          iv(3, 4, "both"),
        ],
        marks: [{ x: Math.SQRT2, label: "$\\sqrt{2}$" }, { x: 1.4 }, { x: 1.5 }],
      }),
      294,
    );
    for (const a of layout.numbers) {
      for (const b of layout.numbers) {
        if (a === b || a.y !== b.y) continue;
        expect(Math.abs(a.x - b.x)).toBeGreaterThanOrEqual((textPx(a.text) + textPx(b.text)) / 2);
      }
    }
    // Three rows would not hold them: a fourth and fifth open instead.
    expect(new Set(layout.numbers.map((n) => n.y)).size).toBeGreaterThan(3);
    expect(layout.height).toBeGreaterThan(Math.max(...layout.numbers.map((n) => n.y)));
  });
});

describe("lineLayout", () => {
  it("gives every bound and mark a tick, and a mark its dot unless it sits on an interval's bound", () => {
    const fig = line({
      intervals: [iv(2, 5, "right")],
      marks: [{ x: 2, label: "$a$" }, { x: 3 }],
    });
    // 2 is an excluded bound in every convention: a filled mark dot there would say it
    // is included (the probe run caught a « point plein » on an excluded bound).
    for (const convention of ["brackets", "dots", "hatched"] as const) {
      const layout = lineLayout({ ...fig, convention }, 294);
      expect(layout.bounds.map((b) => [b.mark, b.dot])).toEqual([
        [true, false],
        [true, true],
        [false, false],
      ]);
    }
  });

  it.each([1e-100, 1e-300, Number.MIN_VALUE, 1e-12])(
    "never throws on numbers %s apart, and draws them at one place",
    (gap) => {
      const fig = line({ marks: [{ x: 0 }, { x: gap }] });
      const layout = lineLayout(fig, 294);
      expect(Number.isFinite(layout.height)).toBe(true);
      expect(layout.ticks.hi).toBeGreaterThan(layout.ticks.lo);
      const [a, b] = layout.bounds;
      expect(Math.abs((a?.x ?? 0) - (b?.x ?? 1))).toBeLessThan(0.01);
    },
  );

  it.each([294, 560, 1200])(
    "draws a thousandth apart, the smallest span the tool accepts, with distinct graduations at %i px",
    (W) => {
      const layout = lineLayout(line({ marks: [{ x: 0 }, { x: 1e-3 }] }), W);
      const [a, b] = layout.bounds;
      expect(Math.abs((a?.x ?? 0) - (b?.x ?? 0))).toBeGreaterThan(100);
      const written = layout.ticks.ticks.map(formatNumber);
      expect(new Set(written).size).toBe(written.length);
    },
  );

  it("spans 0 to 7 for S = ]−∞ ; 2] ∪ ]5 ; +∞[", () => {
    const { ticks } = lineLayout(line(UNION), 294);
    expect([ticks.lo, ticks.hi]).toEqual([0, 7]);
  });

  it("pads more on a side where an interval runs to infinity", () => {
    const layout = lineLayout(line({ intervals: [iv(2, null, "left")], marks: [{ x: 0 }] }), 294);
    const room = (v: number) => layout.x(v);
    // From 2 to the right end, against from 0 to the left end.
    expect(layout.ticks.hi - 2).toBeGreaterThan(0 - layout.ticks.lo);
    expect(room(layout.ticks.hi)).toBeGreaterThan(room(2));
  });

  it("puts close numbers in different rows under the axis, none overlapping", () => {
    const marks = [
      { x: 0 },
      { x: 1.4 },
      { x: Math.SQRT2, label: "$\\sqrt{2}$" },
      { x: 1.5 },
      { x: 3 },
    ];
    const layout = lineLayout(line({ marks }), 294);
    const rows = ["$\\sqrt{2}$", "1,4", "1,5"].map(
      (t) => layout.numbers.find((n) => n.text === t)?.y,
    );
    expect(rows.every((y) => y !== undefined)).toBe(true);
    expect(new Set(rows).size).toBe(3);
    for (const a of layout.numbers) {
      for (const b of layout.numbers) {
        if (a === b || a.y !== b.y) continue;
        expect(Math.abs(a.x - b.x)).toBeGreaterThanOrEqual((textPx(a.text) + textPx(b.text)) / 2);
      }
    }
  });
});

describe("brackets and hatching", () => {
  it("points a bracket's arms as the notation writes it", () => {
    expect(bracketArms("start", true)).toBe(1);
    expect(bracketArms("start", false)).toBe(-1);
    expect(bracketArms("end", true)).toBe(-1);
    expect(bracketArms("end", false)).toBe(1);
  });

  it("hatches what the set leaves out", () => {
    expect(complement([iv(null, 2, "right")], -10, 10)).toEqual([[2, 10]]);
    expect(complement([iv(null, 2, "right"), iv(5, null, "left")], -10, 10)).toEqual([[2, 5]]);
    expect(complement([iv(0, 1, "both")], -1, 2)).toEqual([
      [-1, 0],
      [1, 2],
    ]);
  });
});

describe("hatching, lane by lane", () => {
  const hatched = (intervals: CleanInterval[], more: object = {}) =>
    lineLayout(line({ intervals, convention: "hatched", ...more }), 294);

  it("hatches only ]2 ; 5[ between two unlabelled intervals sharing the axis", () => {
    // x ≤ 2 ou x ≥ 5: each set hatching its own complement would hatch the whole
    // axis, and read « aucun nombre ne convient ».
    const layout = hatched([iv(null, 2, "right"), iv(5, null, "left")]);
    // Under hatching the unlabelled pieces are one solution: one group, one lane.
    expect(layout.groups.map((g) => [g.lane, g.pieces.length])).toEqual([[0, 2]]);
    expect(layout.hatches).toEqual([
      { lane: 0, y: layout.axisY, spans: [[layout.x(2), layout.x(5)]] },
    ]);
  });

  it("hatches the two gaps between three unlabelled pieces, and nothing else", () => {
    const layout = hatched([iv(null, -3, "right"), iv(-1, 1, "both"), iv(4, null, "neither")]);
    expect(layout.groups.map((g) => [g.lane, g.pieces.length])).toEqual([[0, 3]]);
    expect(layout.hatches.map((h) => h.spans)).toEqual([
      [
        [layout.x(-3), layout.x(-1)],
        [layout.x(1), layout.x(4)],
      ],
    ]);
  });

  it("leaves no sliver of hatching where two pieces of one set touch", () => {
    // ]−∞ ; 2[ ∪ ]2 ; 5]: 2 is left out by its brackets, not by a hatch of no width.
    const layout = hatched([iv(null, 2, "neither", "$S$"), iv(2, 5, "right", "$S$")]);
    expect(layout.hatches.map((h) => h.spans)).toEqual([[[layout.x(5), layout.x1 - 10]]]);
  });

  it("draws touching unlabelled pieces as one set, hatching what their union leaves out", () => {
    // The tool refuses them (`union`); a replayed card still draws one true picture.
    const layout = hatched([iv(null, 2, "right"), iv(2, 5, "right")]);
    expect(layout.groups.map((g) => g.lane)).toEqual([0]);
    expect(layout.hatches.map((h) => h.spans)).toEqual([[[layout.x(5), layout.x1 - 10]]]);
  });

  it("hatches nothing when the line has marks but no interval", () => {
    // An empty lane's complement is the whole axis: « aucun nombre ne convient ». (A
    // line with nothing at all never gets here: sanitise makes it « Figure vide ».)
    expect(lineLayout(line({ convention: "hatched", marks: [{ x: 2 }] }), 294).hatches).toEqual([]);
  });

  it("hatches the same with and without values", () => {
    const pieces = [iv(null, 2, "right"), iv(5, null, "left")];
    const spans = (values: boolean) =>
      lineLayout(
        line({ intervals: pieces, convention: "hatched", show_values: values }),
        294,
      ).hatches.map((h) => h.spans.map(([a, b]) => [Math.round(a), Math.round(b)]));
    expect(spans(true)).toEqual(spans(false));
  });

  it("hatches nothing on a lane its pieces fill", () => {
    // ℝ privé de 2: nothing hatched, the brackets at 2 say it is left out.
    expect(
      hatched([iv(null, 2, "neither", "$S$"), iv(2, null, "neither", "$S$")]).hatches[0]?.spans,
    ).toEqual([]);
    expect(hatched([iv(null, null, "neither")]).hatches[0]?.spans).toEqual([]);
  });

  it.each([
    ["two unlabelled", [iv(null, 2, "right"), iv(5, null, "left")], false],
    ["two unlabelled, written", [iv(null, 2, "right"), iv(5, null, "left")], true],
    ["three pieces", [iv(null, -3, "right"), iv(-1, 1, "both"), iv(4, null, "neither")], false],
    ["overlapping", [iv(0, 3, "both"), iv(2, 5, "both"), iv(7, 8, "left")], false],
    ["two sets", [iv(-2, 5, "both", "A"), iv(0, 3, "both", "B"), iv(6, 7, "both")], true],
    [
      "a union",
      [iv(null, -1, "right", "S"), iv(1, 2, "both", "S"), iv(3, null, "left", "S")],
      true,
    ],
  ] as [string, CleanInterval[], boolean][])(
    "never hatches a lane over its own pieces, and hatches all the rest (%s)",
    (_, intervals, showValues) => {
      const layout = hatched(intervals, { show_values: showValues });
      const lanes = new Set(layout.groups.map((g) => g.lane));
      expect(layout.hatches.map((h) => h.lane)).toEqual([...lanes].sort((a, b) => a - b));
      const end = layout.x1 - 10;
      for (const h of layout.hatches) {
        const pieces = layout.groups
          .filter((g) => g.lane === h.lane)
          .flatMap((g) => g.pieces)
          .map((p) => [p.from, p.to] as const);
        for (const [a, b] of h.spans) {
          for (const [p, q] of pieces) expect(b <= p || a >= q).toBe(true);
        }
        // Pieces and hatching, together, cover the axis from x0 to the arrow.
        const covered = [...pieces, ...h.spans].sort((s, t) => s[0] - t[0]);
        let reach = layout.x0;
        for (const [a, b] of covered) {
          expect(a).toBeLessThanOrEqual(reach + 1e-9);
          reach = Math.max(reach, b);
        }
        expect(reach).toBeCloseTo(end, 9);
      }
    },
  );

  it("hatches nothing in the other conventions", () => {
    for (const convention of ["brackets", "dots"] as const) {
      const fig = line({ intervals: [iv(null, 2, "right"), iv(5, null, "left")], convention });
      expect(lineLayout(fig, 294).hatches).toEqual([]);
    }
  });
});
