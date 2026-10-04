// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { CourseLanguageProvider, type CourseLanguage } from "@/lib/course-language";
import { withLocale } from "@/test/locale";
import {
  ANSWER_MESSAGE,
  NEXT_SECTION_MESSAGE,
  NEXT_STEP_MESSAGE,
  REVIEW_MESSAGE,
  START_MESSAGE,
  VOICE_TOOL_FAILED,
  LEARNER_SENTENCES,
  learnerSentences,
  useLearnerSentences,
} from "../prompts";

/** What the interface says to the model for the learner is the course's language, French,
 *  whatever the interface language (spec 010 R4.3): these never go through the catalog. */
describe("the learner's sentences", () => {
  const all = () => [
    REVIEW_MESSAGE("Suites"),
    START_MESSAGE("Suites"),
    NEXT_STEP_MESSAGE,
    NEXT_SECTION_MESSAGE,
    ANSWER_MESSAGE("Oui"),
    VOICE_TOOL_FAILED,
  ];

  it("are the French strings", () => {
    expect(all()).toEqual([
      "Je voudrais revoir la section « Suites ».",
      "On commence la section « Suites » ?",
      "Étape suivante.",
      "Section suivante.",
      "Ma réponse à la question : « Oui ».",
      "Outil indisponible. Dis-le à l'élève et continue sans.",
    ]);
  });

  it("do not change with the interface language", async () => {
    const french = all();
    expect(await withLocale("en", all)).toEqual(french);
  });
});

/** Spec 011 R7.4: an English course sends English sentences, a French course the French ones
 *  byte for byte, and neither depends on the interface language. */
describe("the learner's sentences, per course language", () => {
  const read = (language: CourseLanguage) => {
    const said = learnerSentences(language);
    return [
      said.review("Sequences"),
      said.start("Sequences"),
      said.nextStep,
      said.nextSection,
      said.answer("Yes"),
      said.voiceToolFailed,
    ];
  };

  it("are the French constants for a French course", () => {
    expect(learnerSentences("fr")).toBe(LEARNER_SENTENCES.fr);
    expect(read("fr")).toEqual([
      REVIEW_MESSAGE("Sequences"),
      START_MESSAGE("Sequences"),
      NEXT_STEP_MESSAGE,
      NEXT_SECTION_MESSAGE,
      ANSWER_MESSAGE("Yes"),
      VOICE_TOOL_FAILED,
    ]);
  });

  it("are English for an English course", () => {
    expect(read("en")).toEqual([
      "I'd like to review the section “Sequences”.",
      "Shall we start the section “Sequences”?",
      "Next step.",
      "Next section.",
      "My answer to the question: “Yes”.",
      "Tool unavailable. Tell the student and carry on without it.",
    ]);
  });

  it("do not change with the interface language", async () => {
    for (const language of ["fr", "en"] as const) {
      const expected = read(language);
      expect(await withLocale("en", () => read(language))).toEqual(expected);
      expect(await withLocale("fr", () => read(language))).toEqual(expected);
    }
  });

  it("have a sentence for every key in both languages", () => {
    expect(Object.keys(LEARNER_SENTENCES.en).sort()).toEqual(
      Object.keys(LEARNER_SENTENCES.fr).sort(),
    );
  });

  it("are read from the course on screen", () => {
    function Probe() {
      return <p>{useLearnerSentences().nextStep}</p>;
    }
    render(
      <CourseLanguageProvider language="en">
        <Probe />
      </CourseLanguageProvider>,
    );
    expect(screen.getByText("Next step.")).toBeTruthy();
    cleanup();
    render(<Probe />);
    expect(screen.getByText("Étape suivante.")).toBeTruthy();
  });

  it("never reaches for the interface catalog", () => {
    const source = readFileSync(join(__dirname, "..", "prompts.ts"), "utf8");
    expect(source).not.toMatch(/^import .*paraglide/m);
  });
});
