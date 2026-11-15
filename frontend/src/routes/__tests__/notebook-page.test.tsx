// @vitest-environment jsdom
/**
 * The cahier (spec 018 D8): the chapter's stored boards, section by section in path order,
 * drawn by the board's own cards and read-only; the exchange behind a toggle; an anchor per
 * section; an empty state; the way back to the lesson.
 */
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { stubLayoutApis } from "@/test/jsdom-stubs";

beforeEach(() => stubLayoutApis({ desktop: true }));

vi.mock("@/components/celestin/math", () => ({
  Math: ({ tex }: { tex: string }) => <span>{tex}</span>,
}));

import type { Notebook } from "@/lib/tutor/types";
import { mockApi, mountRoutes } from "@/test/route-harness";
import { Route as NotebookFile } from "../_auth/courses/$courseId/chapters/$chapterId/notebook";

const CHAPTER = {
  id: "suites",
  title: "Les suites numériques",
  position: 1,
  course_id: "maths",
  course_name: "Mathématiques 5e",
  language: "fr",
  subject: "mathematics",
  sections: [
    { id: "s1", index: 1, kind: "teach", title: "Suites numériques", goal: "g1" },
    { id: "s2", index: 2, kind: "practise", title: "Calculer un terme", goal: "g2" },
    { id: "s3", index: 3, kind: "synthesis", title: "Synthèse", goal: "g3" },
  ],
  progress: { done: ["s1"], active: "s2" },
};

const NOTEBOOK: Notebook = {
  sections: [
    // In path order, as the server sends them.
    {
      section_id: "s1",
      items: [
        {
          kind: "card",
          card: { kind: "title", eyebrow: "Section 1", title: "TITRE S1", objective: "o" },
        },
        {
          kind: "card",
          card: {
            kind: "explanation",
            title: "Le terme général",
            blocks: [{ type: "text", text: "Une suite associe un nombre à chaque rang." }],
          },
        },
        {
          kind: "card",
          card: {
            kind: "worked_example",
            title: "Un exemple",
            statement: "Calcule les premiers termes.",
            steps: [{ tex: "u_1 = 3" }, { tex: "u_2 = 5" }, { tex: "u_3 = 7" }],
          },
        },
      ],
    },
    {
      section_id: "s2",
      items: [
        {
          kind: "card",
          card: { kind: "title", eyebrow: "Section 2", title: "TITRE S2", objective: "o" },
        },
        { kind: "tutor", text: "On calcule $u_3$." },
        {
          kind: "card",
          card: {
            kind: "check_question",
            question: "Que vaut $u_3$ ?",
            options: [
              { id: "a", text: "Sept" },
              { id: "b", text: "Neuf" },
            ],
            correct_option_id: "b",
            feedback: "Bien vu : on ajoute 2 à chaque pas.",
          },
        },
        { kind: "learner", text: "Neuf ?" },
      ],
    },
    // A section the chapter does not have: not shown.
    { section_id: "gone", items: [{ kind: "tutor", text: "Fantôme." }] },
  ],
};

const PATH = "/api/courses/maths/chapters/suites";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

function mountNotebook(
  notebook: Notebook = NOTEBOOK,
  initial = "/courses/maths/chapters/suites/notebook",
) {
  const calls = mockApi((method, path) => {
    if (method === "GET" && path.endsWith(`${PATH}/notebook`)) return { body: notebook };
    if (method === "GET" && path.endsWith(PATH)) return { body: CHAPTER };
    return undefined;
  });
  mountRoutes(
    [{ path: "/courses/$courseId/chapters/$chapterId/notebook", file: NotebookFile }],
    initial,
  );
  return calls;
}

const sections = () => Array.from(document.querySelectorAll("section[id]"));

