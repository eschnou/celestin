// @vitest-environment jsdom
/**
 * The Dutch sweep (spec 017 R7.6): every screen of the application, with the interface in Dutch
 * and the data a Dutch account really receives (the server writes Dutch too), must hold no French
 * or English outside a region that carries a `lang` of its own. Course text is marked; anything
 * else in another language is a string nobody translated.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LoginForm, RegisterForm, SetupForm } from "@/components/celestin/auth-forms";
import { foreignTextOutside } from "@/test/english-sweep";
import { withLocale } from "@/test/locale";
import { mockApi, mountRoutes, type Handler } from "@/test/route-harness";
import { Route as ChapterFile } from "../_auth/courses/$courseId/chapters/$chapterId/index";
import { Route as ContentFile } from "../_auth/courses/$courseId/chapters/$chapterId/content";
import { Route as CourseFile } from "../_auth/courses/$courseId/index";
import { Route as CoursesFile } from "../_auth/courses/index";
import { Route as SettingsFile } from "../_auth/settings";

vi.mock("@/components/celestin/math", () => ({
  Math: ({ tex }: { tex: string }) => <span>{tex}</span>,
}));

const LIMITS = {
  chapter_text_min_chars: 10,
  chapter_text_max_chars: 500,
  pack_max_chars: 60000,
  document_max_bytes: 26214400,
  document_max_pages: 50,
  document_min_pixels: 800,
  document_types: ["application/pdf", "image/jpeg", "image/png", "image/webp"],
};
const SUBJECTS = {
  subjects: [{ id: "sciences", label: "Wetenschappen", languages: ["fr"] }],
  limits: LIMITS,
};

const summary = {
  id: "c1",
  name: "Fysica 4e jaar",
  subject: "sciences",
  subject_label: "Wetenschappen",
  language: "nl",
  chapters_total: 3,
  chapters_done: 1,
  last_chapter: { id: "h1", title: "Eenparige beweging" },
  generating: 1,
};

const row = (over: Record<string, unknown> = {}) => ({
  id: "h1",
  position: 1,
  title: "Eenparige beweging",
  ready: true,
  section_count: 9,
  done_count: 2,
  state: "in_progress",
  last: true,
  authoring_state: "idle",
  authoring_message: null,
  authoring_stage: null,
  pages_done: 0,
  page_count: 0,
  authoring_received_chars: 0,
  authoring_quiet_s: null,
  ...over,
});

const DETAIL = {
  ...summary,
  chapters: [
    row(),
    row({
      id: "h2",
      position: 2,
      title: null,
      ready: false,
      state: "not_started",
      last: false,
      section_count: 0,
      authoring_state: "generating",
      authoring_stage: "pack",
      authoring_received_chars: 12400,
      authoring_quiet_s: 50,
    }),
    row({
      id: "h3",
      position: 3,
      title: null,
      ready: false,
      state: "not_started",
      last: false,
      section_count: 0,
      authoring_state: "failed",
      authoring_stage: "transcription",
      authoring_message: "Het lezen van de pagina's duurde te lang. Bezorg het document opnieuw.",
    }),
  ],
};

// The pack and the path are the course's: Dutch here, and marked `lang="nl"` where they show.
const CONTENT = {
  id: "h1",
  course_id: "c1",
  subject: "sciences",
  position: 1,
  version: 2,
  ready: true,
  title: "De eenparige rechtlijnige beweging",
  pack: "# De ERB\n\n## 1. Doel van het hoofdstuk\n\nEen ERB beschrijven.\n",
  curriculum: {
    title: "De eenparige rechtlijnige beweging",
    sections: [
      {
        id: "snelheid",
        index: 1,
        kind: "teach",
        title: "De gemiddelde snelheid",
        goal: "De snelheid definiëren.",
        done_when: "Klaar",
        pack: ["§4.1"],
        beats: ["De definitie aanhalen."],
        exercises: [],
        count: null,
      },
      {
        id: "berekeningen",
        index: 2,
        kind: "practise",
        title: "Berekeningen",
        goal: "v berekenen.",
        done_when: "Klaar",
        pack: [],
        beats: [],
        exercises: ["6.1.1", "6.1.2"],
        count: 2,
      },
    ],
  },
  source_text: "--- page 1 ---\n\nDe tekst uit het document.\n",
  source_kind: "document",
  language: "nl",
  page_count: 2,
  authoring_received_chars: 0,
  authoring_quiet_s: null,
  authoring_state: "idle",
  authoring_message: null,
  has_progress: true,
};

const api =
  (extra?: Handler): Handler =>
  (method, path, body) => {
    const custom = extra?.(method, path, body);
    if (custom) return custom;
    if (path.endsWith("/api/subjects")) return { body: SUBJECTS };
    if (method === "GET" && path.endsWith("/api/courses/c1")) return { body: DETAIL };
    if (method === "GET" && path.endsWith("/api/courses")) return { body: { courses: [summary] } };
    if (method === "GET" && path.endsWith("/chapters/h1/content")) return { body: CONTENT };
    return undefined;
  };

const ROUTES = [
  { path: "/courses/", file: CoursesFile },
  { path: "/courses/$courseId/", file: CourseFile },
  { path: "/courses/$courseId/chapters/$chapterId/", file: ChapterFile },
  { path: "/courses/$courseId/chapters/$chapterId/content", file: ContentFile },
  { path: "/settings", file: SettingsFile },
];

/** Open `initial` as a Dutch account. */
const open = (initial: string, handler?: Handler) => {
  mockApi(api(handler), { locale: "nl", name: "Lea" });
  return mountRoutes(ROUTES, initial);
};

