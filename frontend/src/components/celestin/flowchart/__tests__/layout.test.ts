import { describe, expect, it } from "vitest";
import type { FlowchartBlock } from "@/lib/tutor/types";
import { edgeId, sanitise } from "../graph";
import {
  fit,
  layers,
  layoutFlowchart,
  metricsFor,
  MIN_SCALE,
  structure,
  type Structure,
} from "../layout";
import { labelSizes, measureItems } from "../measure";
import cases from "./layer_cases.json";
import { FIXTURES, LONG_EDGE, LOOP, MERGE, METHOD, NESTED, REPEAT, TWO_WHILES } from "./fixtures";
import {
  laidOut,
  mulberry32,
  randomChart,
  sharedStretches,
  varied,
  violations,
} from "./invariants";

const shaped = (block: FlowchartBlock): Structure => structure(sanitise(block));
const index = (block: FlowchartBlock, id: string) => block.nodes.findIndex((n) => n.id === id);

describe("layers", () => {
  it.each(cases.cases.map((c) => [c.name, c] as const))("matches the shared case %s", (_, c) => {
    const { row, loops } = layers(c.exits);
    expect(row).toEqual(c.rows);
    expect([...loops].sort((a, b) => a[0] - b[0] || a[1] - b[1])).toEqual(c.loops);
  });

  it("starts from the first node whatever its id looks like", () => {
    const g = sanitise({
      type: "flowchart",
      nodes: [
        { id: "10", text: "A", next: [{ to: "2" }] },
        { id: "2", text: "B", next: [{ to: "debut" }] },
        { id: "debut", text: "C" },
      ],
    });
    expect(structure(g).row.slice(0, 3)).toEqual([0, 1, 2]);
  });
});

describe("structure", () => {
  it("finds the while loop's way back to its test", () => {
    const st = shaped(LOOP);
    expect(st.loops.map(({ u, v }) => [u, v])).toEqual([
      [index(LOOP, "incr"), index(LOOP, "test")],
    ]);
  });

  it("gives a long edge one passage per row it crosses", () => {
    const st = shaped(MERGE);
    const d = index(MERGE, "d");
    const stations = st.chain.get(edgeId(d, 1))!;
    expect(stations).toHaveLength(3);
    expect(stations.slice(0, 2).every((s) => s >= st.n)).toBe(true);
    expect(stations.map((s) => st.row[s])).toEqual([2, 3, 4]);
  });

  it("puts the heavier branch first", () => {
    const st = shaped(METHOD);
    const row = st.order[2]!;
    expect(row.indexOf(index(METHOD, "quot"))).toBeLessThan(row.indexOf(index(METHOD, "sa")));
  });

  it.each(Object.entries(FIXTURES))("crosses no edges in %s", (_, block) => {
    const st = shaped(block);
    const pos = new Map<number, number>();
    for (const items of st.order) items.forEach((x, i) => pos.set(x, i));
    for (let r = 0; r + 1 < st.order.length; r++) {
      const edges = st.order[r]!.flatMap((a) =>
        st.succs[a]!.map((b) => [pos.get(a)!, pos.get(b)!]),
      );
      for (const [a, b] of edges)
        for (const [c, d] of edges) expect((a! - c!) * (b! - d!)).toBeGreaterThanOrEqual(0);
    }
  });

  it("sends a question's left answer down and its right answer to the side", () => {
    const st = shaped(METHOD);
    const d1 = index(METHOD, "d1");
    // quot is the heavier branch, so it is on the left, under the question.
    expect(st.port.get(edgeId(d1, 1))).toBe("B");
    expect(st.port.get(edgeId(d1, 0))).toBe("R");
  });

  it("sends a question's loop out of its left vertex", () => {
    const st = shaped(REPEAT);
    const t = index(REPEAT, "t");
    expect(st.port.get(edgeId(t, 0))).toBe("L");
    expect(st.port.get(edgeId(t, 1))).toBe("B");
  });
});

