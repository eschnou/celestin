/**
 * What the lesson shows. Every card is a real `BoardCard` of the product (the types come
 * from the frontend), written in the course's notation: decimal comma, `]a ; b[`,
 * sequences from u₁. The chapter is the student's: « Suites géométriques », her teacher's
 * handout, page numbers included.
 */
import type {
  BoardCard,
  Chapter,
  ChapterRow,
  Progress,
  TranscriptEntry,
} from "@/lib/tutor/types";

/* ------------------------------ the chapter ------------------------------ */

export const CHAPTER: Chapter = {
  id: "ch4",
  title: "Chapitre 4 — Suites géométriques",
  sections: [
    { id: "s1", index: 1, kind: "teach", title: "Reconnaître une suite géométrique", goal: "" },
    { id: "s2", index: 2, kind: "teach", title: "Somme des n premiers termes", goal: "" },
    { id: "s3", index: 3, kind: "practise", title: "Applique la formule", goal: "" },
    { id: "s4", index: 4, kind: "practise", title: "Un exercice mélangé", goal: "" },
    { id: "s5", index: 5, kind: "synthesis", title: "Synthèse du chapitre", goal: "" },
  ],
};

export const PROGRESS_AT: Record<"start" | "mid" | "end", Progress> = {
  start: { done: [], active: "s1" },
  mid: { done: ["s1"], active: "s2" },
  end: { done: ["s1", "s2", "s3"], active: "s4" },
};

export const ROW: ChapterRow = {
  id: "ch4",
  position: 4,
  title: "Suites géométriques",
  ready: false,
  section_count: 5,
  done_count: 0,
  state: "not_started",
  last: false,
  authoring_state: "generating",
  authoring_message: null,
  authoring_stage: "transcription",
  pages_done: 0,
  page_count: 4,
};

/* ------------------------------ the lesson ------------------------------- */

export const TITLE: BoardCard = {
  kind: "title",
  eyebrow: "Chapitre 4 · Suites",
  title: "Les suites géométriques",
  objective: "Calculer la somme des premiers termes, comme dans ton cours.",
};

export const EXPLANATION: BoardCard = {
  kind: "explanation",
  title: "Somme des $n$ premiers termes d'une SG",
  blocks: [
    {
      type: "text",
      text: "Dans une suite géométrique de premier terme $u_1$ et de raison $q$, la somme des $n$ premiers termes s'écrit, comme dans ton cours :",
    },
    {
      type: "quote",
      tex: "S_n = u_1 \\cdot \\dfrac{1-q^n}{1-q}",
      caption: "formule du cours — p. 14",
    },
    {
      type: "note",
      label: "Condition",
      text: "Cette formule n'est valable que si $q \\neq 1$.",
    },
  ],
};

export const WORKED: BoardCard = {
  kind: "worked_example",
  title: "Exemple du cours — p. 15",
  statement: "Calcule $S_4$ pour $u_1 = 3$ et $q = 2$.",
  steps: [
    { tex: "S_4 = u_1 \\cdot \\dfrac{1-q^4}{1-q}", note: null },
    { tex: "S_4 = 3 \\cdot \\dfrac{1-2^4}{1-2}", note: null },
    { tex: "S_4 = 3 \\cdot \\dfrac{-15}{-1} = 45", note: null },
  ],
};

export const EXERCISE: BoardCard = {
  kind: "exercise",
  title: "À toi de jouer",
  statement:
    "La suite $(u_n)$ est géométrique, de premier terme $u_1 = 3$ et de raison $q = 2$. Calcule $S_5$.",
  hint: "Relis la formule de la page 14 : que vaut $1 - q^n$ ?",
};

/** An exercise with a drawing: the board shows the chart, never the value asked for. */
export const EXERCISE_STATS: BoardCard = {
  kind: "exercise",
  title: "Lire une boîte à moustaches",
  statement: "La boîte à moustaches ci-dessous représente les notes de la classe 5A. Détermine la médiane.",
  drawing: {
    type: "chart",
    chart: {
      kind: "box",
      x_title: "Note sur 20",
      boxes: [{ label: "5A", minimum: 4, q1: 9, median: 12, q3: 14, maximum: 19 }],
    },
  },
  hint: "Relis la définition de la médiane, page 22 de ton cours.",
};

export const RECAP: BoardCard = {
  kind: "recap",
  acquired: ["La formule de $S_n$ pour une suite géométrique", "Pourquoi $q \\neq 1$"],
  watch: ["L'exposant : c'est $q^n$, pas $q \\cdot n$"],
  next: "Section suivante : un exercice mélangé, avec les suites arithmétiques.",
};

