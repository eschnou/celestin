import { describe, expect, it } from "vitest";
import {
  DUTCH,
  ENGLISH,
  FRENCH,
  formatInterval,
  formatNumber,
  formatPair,
  formatValue,
  classLabel,
  notationFor,
  type Notation,
} from "../format";
import type { Bound } from "../format";
import type { CourseLanguage } from "@/lib/course-language";
import CASES from "./notation_cases.json";

type Row =
  | {
      language: CourseLanguage;
      kind: "interval";
      args: [Bound, Bound, boolean, boolean];
      text: string;
    }
  | { language: CourseLanguage; kind: "pair"; args: [number, number]; text: string }
  | { language: CourseLanguage; kind: "number"; args: [number]; text: string };

function write(notation: Notation, row: Row): string {
  switch (row.kind) {
    case "interval":
      return notation.interval(...row.args);
    case "pair":
      return notation.pair(...row.args);
    case "number":
      return notation.number(...row.args);
  }
}

describe("the notation of each course language", () => {
  it("is chosen by the course language", () => {
    expect(notationFor("fr")).toBe(FRENCH);
    expect(notationFor("en")).toBe(ENGLISH);
    expect(notationFor("nl")).toBe(DUTCH);
  });

  it.each(CASES as Row[])("writes $kind $args as $text ($language)", (row) => {
    expect(write(notationFor(row.language), row)).toBe(row.text);
  });

  it("writes Flemish notation as the Belgian-French one, with Dutch words (spec 017)", () => {
    for (const key of [
      "number",
      "value",
      "pair",
      "bound",
      "interval",
      "classLabel",
      "separator",
    ] as const) {
      expect(DUTCH[key]).toBe(FRENCH[key]);
    }
    expect(DUTCH.number(0.45)).toBe("0,45");
    expect(DUTCH.value(12.5, "pourcentage").replace(/\s/g, " ")).toBe("12,5 %");
    expect(DUTCH.measureName).toEqual({
      effectif: "Frequentie",
      frequence: "Relatieve frequentie",
      pourcentage: "Percentage",
    });
    expect(DUTCH.boxStats).toEqual(["Minimum", "Q1", "Mediaan", "Q3", "Maximum"]);
  });

  it("keeps the French functions the French row", () => {
    expect(FRENCH.number).toBe(formatNumber);
    expect(FRENCH.value).toBe(formatValue);
    expect(FRENCH.pair).toBe(formatPair);
    expect(FRENCH.interval).toBe(formatInterval);
    expect(FRENCH.classLabel).toBe(classLabel);
  });
});

describe("English numbers", () => {
  it("use a decimal point, commas from five digits, and a true minus", () => {
    expect(ENGLISH.number(0.45)).toBe("0.45");
    expect(ENGLISH.number(12345)).toBe("12,345");
    expect(ENGLISH.number(2018)).toBe("2018");
    expect(ENGLISH.number(-3)).toBe("−3");
    expect(ENGLISH.number(0.1 + 0.2)).toBe("0.3");
  });

  it("put the percent sign against the number", () => {
    expect(ENGLISH.value(12.5, "pourcentage")).toBe("12.5%");
    expect(ENGLISH.value(12, "effectif")).toBe("12");
    expect(ENGLISH.value(0.25, "frequence")).toBe("0.25");
  });

  it("write a class and a bound in the interval notation", () => {
    expect(ENGLISH.classLabel(10, 20, "left")).toBe("[10, 20)");
    expect(ENGLISH.classLabel(10, 20, "right")).toBe("(10, 20]");
    expect(ENGLISH.classLabel(-2.5, 12500, "right")).toBe("(−2.5, 12,500]");
    expect(ENGLISH.bound(-0.5, "−∞")).toBe("−0.5");
    expect(ENGLISH.bound("$\\sqrt{2}$", "+∞")).toBe("$\\sqrt{2}$");
    expect(ENGLISH.bound(null, "−∞")).toBe("−∞");
    expect(ENGLISH.bound(null, "+∞")).toBe("∞");
  });

  it("never close an infinite end, whatever its closure says", () => {
    expect(ENGLISH.interval(null, 2, true, true)).toBe("(−∞, 2]");
    expect(ENGLISH.interval(5, null, true, true)).toBe("[5, ∞)");
    expect(ENGLISH.interval(null, null, true, true)).toBe("(−∞, ∞)");
  });
});

describe("the words the board adds", () => {
  it("name the measures and the box plot's numbers in the course's language", () => {
    expect(FRENCH.measureName).toEqual({
      effectif: "Effectif",
      frequence: "Fréquence",
      pourcentage: "Pourcentage",
    });
    expect(ENGLISH.measureName).toEqual({
      effectif: "Frequency",
      frequence: "Relative frequency",
      pourcentage: "Percentage",
    });
    expect(FRENCH.boxStats).toEqual(["Minimum", "Q1", "Médiane", "Q3", "Maximum"]);
    expect(ENGLISH.boxStats).toEqual(["Minimum", "Q1", "Median", "Q3", "Maximum"]);
  });

  it("separate the members of a list as the course does", () => {
    expect(FRENCH.separator).toBe(" ; ");
    expect(ENGLISH.separator).toBe(", ");
  });
});