describe("fit", () => {
  it("sets two boxes that both want 0 symmetric", () => {
    const [a, b] = fit([0, 0], [10, 10], [10, 10], 4);
    expect(a).toBeCloseTo(-12);
    expect(b).toBeCloseTo(12);
  });

  it("leaves a lone box where it wants to be", () => {
    expect(fit([37], [5], [9], 12)).toEqual([37]);
  });

  it("keeps order and gaps on random inputs", () => {
    const rand = mulberry32(42);
    for (let run = 0; run < 200; run++) {
      const n = 1 + Math.floor(rand() * 6);
      const d = Array.from({ length: n }, () => rand() * 400 - 200);
      const eL = Array.from({ length: n }, () => 4 + rand() * 80);
      const eR = Array.from({ length: n }, () => 4 + rand() * 80);
      const x = fit(d, eL, eR, 12);
      for (let i = 1; i < n; i++)
        expect(x[i]! - eL[i]! - (x[i - 1]! + eR[i - 1]!)).toBeGreaterThanOrEqual(12 - 1e-6);
    }
  });
});

describe("placement", () => {
  it("draws a chain straight down", () => {
    const { layout } = laidOut(LOOP, 560);
    const xs = ["debut", "lire", "init", "test"].map((id) => layout.nodes[index(LOOP, id)]!.x);
    for (const x of xs) expect(x).toBeCloseTo(xs[0]!, 6);
  });

  it("sets a question's bottom answer right under it when the other sits beside it", () => {
    for (const block of [METHOD, NESTED]) {
      for (const width of [268, 560]) {
        const { layout } = laidOut(block, width);
        const st = shaped(block);
        for (const node of sanitise(block).nodes) {
          if (node.kind !== "decision" || node.exits.length < 2) continue;
          const bottom = node.exits.findIndex((_, k) => st.port.get(edgeId(node.index, k)) === "B");
          const child = node.exits[bottom]!.to;
          expect(layout.nodes[child]!.x).toBeCloseTo(layout.nodes[node.index]!.x, 6);
        }
      }
    }
  });
});