const clean = () => expect(foreignTextOutside("nl")).toEqual([]);

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("the Dutch sweep: signed out", () => {
  it("sign-in and registration, with their validation messages", () =>
    withLocale("nl", () => {
      render(<LoginForm onSuccess={() => undefined} />);
      fireEvent.click(screen.getByRole("button", { name: "Aanmelden" }));
      return screen.findByText("Vul je e-mailadres in.").then(() => {
        clean();
        cleanup();
        render(<RegisterForm onSuccess={() => undefined} />);
        fireEvent.click(screen.getByRole("button", { name: "Mijn account aanmaken" }));
        return screen.findByText("Vul je voornaam in.").then(() => {
          clean();
          cleanup();
          render(<SetupForm onSuccess={() => undefined} />);
          fireEvent.click(screen.getByRole("button", { name: "De beheerder aanmaken" }));
          return screen.findByText("Vul je voornaam in.").then(clean);
        });
      });
    }));
});

describe("the Dutch sweep: courses", () => {
  it("« Mijn cursussen », empty, with the create form and its errors", () =>
    withLocale("nl", async () => {
      open("/courses", (method, path) =>
        method === "GET" && path.endsWith("/api/courses") ? { body: { courses: [] } } : undefined,
      );
      await screen.findByText(/Je hebt nog geen cursussen/);
      clean();
      fireEvent.click(screen.getByRole("button", { name: "Nieuwe cursus" }));
      fireEvent.click(await screen.findByRole("button", { name: "De cursus aanmaken" }));
      await screen.findByText("Geef je cursus een naam.");
      clean();
    }));

  it("« Mijn cursussen », with a course card", () =>
    withLocale("nl", async () => {
      open("/courses");
      await screen.findByRole("article", { name: "Fysica 4e jaar" });
      clean();
    }));

  it("a course: ready, preparing and failed chapters, rename and the document picker", () =>
    withLocale("nl", async () => {
      open("/courses/c1");
      await screen.findByRole("heading", { name: "Fysica 4e jaar" });
      clean();
      fireEvent.keyDown(screen.getByRole("button", { name: "Acties voor de cursus" }), {
        key: "Enter",
      });
      await screen.findByRole("menuitem", { name: "Hernoemen" });
      clean();
      fireEvent.click(screen.getByRole("menuitem", { name: "Hernoemen" }));
      fireEvent.change(screen.getByLabelText("Naam van de cursus"), { target: { value: "" } });
      fireEvent.click(screen.getByRole("button", { name: "Opslaan" }));
      await screen.findByText("De naam moet tussen 1 en 80 tekens lang zijn.");
      clean();
      fireEvent.click(screen.getByRole("button", { name: "Annuleren" }));
      fireEvent.click(screen.getByRole("button", { name: "Een hoofdstuk toevoegen" }));
      await screen.findByLabelText("De pdf of de foto's van de cursus");
      clean();
    }));

  it("a chapter in preparation, and a chapter that is not found", () =>
    withLocale("nl", async () => {
      open("/courses/c1/chapters/h2", (method, path) =>
        path.includes("/chapters/h2") && method === "GET"
          ? {
              status: 409,
              body: { code: "chapter_not_ready", message: "Dit hoofdstuk is nog niet klaar." },
            }
          : undefined,
      );
      await screen.findByText("Dit hoofdstuk wordt voorbereid");
      await screen.findByText(/Nog bezig, de dienst is traag\./);
      clean();
      cleanup();
      open("/courses/c1/chapters/zz", (method, path) =>
        path.includes("/chapters/zz") && method === "GET"
          ? { status: 404, body: { code: "not_found", message: "Deze pagina bestaat niet." } }
          : undefined,
      );
      await screen.findByText("Deze cursus of dit hoofdstuk bestaat niet, of is niet van jou.");
      clean();
    }));
});

