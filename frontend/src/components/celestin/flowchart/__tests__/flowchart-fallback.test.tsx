// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FlowchartView } from "../flowchart-view";
import { HIDDEN, LOOP, SECRET } from "./fixtures";

// A drawing that cannot be laid out (here, one that throws) is listed instead.
vi.mock("../layout", async (original) => ({
  ...(await original<typeof import("../layout")>()),
  layoutFlowchart: () => {
    throw new Error("no layout");
  },
}));

afterEach(cleanup);

describe("FlowchartView without a layout", () => {
  it("lists the steps visibly, with its sentence, and never scrolls", () => {
    const { container } = render(<FlowchartView block={LOOP} />);
    expect(container.querySelector('[role="img"]')).toBeNull();
    expect(container.textContent).toContain(
      "Cet organigramme est trop large pour cet écran ; le voici étape par étape.",
    );
    const visible = container.querySelector("ol:not(.sr-only)")!;
    expect(visible.children).toHaveLength(LOOP.nodes.length);
    expect(visible.textContent).toContain("Étape 1 — départ : Début.");
    // Screen readers read the MathML list once, not the visible copy.
    expect(visible.getAttribute("aria-hidden")).toBe("true");
    expect(container.querySelector("ol.sr-only math")).not.toBeNull();
    expect(container.querySelector('[class*="overflow-x"]')).toBeNull();
  });

  it("keeps a hidden box's text out of the list too", () => {
    const { container } = render(<FlowchartView block={HIDDEN} />);
    expect(container.innerHTML).not.toContain(SECRET);
    expect(container.textContent).toContain("à compléter");
  });
});