export const CHECK: BoardCard = {
  kind: "check_question",
  question: "Pourquoi la formule de $S_n$ demande-t-elle $q \\neq 1$ ?",
  options: [
    { id: "a", text: "Le dénominateur $1 - q$ serait nul" },
    { id: "b", text: "Parce que $q$ doit toujours être grand" },
    { id: "c", text: "Pour que la suite soit croissante" },
  ],
  correct_option_id: "a",
  feedback:
    "Exactement : avec $q = 1$, tous les termes sont égaux et la somme vaut simplement $n \\cdot u_1$.",
};

/* ------------------------------ the mosaic ------------------------------- */

export type Showcase = { key: string; label: string; card: BoardCard };

export const SHOWCASE: Showcase[] = [
  {
    key: "stats",
    label: "Diagrammes statistiques",
    card: {
      kind: "explanation",
      title: "Taille des élèves de 5A",
      blocks: [
        { type: "text", text: "Voici les tailles relevées dans la classe, par classes de 10 cm." },
        {
          type: "chart",
          chart: {
            kind: "histogram",
            measure: "effectif",
            bounds: [150, 160, 170, 180, 190],
            values: [3, 9, 8, 2],
            closed: "left",
            polygon: "open",
            show_values: true,
            x_title: "Taille (cm)",
            y_title: "Effectifs",
            caption: "Les classes sont de la forme [a ; b[.",
          },
        },
      ],
    },
  },
  {
    key: "box",
    label: "Boîtes à moustaches",
    card: {
      kind: "explanation",
      title: "Comparer deux classes",
      blocks: [
        { type: "text", text: "Même test, deux classes : la médiane de 5B est plus haute." },
        {
          type: "chart",
          chart: {
            kind: "box",
            x_title: "Note sur 20",
            show_values: true,
            boxes: [
              { label: "5A", minimum: 4, q1: 9, median: 12, q3: 14, maximum: 19 },
              { label: "5B", minimum: 7, q1: 11, median: 13.5, q3: 16, maximum: 20 },
            ],
          },
        },
        {
          type: "note",
          label: "À retenir",
          text: "La médiane de 5B vaut 13,5 : la moitié des élèves ont au moins cette note.",
        },
      ],
    },
  },
  {
    key: "flow",
    label: "Organigrammes",
    card: {
      kind: "explanation",
      title: "Reconnaître une suite : la méthode du cours",
      blocks: [
        {
          type: "flowchart",
          nodes: [
            {
              id: "diff",
              kind: "step",
              text: "Calculer les différences entre termes consécutifs",
              next: [{ to: "d1", label: null }],
            },
            {
              id: "d1",
              kind: "decision",
              text: "Sont-elles égales ?",
              next: [
                { to: "sa", label: "oui" },
                { to: "quot", label: "non" },
              ],
            },
            { id: "sa", kind: "step", text: "C'est une SA", next: [] },
            {
              id: "quot",
              kind: "step",
              text: "Calculer les quotients entre termes consécutifs",
              next: [{ to: "d2", label: null }],
            },
            { id: "d2", kind: "decision", text: "Sont-ils égaux ?", next: [{ to: "sg", label: "oui" }] },
            { id: "sg", kind: "step", text: "C'est une SG", next: [] },
          ],
          path: ["diff", "d1", "quot"],
        },
      ],
    },
  },
  {
    key: "geometry",
    label: "Figures géométriques",
    card: {
      kind: "explanation",
      title: "Le triangle rectangle $ABC$",
      blocks: [
        {
          type: "text",
          text: "Le triangle est rectangle en $A$ : on peut appliquer le théorème de Pythagore.",
        },
        {
          type: "figure",
          figure: {
            kind: "plane",
            points: { A: [0, 0], B: [4, 0], C: [0, 3] },
            shapes: [
              { draw: "polygon", of: ["A", "B", "C"] },
              { draw: "right_angle", of: ["B", "A", "C"] },
              { draw: "segment", of: ["A", "B"], label: "$4$ cm", marks: 1 },
              { draw: "segment", of: ["A", "C"], label: "$3$ cm", marks: 2 },
              { draw: "segment", of: ["B", "C"], label: "$5$ cm", style: "highlight" },
            ],
          },
        },
      ],
    },
  },
  {
    key: "numberline",
    label: "Droites graduées et intervalles",
    card: {
      kind: "explanation",
      title: "Notation des intervalles",
      blocks: [
        {
          type: "text",
          text: "Dans ton cours, les crochets tournés vers l'extérieur excluent la borne : A = ]−3 ; 3[ et B = [5 ; +∞[.",
        },
        {
          type: "figure",
          figure: {
            kind: "number_line",
            intervals: [
              { start: -3, end: 3, closed: "neither", label: "$A$" },
              { start: 5, end: null, closed: "left", label: "$B$" },
            ],
            marks: [{ x: 0 }],
          },
        },
        {
          type: "quote",
          text: "Un intervalle est ouvert en a quand la borne a n'en fait pas partie.",
          caption: "définition du cours — p. 31",
        },
      ],
    },
  },
  {
    key: "sets",
    label: "Ensembles",
    card: {
      kind: "explanation",
      title: "Les ensembles de nombres",
      blocks: [
        { type: "text", text: "Chaque ensemble est contenu dans le suivant : $\\mathbb{N} \\subset \\mathbb{Z} \\subset \\mathbb{D} \\subset \\mathbb{Q} \\subset \\mathbb{R}$." },
        {
          type: "figure",
          figure: {
            kind: "sets",
            layout: "nested",
            sets: ["R", "Q", "D", "Z", "N"].map((id) => ({ id, label: `$\\mathbb{${id}}$` })),
            elements: [
              { text: "$\\sqrt{2}$", within: ["R"] },
              { text: "$\\pi$", within: ["R"] },
              { text: "$\\frac{1}{3}$", within: ["Q"] },
              { text: "0,5", within: ["D"] },
              { text: "−3", within: ["Z"] },
              { text: "7", within: ["N", "Z", "D", "Q", "R"] },
            ],
          },
        },
        {
          type: "definition",
          entries: [
            {
              term: "nombre décimal",
              text: "Un nombre décimal s'écrit avec un nombre fini de chiffres après la virgule.",
            },
          ],
        },
      ],
    },
  },
  {
    key: "plot",
    label: "Graphiques de fonctions",
    card: {
      kind: "explanation",
      title: "Parabole et droite",
      blocks: [
        {
          type: "text",
          text: "Les courbes de $f(x) = x^2 - 4$ et de $g(x) = x - 2$ se coupent en deux points.",
        },
        {
          type: "plot",
          x_range: [-4, 4],
          y_range: [-5, 6],
          x_title: "$x$",
          y_title: "$y$",
          curves: [
            { expr: "x^2-4", label: "$f$" },
            { expr: "x-2", label: "$g$" },
          ],
          points: [
            { x: -1, y: -3, label: "$A$", show_values: true },
            { x: 2, y: 0, label: "$B$", show_values: true },
          ],
        },
      ],
    },
  },
];

