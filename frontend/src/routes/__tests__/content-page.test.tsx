// @vitest-environment jsdom
/** « Contenu du chapitre »: read views and the three editors (005 R5). */
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi, mountRoutes, type Reply } from "@/test/route-harness";
import { toCurriculum } from "@/components/celestin/content/curriculum-editor";
import { Route as ContentFile } from "../_auth/courses/$courseId/chapters/$chapterId/content";
import { Route as CourseFile } from "../_auth/courses/$courseId/index";

vi.mock("@/components/celestin/math", () => ({
  Math: ({ tex }: { tex: string }) => <span>{tex}</span>,
}));

const PACK = "# Le MRU\n\n## 1. Objectif du chapitre\n\nDécrire un MRU avec $v = d/t$.\n";

const CONTENT = {
  id: "h1",
  course_id: "c1",
  subject: "sciences",
  position: 1,
  version: 2,
  ready: true,
  title: "Le MRU",
  pack: PACK,
  curriculum: {
    title: "Le MRU",
    sections: [
      {
        id: "vitesse",
        index: 1,
        kind: "teach",
        title: "La vitesse",
        goal: "Définir v.",
        done_when: "Question répondue.",
        pack: ["§4.1"],
        beats: ["Citer la définition.", "Question de contrôle."],
        exercises: [],
        count: null,
      },
      {
        id: "calculs",
        index: 2,
        kind: "practise",
        title: "Calculs",
        goal: "Calculer v.",
        done_when: "Deux exercices.",
        pack: [],
        beats: [],
        exercises: ["6.1.1", "6.1.2"],
        count: 2,
      },
    ],
  },
  source_text: "--- page 1 ---\n\nLe texte lu dans le document.\n",
  source_kind: "document",
  language: "fr",
  page_count: 2,
  authoring_state: "idle",
  authoring_message: null,
  has_progress: true,
};

const SUBJECTS = {
  subjects: [{ id: "sciences", label: "Physique", languages: ["fr"] }],
  limits: {
    chapter_text_min_chars: 10,
    chapter_text_max_chars: 500,
    pack_max_chars: 60000,
    document_max_bytes: 26214400,
    document_max_pages: 50,
    document_min_pixels: 800,
    document_types: ["application/pdf", "image/jpeg", "image/png", "image/webp"],
  },
};

const SOURCE_TAB = "Texte extrait du document";

function mount(
  extra?: (method: string, path: string, body: unknown) => Reply | undefined,
  content: unknown = CONTENT,
  initial = "/courses/c1/chapters/h1/content",
) {
  const calls = mockApi((method, path, body) => {
    const custom = extra?.(method, path, body);
    if (custom) return custom;
    if (path.endsWith("/api/subjects")) return { body: SUBJECTS };
    if (method === "GET" && path.endsWith("/chapters/h1/content")) return { body: content };
    if (method === "GET" && path.endsWith("/api/courses/c1"))
      return {
        body: {
          id: "c1",
          name: "Physique",
          subject: "sciences",
          subject_label: "Physique",
          language: "fr",
          chapters_total: 1,
          chapters_done: 0,
          last_chapter: null,
          generating: 1,
          chapters: [],
        },
      };
    return undefined;
  });
  const { router } = mountRoutes(
    [
      { path: "/courses/$courseId/", file: CourseFile },
      { path: "/courses/$courseId/chapters/$chapterId/content", file: ContentFile },
    ],
    initial,
  );
  return { calls, router };
}

async function openTab(name: RegExp | string) {
  const tab = await screen.findByRole("tab", { name });
  fireEvent.mouseDown(tab);
  fireEvent.click(tab);
  return tab;
}

