// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { FlowchartBlock } from "@/lib/tutor/types";
import { FlowchartView } from "../flowchart-view";
import { FIXTURES, HIDDEN, LOOP, METHOD, PATH, SECRET } from "./fixtures";

afterEach(cleanup);

const mount = (block: FlowchartBlock) => render(<FlowchartView block={block} />);

/** React props starting with `on` on any element: nothing on the board reacts to the pointer. */
function handlers(container: HTMLElement): string[] {
  return [...container.querySelectorAll("*")].flatMap((el) =>
    Object.keys(el)
      .filter((k) => k.startsWith("__reactProps"))
      .flatMap((k) =>
        Object.keys((el as unknown as Record<string, Record<string, unknown>>)[k] ?? {}).filter(
          (p) => p.startsWith("on"),
        ),
      ),
  );
}

describe("FlowchartView", () => {
  it.each(Object.entries(FIXTURES))("draws %s", (_, block) => {
    const { container, getByRole } = mount(block);
    expect(getByRole("img").getAttribute("aria-label")).toBe(
      `Organigramme en ${block.nodes.length} étapes`,
    );
    expect(container.querySelector("svg")).not.toBeNull();
    // One outline per node, one label per node and per answer.
    expect(container.querySelectorAll("svg g[data-state]")).toHaveLength(block.nodes.length);
    expect(container.querySelector("ol.sr-only")?.children).toHaveLength(block.nodes.length);
  });

  it("typesets maths in the boxes, and as MathML for screen readers", () => {
    const { container } = mount(LOOP);
    const drawing = container.querySelector('[role="img"]')!;
    expect(drawing.querySelectorAll(".katex").length).toBeGreaterThan(0);
    const list = container.querySelector("ol.sr-only")!;
    expect(list.querySelectorAll("math").length).toBeGreaterThan(0);
    expect(list.querySelector(".katex-html")).toBeNull();
    expect(list.textContent).toContain("Étape 4 — question :");
  });

  it("draws geometry only: no SVG text, no tooltip, nothing that reacts to the pointer", () => {
    for (const block of Object.values(FIXTURES)) {
      const { container, unmount } = mount(block);
      expect(container.querySelector("svg text")).toBeNull();
      expect(container.querySelector("svg title")).toBeNull();
      expect(container.querySelector("[title]")).toBeNull();
      expect(handlers(container)).toEqual([]);
      unmount();
    }
  });

  it("never writes a hidden box's text, anywhere", () => {
    const { container } = mount(HIDDEN);
    const html = container.innerHTML;
    expect(html).not.toContain(SECRET);
    expect(html).not.toContain("quotients");
    expect(container.querySelectorAll('g[data-state="hidden"]')).toHaveLength(1);
    const labels = [...container.querySelectorAll('[role="img"] div[aria-hidden]')].map(
      (d) => d.textContent,
    );
    expect(labels).toContain("?");
    expect(container.querySelector("ol.sr-only")?.textContent).toContain("à compléter");
    // Other boxes and the answers are still written.
    expect(html).toContain("différences");
    expect(labels).toContain("non");
  });

  it("marks the walk-through and does not replay the drawing", () => {
    const { container } = mount(PATH);
    const states = [...container.querySelectorAll("g[data-state]")].map((g) =>
      g.getAttribute("data-state"),
    );
    expect(states).toEqual(["path", "path", "path", "current", "path", "path", "idle", "idle"]);
    expect(container.querySelector(".flow-enter")).toBeNull();
    expect(container.querySelector(".chart-trace")).toBeNull();
    expect(container.querySelectorAll("path.stroke-primary").length).toBeGreaterThan(0);
    cleanup();
    const fresh = mount(LOOP).container;
    expect(fresh.querySelector(".flow-enter")).not.toBeNull();
    expect(fresh.querySelector(".chart-trace")).not.toBeNull();
    expect(fresh.querySelector("path.stroke-primary")).toBeNull();
  });

  it("measures in a layer that takes no room", () => {
    const { container } = mount(METHOD);
    const layer = [...container.querySelectorAll("div.invisible")].find((d) =>
      d.classList.contains("overflow-hidden"),
    );
    expect(layer).toBeDefined();
    for (const name of ["h-0", "w-0", "overflow-hidden", "absolute"]) {
      expect(layer!.classList.contains(name)).toBe(true);
    }
    expect(layer!.getAttribute("aria-hidden")).toBe("true");
  });

  it("writes the caption under the drawing", () => {
    const { container } = mount({ ...METHOD, caption: "Méthode du cours ($u_1$ d'abord)" });
    expect(container.querySelector("figcaption")?.textContent).toContain("Méthode du cours");
    expect(container.querySelector("figcaption .katex")).not.toBeNull();
  });

  it("survives a malformed stored flowchart", () => {
    const empty = mount({ type: "flowchart", nodes: "x" } as unknown as FlowchartBlock);
    expect(empty.container.textContent).toContain("Organigramme vide");
    expect(empty.container.querySelector("ol.sr-only")).toBeNull();
    cleanup();

    const broken = {
      type: "flowchart",
      nodes: [
        { id: "a", text: "Début", next: [{ to: "zz" }, { to: "b" }] },
        { id: "b", kind: "boucle", text: "Suite", next: "x" },
        { id: "c" },
        { id: "d", text: "Fin", next: [{ to: "d" }, null] },
      ],
      path: [42, "b"],
      hidden: "a",
      caption: { x: 1 },
    } as unknown as FlowchartBlock;
    let container: HTMLElement | undefined;
    expect(() => (container = mount(broken).container)).not.toThrow();
    expect(container!.querySelector('[role="img"]')?.getAttribute("aria-label")).toBe(
      "Organigramme en 3 étapes",
    );
    expect(container!.textContent).toContain("Suite");
    expect(container!.querySelector("figcaption")).toBeNull();
  });

  it("keeps its DOM when the same block is shown again", () => {
    const view = mount(LOOP);
    const svg = view.container.querySelector("svg");
    view.rerender(<FlowchartView block={LOOP} />);
    expect(view.container.querySelector("svg")).toBe(svg);
  });
});
