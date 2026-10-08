// @vitest-environment jsdom
/** Spec 011 §5.1: the course's language reaches the screens that show course text. */
import { cleanup, render, screen } from "@testing-library/react";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
  COURSE_LANGUAGES,
  CourseLanguageProvider,
  isCourseLanguage,
  useCourseLanguage,
} from "@/lib/course-language";
import { ChapterStrip } from "@/components/celestin/chapter-strip";

afterEach(cleanup);

function Probe() {
  return <p data-testid="probe">{useCourseLanguage()}</p>;
}

describe("useCourseLanguage", () => {
  it("is French outside a provider", () => {
    render(<Probe />);
    expect(screen.getByTestId("probe").textContent).toBe("fr");
  });

  it("is the provided language, and the nearest provider wins", () => {
    render(
      <CourseLanguageProvider language="en">
        <Probe />
        <CourseLanguageProvider language="fr">
          <span data-testid="inner">
            <Probe />
          </span>
        </CourseLanguageProvider>
      </CourseLanguageProvider>,
    );
    expect(screen.getAllByTestId("probe").map((n) => n.textContent)).toEqual(["en", "fr"]);
  });

  it("knows the three course languages", () => {
    expect(COURSE_LANGUAGES).toEqual(["fr", "en", "nl"]);
    expect(isCourseLanguage("nl") && isCourseLanguage("fr") && isCourseLanguage("en")).toBe(true);
    expect(isCourseLanguage("de") || isCourseLanguage(null) || isCourseLanguage("")).toBe(false);
  });
});

describe("course text is marked with the course's language", () => {
  const chapter = {
    id: "c",
    title: "Sequences",
    sections: [{ id: "s1", index: 1, kind: "teach" as const, title: "Terms", goal: "g" }],
  };

  it.each(["fr", "en", "nl"] as const)(
    "a chapter title carries the course language (%s)",
    (language) => {
      render(
        <CourseLanguageProvider language={language}>
          <ChapterStrip chapter={chapter} progress={{ done: [], active: "s1" }} onOpen={() => {}} />
        </CourseLanguageProvider>,
      );
      expect(document.body.querySelectorAll(`[lang="${language}"]`).length).toBeGreaterThan(0);
      for (const other of COURSE_LANGUAGES.filter((l) => l !== language)) {
        expect(document.body.querySelectorAll(`[lang="${other}"]`).length).toBe(0);
      }
    },
  );
});

describe("no constant stands in for the course's language any more", () => {
  it("COURSE_LANG is gone from the source", () => {
    const hits: string[] = [];
    const walk = (dir: string) => {
      for (const name of readdirSync(dir)) {
        const path = join(dir, name);
        if (name === "paraglide" || name === "node_modules") continue;
        if (statSync(path).isDirectory()) walk(path);
        else if (/\.(ts|tsx)$/.test(name) && !path.endsWith("course-language.test.tsx")) {
          if (readFileSync(path, "utf8").includes("COURSE_LANG ")) hits.push(path);
          if (/\bCOURSE_LANG\b/.test(readFileSync(path, "utf8"))) hits.push(path);
        }
      }
    };
    walk(join(__dirname, "..", ".."));
    expect(hits).toEqual([]);
  });
});
