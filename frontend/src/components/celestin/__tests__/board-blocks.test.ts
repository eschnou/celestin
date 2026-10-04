import { describe, expect, it } from "vitest";
import { markTerm, splitInlineMath } from "../board-blocks";

const values = (s: string) => splitInlineMath(s).map((p) => [p.math, p.value]);

describe("splitInlineMath", () => {
  it("leaves plain prose alone", () => {
    expect(values("Bonjour toi")).toEqual([[false, "Bonjour toi"]]);
  });

  it("splits a formula out of a sentence", () => {
    expect(values("La raison $q$ vaut 2")).toEqual([
      [false, "La raison "],
      [true, "q"],
      [false, " vaut 2"],
    ]);
  });

  it("handles several formulas", () => {
    expect(values("$u_1$ et $q$")).toEqual([
      [true, "u_1"],
      [false, " et "],
      [true, "q"],
    ]);
  });

  it("keeps an unmatched dollar literal instead of swallowing the rest", () => {
    expect(values("Il coûte 30$ en 2000")).toEqual([[false, "Il coûte 30$ en 2000"]]);
  });

  it("does not let a price hijack the maths later in the sentence", () => {
    expect(values("Le prix est 30$ et $x^2$ vaut 4.")).toEqual([
      [false, "Le prix est 30$ et "],
      [true, "x^2"],
      [false, " vaut 4."],
    ]);
  });

  it("handles two prices around one formula", () => {
    expect(values("de 25$ à 20$, donc $q = 0,8$")).toEqual([
      [false, "de 25$ à 20$, donc "],
      [true, "q = 0,8"],
    ]);
  });

  it("refuses to open on a dollar followed by a space", () => {
    expect(values("coûte 30$ puis 25$ ensuite")).toEqual([[false, "coûte 30$ puis 25$ ensuite"]]);
  });

  it("refuses to close on a dollar preceded by a space", () => {
    expect(values("$q$ vaut 2, soit 30 $")).toEqual([
      [true, "q"],
      [false, " vaut 2, soit 30 $"],
    ]);
  });

  it("keeps a trailing unmatched dollar after a real formula", () => {
    expect(values("$q$ puis 30$")).toEqual([
      [true, "q"],
      [false, " puis 30$"],
    ]);
  });

  it("keeps an unclosed double dollar literal", () => {
    expect(values("a$$b")).toEqual([[false, "a$$b"]]);
  });

  it("treats an empty pair as literal text", () => {
    expect(values("a$$$$b")).toEqual([[false, "a$$$$b"]]);
  });

  it("renders display maths written with double dollars", () => {
    const parts = splitInlineMath("Voici :\n$$81 ; 54 ; 36$$");
    expect(parts).toEqual([
      { math: false, value: "Voici :\n" },
      { math: true, value: "81 ; 54 ; 36", display: true },
    ]);
  });

  it("does not leave the double dollars in the output", () => {
    expect(
      splitInlineMath("$$S_n = u_1$$")
        .map((p) => p.value)
        .join(""),
    ).not.toContain("$");
  });

  it("marks single dollars as inline, not display", () => {
    expect(splitInlineMath("la raison $q$")[1]).toEqual({
      math: true,
      value: "q",
      display: false,
    });
  });

  it("mixes display and inline in one string", () => {
    expect(values("$$A$$ et $b$")).toEqual([
      [true, "A"],
      [false, " et "],
      [true, "b"],
    ]);
  });

  it("keeps a lone double dollar literal when it never closes", () => {
    expect(values("coût $$ inconnu")).toEqual([[false, "coût $$ inconnu"]]);
  });

  it("handles a formula at each end", () => {
    expect(values("$a$ milieu $b$")).toEqual([
      [true, "a"],
      [false, " milieu "],
      [true, "b"],
    ]);
  });

  it("never returns an empty list", () => {
    expect(splitInlineMath("")).toEqual([{ math: false, value: "" }]);
  });
});

describe("markTerm", () => {
  const marked = (text: string, term: string) =>
    markTerm(splitInlineMath(text), term).map((p) => [p.value, p.strong ?? false]);

  it("marks the first occurrence, whatever its case", () => {
    expect(marked("Un individu est un élément de la population.", "Individu")).toEqual([
      ["Un ", false],
      ["individu", true],
      [" est un élément de la population.", false],
    ]);
  });

  it("matches accented capitals and runs of whitespace", () => {
    expect(marked("L'Échantillon  statistique étudié", "échantillon statistique")).toEqual([
      ["L'", false],
      ["Échantillon  statistique", true],
      [" étudié", false],
    ]);
  });

  it("leaves maths and the rest of the sentence alone", () => {
    expect(marked("La raison $r$ : on appelle raison ce nombre", "raison")).toEqual([
      ["La ", false],
      ["raison", true],
      [" ", false],
      ["r", false],
      [" : on appelle raison ce nombre", false],
    ]);
  });

  it("treats the term literally, never as a pattern", () => {
    expect(marked("Une moyenne (arithmétique) est…", "moyenne (arithmétique)")).toEqual([
      ["Une ", false],
      ["moyenne (arithmétique)", true],
      [" est…", false],
    ]);
  });

  it("changes nothing when the term is missing", () => {
    expect(marked("Un élément de la population.", "individu")).toEqual([
      ["Un élément de la population.", false],
    ]);
  });
});
