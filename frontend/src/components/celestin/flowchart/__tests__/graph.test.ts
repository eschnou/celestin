import { describe, expect, it } from "vitest";
import type { FlowchartBlock } from "@/lib/tutor/types";
import { edgeId, pathState, readingOrder, sanitise } from "../graph";
import { HIDDEN, LOOP, PATH, SECRET } from "./fixtures";

const block = (nodes: unknown, extra: Record<string, unknown> = {}) =>
  ({ type: "flowchart", nodes, ...extra }) as FlowchartBlock;

describe("sanitise", () => {
  it("drops what a stored flowchart may carry that cannot be drawn", () => {
    const g = sanitise(
      block([
        {
          id: "a",
          text: "A",
          kind: "decision",
          next: [
            { to: "b", label: "oui" },
            { to: "zz", label: "non" },
            { to: "a", label: "boucle" },
            { to: "b", label: "encore" },
            { to: "c", label: "non" },
            { to: "d", label: "trop" },
          ],
        },
        { id: "b", text: "B", next: [{ to: "c" }, { to: "d" }] },
        { id: "a", text: "Doublon" },
        { id: "c", text: "C" },
        { id: "d", text: "D", kind: "loop" },
        { id: "", text: "Sans id" },
        { id: "e" },
        "pas un nœud",
      ]),
    );
    expect(g.nodes.map((n) => n.text)).toEqual(["A", "B", "C", "D"]);
    // A dangling exit, a self loop and a repeated target go; a third exit too.
    expect(g.nodes[0]!.exits).toEqual([
      { to: 1, label: "oui" },
      { to: 2, label: "non" },
    ]);
    // A step keeps one exit.
    expect(g.nodes[1]!.exits).toEqual([{ to: 2, label: null }]);
    expect(g.nodes[3]!.kind).toBe("step");
  });

  it("reads a label of spaces only as no label", () => {
    const g = sanitise(
      block([
        { id: "a", text: "A", next: [{ to: "b", label: "  " }] },
        { id: "b", text: "B" },
      ]),
    );
    expect(g.nodes[0]!.exits).toEqual([{ to: 1, label: null }]);
  });

  it("keeps twelve nodes at most", () => {
    const nodes = Array.from({ length: 15 }, (_, i) => ({ id: `n${i}`, text: `N${i}` }));
    expect(sanitise(block(nodes)).nodes).toHaveLength(12);
  });

  it("filters path and hidden to known nodes", () => {
    const g = sanitise({
      ...LOOP,
      path: ["debut", "zz", 3, "lire"],
      hidden: ["fin", "zz", null],
    } as never);
    expect(g.path).toEqual([0, 1]);
    expect(g.nodes[7]!.hidden).toBe(true);
    expect(g.nodes.filter((n) => n.hidden)).toHaveLength(1);
  });

  it("drops a hidden node's text right there", () => {
    const g = sanitise(HIDDEN);
    const quot = g.nodes[3]!;
    expect(quot).toMatchObject({ hidden: true, text: "?" });
    expect(JSON.stringify(g)).not.toContain(SECRET);
    expect(JSON.stringify(g)).not.toContain("quotients");
  });

  it("reads anything that is not a flowchart as an empty one", () => {
    for (const bad of [null, "x", 3, { nodes: "x" }, { nodes: [null] }]) {
      expect(sanitise(bad as never)).toEqual({ nodes: [], path: [], caption: null });
    }
    expect(sanitise(block([], { caption: 12 })).caption).toBeNull();
  });

  it("keeps the first node first, whatever its id looks like", () => {
    const g = sanitise(
      block([
        { id: "10", text: "Dix", next: [{ to: "2" }] },
        { id: "2", text: "Deux", next: [{ to: "debut" }] },
        { id: "debut", text: "Début" },
      ]),
    );
    expect(g.nodes[0]!.text).toBe("Dix");
    expect(readingOrder(g)).toEqual([0, 1, 2]);
  });
});

describe("readingOrder", () => {
  it("walks depth-first in exit order, then appends what was not reached", () => {
    const g = sanitise(
      block([
        {
          id: "q",
          text: "Q ?",
          kind: "decision",
          next: [
            { to: "b", label: "non" },
            { to: "a", label: "oui" },
          ],
        },
        { id: "a", text: "A" },
        { id: "b", text: "B", next: [{ to: "c" }] },
        { id: "c", text: "C" },
        { id: "seul", text: "Seul" },
      ]),
    );
    expect(readingOrder(g)).toEqual([0, 2, 3, 1, 4]);
  });
});

describe("pathState", () => {
  it("marks the nodes walked, the one in progress and the edges followed", () => {
    const g = sanitise(PATH);
    const walk = pathState(g);
    expect(walk.current).toBe(3);
    expect([...walk.visited].sort()).toEqual([0, 1, 2, 4, 5]);
    expect(walk.edges.has(edgeId(3, 0))).toBe(true);
    expect(walk.edges.has(edgeId(5, 0))).toBe(true);
    expect(walk.edges.has(edgeId(3, 1))).toBe(false);
  });

  it("is empty without a path", () => {
    expect(pathState(sanitise(LOOP))).toEqual({
      visited: new Set(),
      current: null,
      edges: new Set(),
    });
  });
});
