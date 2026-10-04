// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CardView, Whiteboard } from "../whiteboard";
import { CHARTS } from "../charts/__tests__/fixtures";
import { NUMBER_LINE, PLANE, SETS } from "../figure/__tests__/fixtures";
import { HIDDEN, METHOD, SECRET } from "../flowchart/__tests__/fixtures";
import { PLOTS } from "../plot/__tests__/fixtures";
import type {
  BoardCard,
  CheckQuestionCard,
  ChartBlock,
  Drawing,
  ExerciseCard,
  ExplanationCard,
  PlotBlock,
  WorkedExampleCard,
} from "@/lib/tutor/types";

const CARD: CheckQuestionCard = {
  kind: "check_question",
  question: "Pourquoi $q \\neq 1$ ?",
  options: [
    { id: "a", text: "Division par zéro" },
    { id: "b", text: "Par habitude" },
  ],
  correct_option_id: "a",
  feedback: "Exactement.",
};

afterEach(cleanup);

describe("check-question card", () => {
  it("reports the picked option and its correctness, and keeps its local feedback", () => {
    const onAnswer = vi.fn();
    render(<CardView card={CARD} onAnswer={onAnswer} />);
    fireEvent.click(screen.getByText("Par habitude"));
    expect(onAnswer).toHaveBeenLastCalledWith({ id: "b", text: "Par habitude" }, false);
    expect(screen.queryByText("Exactement.")).toBeNull();

    fireEvent.click(screen.getByText("Division par zéro"));
    expect(onAnswer).toHaveBeenLastCalledWith({ id: "a", text: "Division par zéro" }, true);
    expect(screen.getByText("Exactement.")).toBeTruthy();
  });

  it("works without a handler", () => {
    render(<CardView card={CARD} />);
    expect(() => fireEvent.click(screen.getByText("Par habitude"))).not.toThrow();
  });
});

describe("definition block", () => {
  const DEFINITIONS: ExplanationCard = {
    kind: "explanation",
    title: "Population, échantillon et individu",
    blocks: [
      {
        type: "definition",
        entries: [
          { term: "population", text: "Une population est un ensemble d'individus." },
          { term: "individu", text: "Un individu est un élément de la population." },
        ],
      },
    ],
  };

  it("lists each term and sets it in bold inside its definition", () => {
    const { container } = render(<CardView card={DEFINITIONS} />);
    expect(screen.getByText("Définitions")).toBeTruthy();
    expect([...container.querySelectorAll("dt")].map((dt) => dt.textContent)).toEqual([
      "population",
      "individu",
    ]);
    expect([...container.querySelectorAll("dd strong")].map((b) => b.textContent)).toEqual([
      "population",
      "individu",
    ]);
  });
});

describe("charts on cards", () => {
  const CHART: ChartBlock = { type: "chart", chart: CHARTS.sticks };
  const cards: BoardCard[] = [
    { kind: "explanation", title: "Les notes", blocks: [{ type: "text", text: "Voici :" }, CHART] },
    {
      kind: "worked_example",
      title: "Le mode",
      statement: "Lis le graphique.",
      drawing: CHART,
      steps: [{ tex: "Mo = 14" }],
    },
    { kind: "exercise", title: "Lecture", statement: "Quel est le mode ?", drawing: CHART },
  ];

  it.each(cards.map((c) => [c.kind, c] as const))("draws a chart in a %s card", (_, card) => {
    const { getByRole } = render(<CardView card={card} />);
    expect(getByRole("img").getAttribute("aria-label")).toContain("Diagramme en bâtons");
  });
});