/* ----------------------------- the conversation ----------------------------- */

export type Line = {
  at: number; // seconds after the lesson starts
  entry: TranscriptEntry;
  typed?: number; // seconds spent typing a tutor message
};

let n = 0;
const tutor = (text: string): TranscriptEntry => ({ id: `t${n++}`, role: "tutor", text, blockId: n });
const learner = (text: string): TranscriptEntry => ({ id: `l${n++}`, role: "learner", text });
const marker = (text: string, boardIndex: number | null = null): TranscriptEntry => ({
  id: `m${n++}`,
  role: "marker",
  text,
  boardIndex,
});

export const LESSON_LINES: Line[] = [
  {
    at: 0.9,
    typed: 2.4,
    entry: tutor("Bonjour Léa ! On reprend ton chapitre 4, directement dans ton cours."),
  },
  { at: 4.2, entry: marker("explication affichée", 1) },
  {
    at: 4.4,
    typed: 3,
    entry: tutor("Regarde à droite : la formule est écrite comme dans ton cours, page 14."),
  },
  { at: 8.6, entry: learner("pourquoi q ≠ 1 ?") },
  {
    at: 9.6,
    typed: 3.4,
    entry: tutor(
      "Bonne question ! Si $q = 1$, le dénominateur $1 - q$ vaut zéro : ton cours en fait un cas à part.",
    ),
  },
  { at: 13.4, entry: marker("exemple affiché", 2) },
  {
    at: 13.6,
    typed: 2.2,
    entry: tutor("Voici l'exemple de ton prof, étape par étape."),
  },
  { at: 17.2, entry: marker("exercice posé", 3) },
  {
    at: 17.4,
    typed: 2.4,
    entry: tutor("À toi : calcule $S_5$. Je ne te donne pas la réponse !"),
  },
  { at: 21.2, entry: learner("S₅ = 93") },
  { at: 22.4, entry: marker("réponse vérifiée") },
  {
    at: 22.6,
    typed: 2.2,
    entry: tutor("Exact : $S_5 = 93$. Bravo Léa, on fait le point."),
  },
];

/** When each card reaches the board, in seconds after the lesson starts. */
export const BOARD_BEATS: { at: number; card: BoardCard }[] = [
  { at: 1.1, card: TITLE },
  { at: 4.2, card: EXPLANATION },
  { at: 13.4, card: WORKED },
  { at: 17.2, card: EXERCISE },
  { at: 23.8, card: RECAP },
];