async function confirm() {
  const dialog = await screen.findByRole("alertdialog");
  expect(dialog.textContent).toContain("progression");
  fireEvent.click(within(dialog).getByRole("button", { name: "Enregistrer" }));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("reading", () => {
  it("shows the pack, the path and the text read from the document", async () => {
    mount();
    expect(
      await screen.findByRole("heading", { level: 1, name: "Chapitre 1 — Le MRU" }),
    ).toBeTruthy();
    expect(screen.getByText(/Décrire un MRU avec/)).toBeTruthy();
    await openTab("Parcours");
    expect(await screen.findByText("La vitesse")).toBeTruthy();
    expect(screen.getByText("2 · Exercices")).toBeTruthy();
    expect(screen.getByText(/6\.1\.1 ; 6\.1\.2/)).toBeTruthy();
    expect(screen.getByText("Terminée quand : Deux exercices.")).toBeTruthy();
    await openTab(SOURCE_TAB);
    expect(await screen.findByText(/Le texte lu dans le document\./)).toBeTruthy();
    expect(screen.getByText(/2 pages\)\. Le fichier n'est pas conservé\./)).toBeTruthy();
  });

  it("opens on the text when asked to drop the document again", async () => {
    mount(undefined, CONTENT, "/courses/c1/chapters/h1/content?tab=source");
    const tab = await screen.findByRole("tab", { name: SOURCE_TAB });
    expect(tab.getAttribute("aria-selected")).toBe("true");
  });

  it("locks the editors while a new version is being prepared", async () => {
    mount(undefined, { ...CONTENT, authoring_state: "generating" });
    const edit = (await screen.findByRole("button", {
      name: "Modifier le contenu",
    })) as HTMLButtonElement;
    expect(edit.disabled).toBe(true);
    expect(screen.getByText("Modifiable une fois la préparation terminée.")).toBeTruthy();
  });

  it("says a chapter is still in preparation", async () => {
    mount(undefined, {
      ...CONTENT,
      ready: false,
      pack: null,
      curriculum: null,
      title: null,
      authoring_state: "generating",
      version: 0,
      has_progress: false,
    });
    expect(await screen.findByText(/Ce chapitre est en préparation/)).toBeTruthy();
    expect(screen.getByRole("tab", { name: SOURCE_TAB }).getAttribute("aria-selected")).toBe(
      "true",
    );
  });

  it("offers only a new document when no page was read", async () => {
    mount(undefined, {
      ...CONTENT,
      ready: false,
      pack: null,
      curriculum: null,
      title: null,
      source_text: "",
      authoring_state: "failed",
      authoring_message: "Je n'ai pas pu lire certaines pages.",
      version: 0,
      has_progress: false,
    });
    expect(await screen.findByText("Les pages n'ont pas encore été lues.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Modifier le texte" })).toBeNull();
    expect(screen.getByRole("button", { name: "Remplacer par un document" })).toBeTruthy();
  });
});

describe("the pack editor", () => {
  it("saves after confirming the progress reset", async () => {
    const { calls } = mount((method, path) =>
      method === "PUT" && path.endsWith("/pack")
        ? { body: { ...CONTENT, version: 3, has_progress: false } }
        : undefined,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Modifier le contenu" }));
    fireEvent.change(screen.getByLabelText("Contenu du chapitre"), {
      target: { value: PACK + "\nAjout." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer le contenu" }));
    await confirm();
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PUT")?.body).toEqual({
        version: 2,
        pack: PACK + "\nAjout.",
      }),
    );
    expect(await screen.findByRole("button", { name: "Modifier le contenu" })).toBeTruthy();
  });

  it("lists the validator's issues and stays open", async () => {
    mount((method) =>
      method === "PUT"
        ? {
            status: 422,
            body: {
              code: "content_invalid",
              message: "Le contenu n'est pas valide.",
              issues: [{ where: "§ 5", message: "section « ## 5. Vocabulaire » manquante" }],
            },
          }
        : undefined,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Modifier le contenu" }));
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer le contenu" }));
    await confirm();
    expect((await screen.findByRole("alert")).textContent).toContain(
      "§ 5 : section « ## 5. Vocabulaire » manquante",
    );
    expect(screen.getByLabelText("Contenu du chapitre")).toBeTruthy();
  });

  it("offers to reload when the chapter changed meanwhile", async () => {
    const { calls } = mount((method) =>
      method === "PUT"
        ? {
            status: 409,
            body: { code: "stale_version", message: "Le chapitre a changé entre-temps." },
          }
        : undefined,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Modifier le contenu" }));
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer le contenu" }));
    await confirm();
    fireEvent.click(await screen.findByRole("button", { name: "Recharger" }));
    await waitFor(() =>
      expect(calls.filter((c) => c.path.endsWith("/content")).length).toBeGreaterThan(1),
    );
  });

  it("previews the Markdown", async () => {
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "Modifier le contenu" }));
    fireEvent.click(screen.getByRole("tab", { name: "Aperçu" }));
    expect(screen.getAllByText(/Décrire un MRU avec/).length).toBeGreaterThan(0);
  });
});

describe("the path editor", () => {
  async function openEditor(extra?: Parameters<typeof mount>[0]) {
    const mounted = mount(extra);
    await openTab("Parcours");
    fireEvent.click(await screen.findByRole("button", { name: "Modifier le parcours" }));
    return mounted;
  }

  it("adds, moves, removes and switches kinds, then sends a clean path", async () => {
    const { calls } = await openEditor((method) =>
      method === "PUT" ? { body: CONTENT } : undefined,
    );
    fireEvent.click(screen.getByRole("button", { name: "Descendre la section 1" }));
    expect(
      (screen.getByLabelText("Titre", { selector: "#section-0-title" }) as HTMLInputElement).value,
    ).toBe("Calculs");
    fireEvent.change(screen.getByLabelText("Sorte de section 1"), { target: { value: "teach" } });
    fireEvent.change(
      await screen.findByLabelText("Étapes (une par ligne)", { selector: "#section-0-beats" }),
      {
        target: { value: "Rappeler la formule.\n\nFaire calculer." },
      },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ajouter une section" }));
    fireEvent.click(screen.getByRole("button", { name: "Retirer la section 3" }));
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer le parcours" }));
    await confirm();
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    const sent = calls.find((c) => c.method === "PUT")!.body as {
      version: number;
      curriculum: ReturnType<typeof toCurriculum>;
    };
    expect(sent.version).toBe(2);
    expect(sent.curriculum.sections.map((s) => [s.id, s.kind])).toEqual([
      ["calculs", "teach"],
      ["vitesse", "teach"],
    ]);
    expect(sent.curriculum.sections[0]).toMatchObject({
      beats: ["Rappeler la formule.", "Faire calculer."],
      exercises: [],
      count: null,
    });
  });

  it("checks required fields before sending", async () => {
    const { calls } = await openEditor();
    fireEvent.change(screen.getByLabelText("Titre", { selector: "#section-0-title" }), {
      target: { value: "  " },
    });
    fireEvent.change(
      screen.getByLabelText("Étapes (une par ligne)", { selector: "#section-0-beats" }),
      { target: { value: "" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer le parcours" }));
    await confirm();
    expect(await screen.findByText("Le titre est obligatoire.")).toBeTruthy();
    expect(screen.getByText("Une leçon a au moins une étape.")).toBeTruthy();
    expect(calls.some((c) => c.method === "PUT")).toBe(false);
  });

  it("shows a server issue under the section it names", async () => {
    await openEditor((method) =>
      method === "PUT"
        ? {
            status: 422,
            body: {
              code: "content_invalid",
              message: "x",
              issues: [
                {
                  where: "section « calculs »",
                  message: "l'exercice 6.9.9 n'existe pas dans le contenu",
                },
              ],
            },
          }
        : undefined,
    );
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer le parcours" }));
    await confirm();
    const issue = await screen.findByText(/l'exercice 6\.9\.9 n'existe pas/);
    const item = issue.closest("li[class*='rounded-xl']") as HTMLElement;
    expect((within(item).getByLabelText("Titre") as HTMLInputElement).value).toBe("Calculs");
  });
});

describe("the text editor", () => {
  it("starts a new preparation after confirmation and goes back to the course", async () => {
    const { calls, router } = mount((method, path) =>
      method === "PUT" && path.endsWith("/source") ? { status: 202, body: {} } : undefined,
    );
    await openTab(SOURCE_TAB);
    fireEvent.click(await screen.findByRole("button", { name: "Modifier le texte" }));
    fireEvent.change(screen.getByRole("textbox", { name: SOURCE_TAB }), {
      target: { value: "Un nouveau texte de cours." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Préparer à nouveau" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain("Le contenu actuel reste utilisable en attendant");
    fireEvent.click(within(dialog).getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/courses/c1"));
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({
      source_text: "Un nouveau texte de cours.",
    });
  });

  it("refuses text outside the limits", async () => {
    mount();
    await openTab(SOURCE_TAB);
    fireEvent.click(await screen.findByRole("button", { name: "Modifier le texte" }));
    fireEvent.change(screen.getByRole("textbox", { name: SOURCE_TAB }), {
      target: { value: "court" },
    });
    expect(
      (screen.getByRole("button", { name: "Préparer à nouveau" }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });
});

describe("replacing the document", () => {
  it("sends the new pages after confirmation and goes back to the course", async () => {
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:page");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    const { calls, router } = mount((method, path) =>
      method === "PUT" && path.endsWith("/document") ? { status: 202, body: {} } : undefined,
    );
    await openTab(SOURCE_TAB);
    fireEvent.click(await screen.findByRole("button", { name: "Remplacer par un document" }));
    const pdf = new File(["%PDF-"], "chapitre.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText("Le PDF ou les photos du cours"), {
      target: { files: [pdf] },
    });
    expect(screen.getByText("chapitre.pdf")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Préparer à nouveau" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain("Célestin va lire ce document");
    fireEvent.click(within(dialog).getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/courses/c1"));
    const form = calls.find((c) => c.method === "PUT")?.body as FormData;
    expect(form.getAll("files")).toEqual([pdf]);
    vi.restoreAllMocks();
  });
});
