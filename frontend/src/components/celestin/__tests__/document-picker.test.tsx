// @vitest-environment jsdom
/** Choosing a chapter's pages (006 R1): what is accepted, order, limits, object URLs. */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/tutor/client";
import { withLocale } from "@/test/locale";
import type { Limits } from "@/lib/tutor/types";
import { DocumentPicker, selectionProblem } from "../document-picker";

const LIMITS: Limits = {
  chapter_text_min_chars: 300,
  chapter_text_max_chars: 100000,
  pack_max_chars: 60000,
  document_max_bytes: 1000,
  document_max_pages: 3,
  document_min_pixels: 800,
  document_types: ["application/pdf", "image/jpeg", "image/png", "image/webp"],
};

const file = (name: string, type: string, size = 10) =>
  new File(["x".repeat(size)], name, { type });
const jpeg = (name: string, size = 10) => file(name, "image/jpeg", size);
const pdf = (name = "cours.pdf", size = 10) => file(name, "application/pdf", size);

let created: string[];
let revoked: string[];

beforeEach(() => {
  created = [];
  revoked = [];
  vi.spyOn(URL, "createObjectURL").mockImplementation(() => {
    created.push(`blob:${created.length + 1}`);
    return `blob:${created.length}`;
  });
  vi.spyOn(URL, "revokeObjectURL").mockImplementation((url) => void revoked.push(url));
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function mount(onSubmit = vi.fn(async () => undefined)) {
  const view = render(
    <DocumentPicker
      id="doc"
      limits={LIMITS}
      submitLabel="Préparer le chapitre"
      confirm={null}
      onSubmit={onSubmit}
      onCancel={() => undefined}
    />,
  );
  const input = screen.getByLabelText("Le PDF ou les photos du cours") as HTMLInputElement;
  const submit = screen.getByRole("button", { name: "Préparer le chapitre" }) as HTMLButtonElement;
  const choose = (...files: File[]) => fireEvent.change(input, { target: { files } });
  return { ...view, input, submit, choose, onSubmit };
}

const pages = () => screen.queryAllByRole("img").map((img) => img.getAttribute("src"));

describe("DocumentPicker", () => {
  it("accepts PDF and photos only, several at once", () => {
    const { input, choose } = mount();
    expect(input.accept).toBe("application/pdf,image/jpeg,image/png,image/webp");
    expect(input.multiple).toBe(true);
    choose(file("photo.heic", "image/heic"));
    expect(screen.getByRole("alert").textContent).toContain("« photo.heic » n'est ni un PDF");
    choose(pdf("a.pdf"), jpeg("b.jpg"));
    expect(screen.getByRole("alert").textContent).toBe(
      "Choisis un seul PDF, ou seulement des photos.",
    );
  });

  it("adds photos in order, moves and removes them, and frees their previews", () => {
    const { choose } = mount();
    choose(jpeg("1.jpg"), jpeg("2.jpg"));
    choose(jpeg("3.jpg"));
    expect(pages()).toEqual(["blob:1", "blob:2", "blob:3"]);
    fireEvent.click(screen.getByRole("button", { name: "Descendre la page 1" }));
    expect(pages()).toEqual(["blob:2", "blob:1", "blob:3"]);
    fireEvent.click(screen.getByRole("button", { name: "Retirer la page 3" }));
    expect(pages()).toEqual(["blob:2", "blob:1"]);
    expect(revoked).toEqual(["blob:3"]);
  });

  it("replaces photos by a PDF, which shows its name and size", () => {
    const { choose } = mount();
    choose(jpeg("1.jpg"), jpeg("2.jpg"));
    choose(pdf("cours.pdf"));
    expect(pages()).toEqual([]);
    expect(revoked).toEqual(["blob:1", "blob:2"]);
    expect(screen.getByText("cours.pdf")).toBeTruthy();
    expect(screen.getByText("Le nombre de pages sera vérifié à l'envoi.")).toBeTruthy();
  });

  it("keeps the submit off outside the limits", () => {
    const { choose, submit } = mount();
    expect(submit.disabled).toBe(true);
    choose(jpeg("1.jpg"), jpeg("2.jpg"), jpeg("3.jpg"), jpeg("4.jpg"));
    expect(screen.getByText("3 pages au plus par chapitre. Découpe le document.")).toBeTruthy();
    expect(submit.disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Retirer la page 4" }));
    expect(submit.disabled).toBe(false);
    choose(pdf("gros.pdf", 2000));
    expect(submit.disabled).toBe(true);
    expect(selectionProblem([pdf("gros.pdf", 2000)], LIMITS)).toMatch(/^Le document dépasse/);
  });

  it("frees every preview when it goes away", () => {
    const { choose, unmount } = mount();
    choose(jpeg("1.jpg"), jpeg("2.jpg"));
    unmount();
    expect(revoked.sort()).toEqual(["blob:1", "blob:2"]);
  });

  it("sends the files in page order and shows a server refusal", async () => {
    const onSubmit = vi.fn(async () => {
      throw new ApiError("too_many_pages", "30 pages au plus par chapitre.", 422);
    });
    const { choose, submit } = mount(onSubmit);
    const [a, b] = [jpeg("a.jpg"), jpeg("b.jpg")];
    choose(a, b);
    fireEvent.click(screen.getByRole("button", { name: "Monter la page 2" }));
    fireEvent.click(submit);
    expect((await screen.findByRole("alert")).textContent).toBe("30 pages au plus par chapitre.");
    expect(onSubmit).toHaveBeenCalledWith([b, a]);
  });
});

describe("DocumentPicker in English", () => {
  const english = (fn: () => void) => () => withLocale("en", fn);

  it(
    "words the refusals, the page controls and the totals",
    english(() => {
      const view = render(
        <DocumentPicker
          id="doc"
          limits={LIMITS}
          submitLabel="Prepare the chapter"
          confirm={null}
          onSubmit={async () => undefined}
          onCancel={() => undefined}
        />,
      );
      const input = view.getByLabelText("The PDF or photos of the course") as HTMLInputElement;
      const choose = (...files: File[]) => fireEvent.change(input, { target: { files } });
      choose(file("photo.heic", "image/heic"));
      expect(screen.getByRole("alert").textContent).toBe(
        "“photo.heic” is neither a PDF nor a JPEG, PNG or WebP photo.",
      );
      choose(pdf("a.pdf"), jpeg("b.jpg"));
      expect(screen.getByRole("alert").textContent).toBe("Choose a single PDF, or photos only.");
      choose(jpeg("1.jpg"), jpeg("2.jpg"));
      expect(screen.getByText("2 pages · 0 MB")).toBeTruthy();
      expect(screen.getByRole("button", { name: "Move page 1 down" })).toBeTruthy();
      expect(screen.getByRole("button", { name: "Remove page 2" })).toBeTruthy();
      expect(screen.getByRole("list", { name: "Chosen pages" })).toBeTruthy();
      choose(jpeg("3.jpg"), jpeg("4.jpg"));
      expect(screen.getByText("3 pages at most per chapter. Split the document up.")).toBeTruthy();
    }),
  );

  it(
    "words the size limit with the interface language's unit",
    english(() => {
      expect(selectionProblem([pdf("gros.pdf", 2000)], LIMITS)).toBe(
        "The document is larger than 0 MB.",
      );
    }),
  );

  it("states the limits in the hint", () =>
    withLocale("en", () => {
      render(
        <DocumentPicker
          id="doc"
          limits={{ ...LIMITS, document_max_bytes: 26214400 }}
          submitLabel="Prepare"
          confirm={null}
          onSubmit={async () => undefined}
          onCancel={() => undefined}
        />,
      );
      expect(screen.getByText(/3 pages and 25 MB at most\./)).toBeTruthy();
    }));
});