describe("drawings on cards", () => {
  const PARABOLA: PlotBlock = {
    ...PLOTS.parabola,
    // As an exercise may carry it: no point's values written.
    points: PLOTS.parabola.points.map((p) => ({ ...p, show_values: false })),
  };
  const drawings: [string, Drawing, string | RegExp][] = [
    ["flowchart", METHOD, `Organigramme en ${METHOD.nodes.length} étapes`],
    ["plane figure", { type: "figure", figure: PLANE }, "Figure géométrique"],
    ["number line", { type: "figure", figure: NUMBER_LINE }, "Droite graduée"],
    ["set diagram", { type: "figure", figure: SETS }, "Diagramme d'ensembles"],
    ["plot", PARABOLA, /^Graphique : y en fonction de x$/],
  ];

  const STATEMENT = "Observe le tableau.";
  const STEP_NOTE = "première étape";
  const HINT = "Commence par le haut.";

  /** `a` comes before `b` in the document. */
  const before = (a: Node, b: Node) =>
    Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);

  function drawn(label: string | RegExp): HTMLElement {
    const img = screen.getByRole("img");
    const name = img.getAttribute("aria-label") ?? "";
    if (typeof label === "string") expect(name).toBe(label);
    else expect(name).toMatch(label);
    expect(img.querySelector("svg")).not.toBeNull();
    return img;
  }

  it.each(drawings)("draws a %s in an explanation", (_, block, label) => {
    const card: ExplanationCard = {
      kind: "explanation",
      title: "Au tableau",
      blocks: [{ type: "text", text: STATEMENT }, block],
    };
    render(<CardView card={card} />);
    expect(before(screen.getByText(STATEMENT), drawn(label))).toBe(true);
  });

  it.each(drawings)(
    "draws a %s as a worked example's drawing, between statement and steps",
    (_, block, label) => {
      const card: WorkedExampleCard = {
        kind: "worked_example",
        title: "Exemple",
        statement: STATEMENT,
        drawing: block,
        steps: [{ tex: "x = 1", note: STEP_NOTE }],
      };
      render(<CardView card={card} />);
      const img = drawn(label);
      expect(before(screen.getByText(STATEMENT), img)).toBe(true);
      expect(before(img, screen.getByText(STEP_NOTE))).toBe(true);
    },
  );

  it.each(drawings)(
    "draws a %s as an exercise's drawing, between statement and hint",
    (_, block, label) => {
      const card: ExerciseCard = {
        kind: "exercise",
        title: "Exercice",
        statement: STATEMENT,
        drawing: block,
        hint: HINT,
      };
      render(<CardView card={card} />);
      const img = drawn(label);
      expect(before(screen.getByText(STATEMENT), img)).toBe(true);
      expect(before(img, screen.getByText(HINT))).toBe(true);
    },
  );

  it("keeps an exercise's hidden flowchart box out of the page", () => {
    const card: ExerciseCard = {
      kind: "exercise",
      title: "À compléter",
      statement: "Complète l'organigramme.",
      drawing: HIDDEN,
    };
    const { container } = render(<CardView card={card} />);
    drawn(`Organigramme en ${HIDDEN.nodes.length} étapes`);
    expect(container.innerHTML).not.toContain(SECRET);
  });
});

describe("next-step button", () => {
  it("is greyed until the tutor proposes the step, then sends on click", () => {
    const onNextStep = vi.fn();
    const { rerender } = render(
      <Whiteboard
        card={CARD}
        cards={[CARD]}
        onSelect={() => {}}
        nextStep={null}
        onNextStep={onNextStep}
      />,
    );
    const button = screen.getByRole("button", { name: "Étape suivante" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.click(button);
    expect(onNextStep).not.toHaveBeenCalled();

    rerender(
      <Whiteboard
        card={CARD}
        cards={[CARD]}
        onSelect={() => {}}
        nextStep={{ kind: "step" }}
        onNextStep={onNextStep}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Étape suivante" }));
    expect(onNextStep).toHaveBeenCalledOnce();
  });

  it("reads « Section suivante » once a section has closed", () => {
    render(
      <Whiteboard
        card={CARD}
        cards={[CARD]}
        onSelect={() => {}}
        nextStep={{ kind: "section", sectionId: "sa" }}
        onNextStep={() => {}}
      />,
    );
    const button = screen.getByRole("button", { name: "Section suivante" }) as HTMLButtonElement;
    expect(button.disabled).toBe(false);
    expect(screen.queryByRole("button", { name: "Étape suivante" })).toBeNull();
  });

  it("is absent on an empty board", () => {
    render(
      <Whiteboard
        card={null}
        cards={[]}
        onSelect={() => {}}
        nextStep={{ kind: "step" }}
        onNextStep={() => {}}
      />,
    );
    expect(screen.queryByRole("button", { name: "Étape suivante" })).toBeNull();
  });
});