describe("invariants", () => {
  it.each(Object.entries(FIXTURES))("hold on %s at every width", (_, block) => {
    for (const width of [268, 560, 800]) {
      expect(violations(laidOut(block, width).layout), `${width}`).toEqual([]);
    }
  });

  // DEC_STEP_ROW is left out: a question beside an io box is the tightest row
  // seen, right at the 0,85 floor with estimated sizes (see the next test).
  const { DEC_STEP_ROW, ...phone } = FIXTURES;
  it.each(Object.entries(phone))("fit %s on a phone's board", (_, block) => {
    const graph = sanitise(block);
    const sizes = labelSizes(graph, measureItems(graph), [], metricsFor(268)).sizes;
    const layout = layoutFlowchart(graph, sizes, 268);
    expect(layout).not.toBeNull();
    expect(layout!.scale).toBeGreaterThanOrEqual(MIN_SCALE);
    expect(layout!.width * layout!.scale).toBeLessThanOrEqual(268 + 0.01);
  });

  it("draws the tightest row slightly smaller, or lists it, never smaller than the floor", () => {
    const { graph, layout } = laidOut(DEC_STEP_ROW, 268);
    expect(layout.level).toBe(4);
    expect(layout.scale).toBeGreaterThan(0.8);
    const sizes = labelSizes(graph, measureItems(graph), [], metricsFor(268)).sizes;
    const shown = layoutFlowchart(graph, sizes, 268);
    expect(shown === null).toBe(layout.scale < MIN_SCALE);
  });

  it("draws every fixture at full size on a desktop board", () => {
    for (const block of Object.values(FIXTURES)) expect(laidOut(block, 560).layout.scale).toBe(1);
  });

  it("gives up on a row too wide for a phone, for the list to take over", () => {
    const wide: FlowchartBlock = {
      type: "flowchart",
      nodes: [
        { id: "a", text: "Commencer par lire toutes les données", next: [{ to: "d" }] },
        {
          id: "d",
          kind: "decision",
          text: "La variable est-elle qualitative ?",
          next: [
            { to: "d2", label: "oui" },
            { to: "d3", label: "non" },
          ],
        },
        {
          id: "d2",
          kind: "decision",
          text: "Les modalités sont-elles ordonnées ?",
          next: [
            { to: "w", label: "oui" },
            { to: "x", label: "non" },
          ],
        },
        {
          id: "d3",
          kind: "decision",
          text: "La variable est-elle discrète ?",
          next: [
            { to: "y", label: "oui" },
            { to: "z", label: "non" },
          ],
        },
        { id: "w", text: "Diagramme en barres ordonnées" },
        { id: "x", text: "Diagramme circulaire des modalités" },
        { id: "y", text: "Diagramme en bâtons des valeurs" },
        { id: "z", text: "Histogramme des classes" },
      ],
    };
    const graph = sanitise(wide);
    const sizes = labelSizes(graph, measureItems(graph), [], metricsFor(268)).sizes;
    expect(layoutFlowchart(graph, sizes, 268)).toBeNull();
    expect(violations(laidOut(wide, 268).layout)).toEqual([]);
  });

  it("hold on random flowcharts the tool accepts", () => {
    const rand = mulberry32(7);
    let charts = 0;
    while (charts < 300) {
      const block = randomChart(rand);
      if (!block) continue;
      charts += 1;
      for (const [width, chart] of [
        [268, block],
        [560, block],
        [400, varied(block, rand)],
      ] as const) {
        const found = violations(laidOut(chart, width).layout);
        expect(found, `${width} ${JSON.stringify(chart)}`).toEqual([]);
      }
    }
  });

  it("are checked for real: a label moved onto a box is caught", () => {
    const { layout } = laidOut(METHOD, 560);
    const [edge] = layout.edges.filter((e) => e.label);
    const box = layout.nodes[0]!;
    edge!.label = { ...edge!.label!, left: box.x, top: box.cy };
    expect(violations(layout).some((v) => v.startsWith(`label ${edge!.id} over box 0`))).toBe(true);
  });

  it("gives two loops that meet in a gap a lane each", () => {
    for (const width of [268, 560]) {
      const { layout } = laidOut(TWO_WHILES, width);
      // A loop's last three points: up its lane, along the bar, down into its test.
      const lanes = layout.edges
        .filter((e) => e.loop)
        .map((e) => e.points[e.points.length - 3]![0]);
      expect(lanes).toHaveLength(2);
      expect(Math.abs(lanes[0]! - lanes[1]!)).toBeCloseTo(layout.metrics.lane, 6);
    }
  });

  it("keeps a long edge's way down off another edge's way into its box", () => {
    for (const width of [400, 560, 800])
      expect(sharedStretches(laidOut(LONG_EDGE, width).layout), `${width}`).toEqual([]);
  });

  it("are checked for real: two edges into different boxes along one line are caught", () => {
    const { layout } = laidOut(METHOD, 560);
    const edge = (id: number, to: number, x: number, y1: number, y2: number) => ({
      id,
      from: 0,
      to,
      loop: false,
      port: "B" as const,
      points: [
        [x, y1],
        [x, y2],
      ] as [number, number][],
      label: null,
    });
    const along = { ...layout, edges: [edge(0, 1, 10, 0, 50), edge(2, 2, 12, 40, 90)] };
    expect(sharedStretches(along)).toEqual(["edges 0 and 2 run along each other"]);
    // Into the same box they merge on purpose; a few pixels apart they read as two.
    const merged = { ...layout, edges: [edge(0, 1, 10, 0, 50), edge(2, 1, 10, 40, 90)] };
    expect(sharedStretches(merged)).toEqual([]);
    const apart = { ...layout, edges: [edge(0, 1, 10, 0, 50), edge(2, 2, 16, 40, 90)] };
    expect(sharedStretches(apart)).toEqual([]);
  });

  it("uses the compact metrics on a phone", () => {
    expect(metricsFor(300).compact).toBe(true);
    expect(metricsFor(560).compact).toBe(false);
  });
});
