// @vitest-environment jsdom
/** Spec 011 R4.3/R7: the source editor names the marks of the course's own transcription. */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { CourseLanguageProvider, type CourseLanguage } from "@/lib/course-language";
import type { ChapterContent, Limits } from "@/lib/tutor/types";
import { withLocale } from "@/test/locale";
import { SourceEditor } from "../source-editor";

afterEach(cleanup);

const LIMITS: Limits = {
  chapter_text_min_chars: 300,
  chapter_text_max_chars: 100000,
  pack_max_chars: 60000,
  document_max_bytes: 1,
  document_max_pages: 1,
  document_min_pixels: 1,
  document_types: [],
};

const content = (language: CourseLanguage): ChapterContent =>
  ({
    id: "h1",
    course_id: "c1",
    subject: "mathematics",
    language,
    position: 1,
    version: 1,
    ready: true,
    title: "T",
    pack: "# P",
    curriculum: null,
    source_text: "x".repeat(400),
    source_kind: "document",
    page_count: 2,
    authoring_state: "idle",
    authoring_message: null,
    has_progress: false,
  }) as ChapterContent;

function hint(language: CourseLanguage): string {
  render(
    <CourseLanguageProvider language={language}>
      <SourceEditor
        content={content(language)}
        limits={LIMITS}
        onSave={async () => undefined}
        onCancel={() => undefined}
      />
    </CourseLanguageProvider>,
  );
  const node = screen.getByText(/--- page N ---/);
  return node.textContent ?? "";
}

describe("the source editor's hint", () => {
  it("is the French sentence, byte for byte, for a French course", () => {
    expect(hint("fr")).toBe(
      "Corrige ce que Célestin a mal lu, surtout les passages marqués [incertain : …] ou [illisible]. Les marques « --- page N --- » indiquent les pages.",
    );
  });

  it("names the English marks for an English course, in a French interface", () => {
    const text = hint("en");
    expect(text).toContain("[uncertain: …]");
    expect(text).toContain("[illegible]");
    expect(text).not.toContain("incertain");
    expect(text).not.toContain("illisible");
  });

  it("names the English marks in an English interface, and the French ones for a French course", async () => {
    await withLocale("en", () => {
      expect(hint("en")).toBe(
        "Fix what Célestin misread, especially the passages marked [uncertain: …] or [illegible]. The “--- page N ---” marks show the pages.",
      );
      cleanup();
      expect(hint("fr")).toContain("[incertain : …]");
    });
  });
});
