/** Plural messages in both languages (spec 010 R3.4): French treats 0 and 1 as singular, English
 *  only 1. The wording is written out per category, never built from fragments. */
import { describe, expect, it } from "vitest";
import { m } from "@/paraglide/messages";

type Case = [count: number, fr: string, en: string];

function table(name: string, say: (count: number, locale: "fr" | "en") => string, cases: Case[]) {
  describe(name, () => {
    for (const [count, fr, en] of cases) {
      it(`${count}`, () => {
        expect(say(count, "fr")).toBe(fr);
        expect(say(count, "en")).toBe(en);
      });
    }
  });
}

table("chapter sections", (count, locale) => m.chapter_status_sections({ count }, { locale }), [
  [0, "0 section", "0 sections"],
  [1, "1 section", "1 section"],
  [2, "2 sections", "2 sections"],
]);

table("course deletion", (count, locale) => m.course_delete_description({ count }, { locale }), [
  [
    0,
    "Ses 0 chapitre, leur contenu et ta progression seront effacés. C'est définitif.",
    "Its 0 chapters, their content and your progress will be erased. This can't be undone.",
  ],
  [
    1,
    "Ses 1 chapitre, leur contenu et ta progression seront effacés. C'est définitif.",
    "Its 1 chapter, its content and your progress will be erased. This can't be undone.",
  ],
  [
    2,
    "Ses 2 chapitres, leur contenu et ta progression seront effacés. C'est définitif.",
    "Its 2 chapters, their content and your progress will be erased. This can't be undone.",
  ],
]);

table("document pages", (count, locale) => m.content_document_note({ count }, { locale }), [
  [
    1,
    "Lu dans le document que tu as déposé (1 page). Le fichier n'est pas conservé.",
    "Read from the document you uploaded (1 page). The file isn't kept.",
  ],
  [
    2,
    "Lu dans le document que tu as déposé (2 pages). Le fichier n'est pas conservé.",
    "Read from the document you uploaded (2 pages). The file isn't kept.",
  ],
]);

table(
  "photos chosen",
  (count, locale) => m.content_picker_total({ count, size: "1,5 Mo" }, { locale }),
  [
    [0, "0 page · 1,5 Mo", "0 pages · 1,5 Mo"],
    [1, "1 page · 1,5 Mo", "1 page · 1,5 Mo"],
    [3, "3 pages · 1,5 Mo", "3 pages · 1,5 Mo"],
  ],
);

table(
  "exercises of a section",
  (count, locale) => m.content_exercises_from({ count, list: "6.1.1" }, { locale }),
  [
    [1, "1 exercice à partir de : 6.1.1", "1 exercise based on: 6.1.1"],
    [2, "2 exercices à partir de : 6.1.1", "2 exercises based on: 6.1.1"],
  ],
);

table(
  "characters typed",
  (count, locale) => m.content_source_count({ count, formatted: String(count) }, { locale }),
  [
    [0, "0 caractères", "0 characters"],
    [1, "1 caractères", "1 character"],
    [2, "2 caractères", "2 characters"],
  ],
);

describe("the course card progress agrees on both counts", () => {
  const progress = (done: number, total: number, locale: "fr" | "en") =>
    m.course_card_progress({ done, total }, { locale });

  it("in French, 0 and 1 are singular", () => {
    expect(progress(0, 1, "fr")).toBe("0 / 1 chapitre terminé");
    expect(progress(1, 2, "fr")).toBe("1 / 2 chapitres terminé");
    expect(progress(0, 2, "fr")).toBe("0 / 2 chapitres terminé");
    expect(progress(2, 2, "fr")).toBe("2 / 2 chapitres terminés");
  });

  it("in English, only the chapters take a plural", () => {
    expect(progress(0, 1, "en")).toBe("0 / 1 chapter completed");
    expect(progress(1, 2, "en")).toBe("1 / 2 chapters completed");
    expect(progress(2, 2, "en")).toBe("2 / 2 chapters completed");
  });
});

table(
  "chapter map progress",
  (done, locale) => m.lesson_map_progress({ done, total: 4 }, { locale }),
  [
    [0, "0 section faite sur 4", "0 of 4 sections done"],
    [1, "1 section faite sur 4", "1 of 4 sections done"],
    [2, "2 sections faites sur 4", "2 of 4 sections done"],
  ],
);

table("definitions label", (count, locale) => m.board_definitions({ count }, { locale }), [
  [0, "Définition", "Definitions"],
  [1, "Définition", "Definition"],
  [2, "Définitions", "Definitions"],
]);

table("flowchart label", (count, locale) => m.describe_flowchart_label({ count }, { locale }), [
  [0, "Organigramme en 0 étape", "Flowchart in 0 steps"],
  [1, "Organigramme en 1 étape", "Flowchart in 1 step"],
  [2, "Organigramme en 2 étapes", "Flowchart in 2 steps"],
]);

table(
  "ticks on a segment",
  (count, locale) => m.describe_figure_marks_segment({ count }, { locale }),
  [
    [1, ", codé de 1 trait", ", marked with 1 tick"],
    [2, ", codé de 2 traits", ", marked with 2 ticks"],
  ],
);

table("a curve in pieces", (count, locale) => m.describe_plot_curves({ count }, { locale }), [
  [1, "Une courbe.", "One curve."],
  [2, "Une courbe en 2 morceaux.", "One curve in 2 pieces."],
]);

table(
  "a named curve in pieces",
  (count, locale) => m.describe_plot_curves_named({ name: "f", count }, { locale }),
  [
    [1, "Courbe f.", "Curve f."],
    [2, "Courbe f, en 2 morceaux.", "Curve f, in 2 pieces."],
  ],
);

table("sequences", (count, locale) => m.describe_plot_sequences({ count }, { locale }), [
  [1, "Une suite, en points isolés.", "One sequence, as separate points."],
  [2, "2 suites, en points isolés.", "2 sequences, as separate points."],
]);

table("broken lines", (count, locale) => m.describe_plot_lines({ count }, { locale }), [
  [1, "Une ligne brisée.", "One broken line."],
  [2, "2 lignes brisées.", "2 broken lines."],
]);

table("marked points", (count, locale) => m.describe_plot_points_marked({ count }, { locale }), [
  [1, "Un point marqué.", "One marked point."],
  [2, "2 points marqués.", "2 marked points."],
]);

table("dashed drawings", (count, locale) => m.describe_plot_dashed({ count }, { locale }), [
  [1, "1 tracé en pointillés.", "1 dashed drawing."],
  [3, "3 tracés en pointillés.", "3 dashed drawings."],
]);