describe("the cahier", () => {
  it("shows the sections in the server's (path) order, each with its number, kind and title", async () => {
    mountNotebook();
    await screen.findByRole("heading", { name: "Suites numériques" });
    expect(sections().map((s) => s.id)).toEqual(["s1", "s2"]);
    const first = sections()[0] as HTMLElement;
    expect(within(first).getByText("1")).toBeTruthy();
    expect(within(first).getByText("Leçon")).toBeTruthy();
    expect(within(sections()[1] as HTMLElement).getByText("Exercices")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Suites numériques" }).getAttribute("lang")).toBe(
      "fr",
    );
    expect(screen.queryByText("Fantôme.")).toBeNull();
    expect(screen.getByRole("heading", { name: "Les suites numériques" })).toBeTruthy();
  });

  it("draws the cards with the board's own components, title cards skipped", async () => {
    mountNotebook();
    await screen.findByText("Une suite associe un nombre à chaque rang.");
    expect(screen.queryByText("TITRE S1")).toBeNull();
    expect(screen.queryByText("TITRE S2")).toBeNull();
    expect(
      Array.from(document.querySelectorAll("[data-card]")).map((c) => c.getAttribute("data-card")),
    ).toEqual(["explanation", "worked_example", "check_question"]);
    // A worked example shows all its steps.
    for (const tex of ["u_1 = 3", "u_2 = 5", "u_3 = 7"]) expect(screen.getByText(tex)).toBeTruthy();
    // Read-only: no page-turn button, no history strip.
    expect(screen.queryByRole("button", { name: "Étape suivante" })).toBeNull();
    expect(screen.queryByText("Tableau")).toBeNull();
  });

  it("reveals a check question's answer and feedback only once an option is picked", async () => {
    const calls = mountNotebook();
    const wrong = await screen.findByRole("button", { name: /Sept/ });
    expect(screen.getByRole("button", { name: /Neuf/ })).toBeTruthy();
    expect(screen.queryByText(/Bien vu/)).toBeNull();
    const before = calls.length;
    fireEvent.click(wrong);
    expect(screen.getByText(/Bien vu/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /Neuf/ }).className).toContain("border-success");
    expect(wrong.className).toContain("border-destructive");
    // Nothing is sent anywhere: it is her own past lesson.
    expect(calls.length).toBe(before);
  });

  it("shows the exchange between the boards behind a toggle", async () => {
    mountNotebook();
    await screen.findByText("Une suite associe un nombre à chaque rang.");
    expect(screen.queryByText(/On calcule/)).toBeNull();
    expect(screen.queryByText("Neuf ?")).toBeNull();
    fireEvent.click(screen.getByRole("switch", { name: "Afficher les échanges" }));
    const tutor = await screen.findByText(/On calcule/);
    expect(tutor.closest("[lang]")?.getAttribute("lang")).toBe("fr");
    // Its maths goes through the board's KaTeX entry point, as in the lesson.
    expect(within(tutor.closest("p")!).getByText("u_3")).toBeTruthy();
    expect(screen.getByText("Neuf ?")).toBeTruthy();
    // In the order they were said: the tutor's line before the card, the answer after it.
    const s2 = sections()[1] as HTMLElement;
    const text = s2.textContent ?? "";
    expect(text.indexOf("On calcule")).toBeLessThan(text.indexOf("Que vaut"));
    expect(text.indexOf("Que vaut")).toBeLessThan(text.indexOf("Neuf ?"));
  });

  it("scrolls to the section the link named", async () => {
    const scrolled: string[] = [];
    Element.prototype.scrollIntoView = vi.fn(function (this: Element) {
      scrolled.push(this.id);
    });
    mountNotebook(NOTEBOOK, "/courses/maths/chapters/suites/notebook#s2");
    await screen.findByText(/Que vaut/);
    await waitFor(() => expect(scrolled).toContain("s2"));
  });

  it("says a section has nothing on the board when it only showed its title card", async () => {
    mountNotebook({
      sections: [
        {
          section_id: "s1",
          items: [
            {
              kind: "card",
              card: { kind: "title", eyebrow: "Section 1", title: "TITRE S1", objective: "o" },
            },
            { kind: "tutor", text: "On commence par le vocabulaire." },
          ],
        },
      ],
    });
    await screen.findByText("Rien au tableau dans cette section.");
    fireEvent.click(screen.getByRole("switch", { name: "Afficher les échanges" }));
    await screen.findByText("On commence par le vocabulaire.");
    expect(screen.queryByText("Rien au tableau dans cette section.")).toBeNull();
  });

  it("says so when nothing is stored yet", async () => {
    mountNotebook({ sections: [] });
    await screen.findByText(/Ton cahier est encore vide/);
    expect(screen.queryByRole("switch")).toBeNull();
  });

  it("leads back to the lesson", async () => {
    mountNotebook();
    const back = await screen.findByRole("link", { name: "← Retour à la séance" });
    expect(back.getAttribute("href")).toBe("/courses/maths/chapters/suites");
  });

  it("says when the cahier cannot be read", async () => {
    mockApi((method, path) => {
      if (method === "GET" && path.endsWith(`${PATH}/notebook`))
        return { status: 500, body: { code: "server_error", message: "Panne du serveur." } };
      if (method === "GET" && path.endsWith(PATH)) return { body: CHAPTER };
      return undefined;
    });
    mountRoutes(
      [{ path: "/courses/$courseId/chapters/$chapterId/notebook", file: NotebookFile }],
      "/courses/maths/chapters/suites/notebook",
    );
    await screen.findByText(/Panne du serveur\./);
    expect(screen.getByRole("button", { name: "Réessayer" })).toBeTruthy();
  });
});