describe("the Dutch sweep: the content page", () => {
  const tab = async (name: string) => {
    const el = await screen.findByRole("tab", { name });
    fireEvent.mouseDown(el);
    fireEvent.click(el);
  };

  it("the pack, the path and the text, read-only and in their editors", () =>
    withLocale("nl", async () => {
      open("/courses/c1/chapters/h1/content");
      await screen.findByRole("tab", { name: "Inhoud" });
      clean();
      fireEvent.click(screen.getByRole("button", { name: "De inhoud bewerken" }));
      clean();
      fireEvent.click(screen.getByRole("button", { name: "De inhoud opslaan" }));
      await screen.findByRole("alertdialog");
      clean();
      cleanup();

      open("/courses/c1/chapters/h1/content");
      await tab("Traject");
      await screen.findByText("1 · Les");
      clean();
      fireEvent.click(screen.getByRole("button", { name: "Het traject bewerken" }));
      await screen.findByLabelText("Titel van het traject");
      clean();
      cleanup();

      open("/courses/c1/chapters/h1/content");
      await tab("Tekst uit het document gehaald");
      await screen.findByRole("button", { name: "De tekst bewerken" });
      clean();
      fireEvent.click(screen.getByRole("button", { name: "De tekst bewerken" }));
      await screen.findByText(/Verbeter wat Célestin verkeerd las/);
      clean();
    }));

  it("a Dutch account's refused edit lists Dutch reasons", () =>
    withLocale("nl", async () => {
      open("/courses/c1/chapters/h1/content", (method) =>
        method === "PUT"
          ? {
              status: 422,
              body: {
                code: "content_invalid",
                message: "De inhoud is niet geldig. Verbeter de aangeduide punten.",
                issues: [
                  {
                    where: "§ 5",
                    message: "sectie “## 5. Woordenschat” ontbreekt of heeft een verkeerde titel",
                  },
                ],
              },
            }
          : undefined,
      );
      fireEvent.click(await screen.findByRole("button", { name: "De inhoud bewerken" }));
      fireEvent.click(screen.getByRole("button", { name: "De inhoud opslaan" }));
      const dialog = await screen.findByRole("alertdialog");
      fireEvent.click(within(dialog).getByRole("button", { name: "Opslaan" }));
      await screen.findByRole("alert");
      clean();
    }));
});

describe("the Dutch sweep: settings and the user menu", () => {
  it("the settings screen lists the three languages and is clean", () =>
    withLocale("nl", async () => {
      open("/settings");
      await screen.findByRole("heading", { name: "Instellingen" });
      expect(screen.getByRole("radio", { name: "Nederlands" })).toBeTruthy();
      expect(screen.getByRole("radio", { name: "Français" })).toBeTruthy();
      clean();
    }));

  it("the open user menu", () =>
    withLocale("nl", async () => {
      open("/courses");
      await screen.findByRole("button", { name: "Lea" });
      fireEvent.keyDown(screen.getByRole("button", { name: "Lea" }), { key: "Enter" });
      await screen.findByRole("menuitem", { name: "Instellingen" });
      clean();
    }));
});

import { within } from "@testing-library/react";
