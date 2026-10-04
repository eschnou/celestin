// @vitest-environment jsdom
/** A flowchart read in English: our words change, Célestin's texts and answers do not. */
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe as suite, expect, it } from "vitest";
import { withLocale } from "@/test/locale";
import { describe, stepText } from "../describe";
import { sanitise } from "../graph";
import { FlowchartView } from "../flowchart-view";
import { HIDDEN, LOOP, METHOD, NESTED, PATH, SECRET } from "./fixtures";

afterEach(cleanup);
const read = (block: Parameters<typeof sanitise>[0]) => describe(sanitise(block)).map(stepText);

suite("flowchart describe in English", () => {
  it("reads the method in order, each answer with where it leads", () =>
    withLocale("en", () => {
      expect(read(METHOD)).toEqual([
        "Step 1 — Calculer les différences entre termes consécutifs.",
        "Step 2 — question: Sont-elles égales ? If “oui”: step 3. If “non”: step 4.",
        "Step 3 — C'est une SA. End of the path.",
        "Step 4 — Calculer les quotients entre termes consécutifs.",
        "Step 5 — question: Sont-ils égaux ? If “oui”: step 6.",
        "Step 6 — C'est une SG. End of the path.",
      ]);
    }));

  it("says where a loop goes back to and names the kinds of boxes", () =>
    withLocale("en", () => {
      const steps = read(LOOP);
      expect(steps[0]).toBe("Step 1 — start: Début.");
      expect(steps[1]).toBe("Step 2 — input or output: Lire $n$.");
      expect(steps[3]).toBe(
        "Step 4 — question: $i \\leqslant n$ ? If “oui”: step 5. If “non”: step 7.",
      );
      expect(steps[5]).toBe("Step 6 — $i \\leftarrow i + 1$. Back to step 4.");
      expect(steps[7]).toBe("Step 8 — end: Fin.");
      expect(read(NESTED).filter((s) => s.endsWith(" End of the path."))).toHaveLength(3);
    }));

  it("reads an arrow's label and a jump", () =>
    withLocale("en", () => {
      expect(
        read({
          type: "flowchart",
          nodes: [
            { id: "a", text: "Lancer le dé", next: [{ to: "b", label: "puis" }] },
            { id: "b", text: "Noter le résultat", next: [{ to: "a", label: "$n < 10$" }] },
          ],
        }),
      ).toEqual([
        "Step 1 — Lancer le dé. Arrow “puis”: step 2.",
        "Step 2 — Noter le résultat. Arrow “$n < 10$”: back to step 1.",
      ]);
      const steps = read({
        type: "flowchart",
        nodes: [
          {
            id: "q",
            kind: "decision",
            text: "Q ?",
            next: [
              { to: "a", label: "oui" },
              { to: "b", label: "non" },
            ],
          },
          { id: "a", text: "A", next: [{ to: "c" }] },
          { id: "b", text: "B", next: [{ to: "c" }] },
          { id: "c", text: "C" },
        ],
      });
      expect(steps[3]).toBe("Step 4 — B. Next: step 3.");
    }));

  it("reads a hidden box as to be filled in, never its text, and marks the walk-through", () =>
    withLocale("en", () => {
      const steps = read(HIDDEN);
      expect(steps[3]).toBe("Step 4 — to fill in.");
      expect(steps.join(" ")).not.toContain(SECRET);
      const walk = read(PATH);
      expect(walk[3]).toContain("(current step)");
      expect(walk[4]).toContain("(already visited)");
    }));
});

suite("FlowchartView in English", () => {
  it("labels the drawing with a plural and puts the steps in the interface language", () =>
    withLocale("en", () => {
      const { container, getByRole } = render(<FlowchartView block={METHOD} />);
      expect(getByRole("img").getAttribute("aria-label")).toBe(
        `Flowchart in ${METHOD.nodes.length} steps`,
      );
      expect(container.querySelector("ol.sr-only")?.getAttribute("lang")).toBe("en");
      cleanup();
      const empty = render(<FlowchartView block={{ type: "flowchart", nodes: "x" } as never} />);
      expect(empty.container.textContent).toContain("Empty flowchart");
    }));
});
