// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FlowchartView } from "../flowchart-view";
import { measuredSize } from "../use-label-sizes";
import { METHOD } from "./fixtures";

// jsdom lays nothing out, so these getters stand in for a browser: a node
// label's block reports its max-width (CSS shrink-to-fit once its text wraps),
// the RichText span inside it the width of its widest line.
const TIGHT = 70;
const EDGE = 20;

beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockImplementation(function (
    this: HTMLElement,
  ) {
    if (this.tagName === "SPAN") return TIGHT;
    const cap = parseFloat(this.style.maxWidth);
    return Number.isFinite(cap) ? cap : EDGE;
  });
  vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockImplementation(function (
    this: HTMLElement,
  ) {
    return this.tagName === "SPAN" ? 16 : 32;
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function block(maxWidth: number | null, inner: string): HTMLElement {
  const box = document.createElement("div");
  if (maxWidth !== null) box.style.maxWidth = `${maxWidth}px`;
  box.innerHTML = inner;
  return box;
}

describe("measuredSize", () => {
  const node = { kind: "node", node: 0, rung: 0, text: "Calculer" } as const;
  const edge = { kind: "edge", edge: 0, text: "oui" } as const;

  it("takes a wrapped label's widest line, not the rung its block is capped at", () => {
    expect(measuredSize(block(220, "<span>Calculer</span>"), node)).toEqual({ w: TIGHT, h: 32 });
  });

  it("keeps the block's width around display maths, and for an answer on one line", () => {
    const display = block(220, '<span><span class="katex-display">x</span></span>');
    expect(measuredSize(display, node).w).toBe(220);
    expect(measuredSize(block(null, "<span>oui</span>"), edge).w).toBe(EDGE);
  });
});

describe("FlowchartView, measured", () => {
  it("draws each box around its label's widest line", () => {
    const { container } = render(<FlowchartView block={METHOD} />);
    const labels = [...container.querySelectorAll<HTMLElement>('[role="img"] div.text-center')];
    expect(labels).toHaveLength(METHOD.nodes.length);
    for (const label of labels) expect(label.style.width).toBe(`${TIGHT + 1}px`);
  });
});
