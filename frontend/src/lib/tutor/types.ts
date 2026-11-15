/**
 * Mirrors the backend DTOs.
 *
 * The SSE event set is a two-sided contract, specified in
 * `specs/001-tutor-chat-agent/design.md` §3.2 and pinned by golden transcript
 * tests in the backend. Changing it here means changing it there too.
 */

import type { CourseLanguage } from "@/lib/course-language";

/* ------------------------------ board cards ------------------------------ */

export type Block =
  | { type: "text"; text: string }
  | { type: "formula"; tex: string; caption?: string | null }
  /** Quoted verbatim from the course: prose in `text`, a formula in `tex`, never both. */
  | { type: "quote"; text?: string | null; tex?: string | null; caption: string }
  | { type: "note"; label: string; text: string }
  /** Definitions quoted from the pack; each `term` appears in its `text`. */
  | { type: "definition"; entries: DefinitionEntry[] }
  | Drawing;

export type DefinitionEntry = { term: string; text: string };

/* --------------------------------- charts --------------------------------- */

/** Statistics, never geometry: the board draws the chart from them (spec 008). */
export type Measure = "effectif" | "frequence" | "pourcentage";
/** `left` is [a ; b[, `right` is ]a ; b]. */
export type Closed = "left" | "right";

type Shown = { show_values?: boolean; caption?: string | null };
type Counts = Shown & { measure: Measure };
/** A grouped series: n classes between n + 1 bounds. */
type Classes = Counts & {
  bounds: number[];
  values: number[];
  closed: Closed;
  x_title: string;
  y_title: string;
};

export type BarChart = Counts & {
  kind: "bars";
  categories: string[];
  values: number[];
  x_title?: string | null;
  y_title: string;
};
export type StickChart = Counts & {
  kind: "sticks";
  x: number[];
  values: number[];
  polygon?: boolean;
  x_title: string;
  y_title: string;
};
export type Histogram = Classes & {
  kind: "histogram";
  reference_amplitude?: number | null;
  bars?: boolean;
  polygon?: "none" | "open" | "closed";
};
export type CumulativePolygon = Classes & {
  kind: "cumulative";
  direction: "increasing" | "decreasing";
};
export type PieChart = Counts & { kind: "pie"; categories: string[]; values: number[] };
export type Box = {
  label?: string | null;
  minimum: number;
  q1: number;
  median: number;
  q3: number;
  maximum: number;
};
export type BoxPlot = Shown & { kind: "box"; boxes: Box[]; x_title?: string | null };
export type Chart = BarChart | StickChart | Histogram | CumulativePolygon | PieChart | BoxPlot;
export type ChartBlock = { type: "chart"; chart: Chart };

/* ------------------------------- flowcharts ------------------------------- */

/** A method as an organigramme: nodes and their exits; the board lays it out. */
export type FlowNodeKind = "start" | "end" | "step" | "decision" | "io";
export type FlowExit = { to: string; label?: string | null };
export type FlowNode = {
  id: string;
  /** "step" when absent (the backend default; always present on the wire). */
  kind?: FlowNodeKind;
  text: string;
  /** At most two; only a decision has two. */
  next?: FlowExit[];
};
export type FlowchartBlock = {
  type: "flowchart";
  /** The first node is where the flowchart starts. */
  nodes: FlowNode[];
  /** Nodes followed so far, in the arrows' order; the last is the current step. */
  path?: string[];
  /** On an exercise's drawing: nodes shown as « ? ». Their text never reaches the DOM. */
  hidden?: string[];
  caption?: string | null;
};

/* -------------------------------- figures -------------------------------- */

/** Drawn by the board from points and relations, never from pixels. */
export type FigureDraw =
  "segment" | "line" | "ray" | "vector" | "polygon" | "circle" | "arc" | "angle" | "right_angle";

export type FigureShape = {
  draw: FigureDraw;
  /** Point names; how many, and in which order, depends on `draw`. */
  of: string[];
  radius?: number | null;
  /** Codage: ticks on a segment, arcs on an angle (0–3). */
  marks?: number;
  label?: string | null;
  style?: "dashed" | "highlight" | null;
};

type FigureShown = { show_values?: boolean; caption?: string | null };

export type PlaneFigure = FigureShown & {
  kind: "plane";
  /** Name → [x, y] in the figure's own units, y up. */
  points?: Record<string, number[]>;
  shapes?: FigureShape[];
  x_range?: number[] | null;
  y_range?: number[] | null;
  axes?: boolean;
  grid?: boolean;
  marker?: "cross" | "dot";
};

/** `start` null is −∞, `end` null is +∞. */
export type LineInterval = {
  start?: number | null;
  end?: number | null;
  closed: "both" | "left" | "right" | "neither";
  label?: string | null;
};
export type LineMark = { x: number; label?: string | null };

export type NumberLine = FigureShown & {
  kind: "number_line";
  intervals?: LineInterval[];
  marks?: LineMark[];
  convention?: "brackets" | "dots" | "hatched";
};

export type FigureSet = { id: string; label: string };
/** `within`: the sets holding the element (the sets containing them count too); [] is outside them all. */
export type SetElement = { text: string; within?: string[] };

export type SetDiagram = {
  kind: "sets";
  layout: "nested" | "overlap" | "separate";
  /** Outermost first when nested. */
  sets: FigureSet[];
  universe?: string | null;
  elements?: SetElement[];
  shade?: string[][];
  caption?: string | null;
};

export type Figure = PlaneFigure | NumberLine | SetDiagram;
export type FigureBlock = { type: "figure"; figure: Figure };

/* ---------------------------------- plots ---------------------------------- */

/** A graph in a cartesian plane: Célestin gives the maths, the board samples and draws it. */
export type PlotDot = "none" | "filled" | "hollow";
/** [min, max] on an axis, [a, b] for a domain, [x, y] for a vertex. */
export type PlotPair = [number, number];

export type PlotCurve = {
  /** Our grammar (components/celestin/plot/expression.ts), in x or t. Never shown as text. */
  expr: string;
  domain?: PlotPair | null;
  start_dot?: PlotDot;
  end_dot?: PlotDot;
  dashed?: boolean;
  label?: string | null;
};
export type PlotSequence = { expr: string; first?: number; last: number; label?: string | null };
export type PlotPoint = {
  x: number;
  y: number;
  label?: string | null;
  mark?: "filled" | "hollow" | "cross";
  guides?: boolean;
  show_values?: boolean;
};
export type PlotLine = { vertices: PlotPair[]; dashed?: boolean; label?: string | null };
export type PlotBlock = {
  type: "plot";
  x_range: PlotPair;
  y_range: PlotPair;
  x_title: string;
  y_title: string;
  x_step?: number | null;
  y_step?: number | null;
  grid?: boolean;
  orthonormal?: boolean;
  curves?: PlotCurve[];
  sequences?: PlotSequence[];
  points?: PlotPoint[];
  lines?: PlotLine[];
  caption?: string | null;
};

/** What a worked example or an exercise draws under its statement: one drawing block. */
export type Drawing = ChartBlock | FlowchartBlock | FigureBlock | PlotBlock;

export type Step = { tex: string; note?: string | null };
export type Option = { id: string; text: string };

export type TitleCard = { kind: "title"; eyebrow: string; title: string; objective: string };
export type ExplanationCard = { kind: "explanation"; title: string; blocks: Block[] };
export type WorkedExampleCard = {
  kind: "worked_example";
  title: string;
  statement: string;
  drawing?: Drawing | null;
  steps: Step[];
};
export type ExerciseCard = {
  kind: "exercise";
  title: string;
  statement: string;
  drawing?: Drawing | null;
  hint?: string | null;
};
export type CheckQuestionCard = {
  kind: "check_question";
  question: string;
  options: Option[];
  correct_option_id: string;
  feedback: string;
};
export type RecapCard = { kind: "recap"; acquired: string[]; watch: string[]; next: string };

export type BoardCard =
  TitleCard | ExplanationCard | WorkedExampleCard | ExerciseCard | CheckQuestionCard | RecapCard;

/* ------------------------------- chapter --------------------------------- */

export type SectionKind = "teach" | "practise" | "synthesis";

/** What `GET /api/chapters/current` returns per section: never beats or exercises. */
export type SectionOverview = {
  id: string;
  index: number;
  kind: SectionKind;
  title: string;
  goal: string;
};

export type Chapter = { id: string; title: string; sections: SectionOverview[] };

/** `GET /api/courses/{courseId}/chapters/{chapterId}`: the overview plus where the student is (005). */
export type ChapterView = Chapter & {
  /** Its rank in the course: the chapter's number, which the backend puts in `title`. */
  position: number;
  course_id: string;
  course_name: string;
  subject: SubjectId;
  /** The course's language: Célestin's, the board's, the pack's (spec 011). */
  language: CourseLanguage;
  progress: Progress;
};

/* ------------------------------- courses -------------------------------- */

/** Four categories, grouped by how a subject is taught (backend `domain/subject.py`). */
export type SubjectId = "mathematics" | "sciences" | "languages" | "general";

/** `languages`: the course languages the subject is offered in (spec 011). */
export type Subject = { id: SubjectId; label: string; languages: CourseLanguage[] };

/** What the server accepts: text lengths (the transcription editor) and documents (006). */
export type Limits = {
  chapter_text_min_chars: number;
  chapter_text_max_chars: number;
  pack_max_chars: number;
  document_max_bytes: number;
  document_max_pages: number;
  document_min_pixels: number;
  document_types: string[];
};

export type SubjectsResponse = { subjects: Subject[]; limits: Limits };

export type ChapterState = "not_started" | "in_progress" | "done";

/** Where a chapter's preparation stands: nothing running, running, or the last run failed. */
export type AuthoringState = "idle" | "generating" | "failed";

/** The step a preparation is at, or stopped at when it failed (006). */
export type AuthoringStage = "transcription" | "pack" | "curriculum";

export type ChapterRow = {
  id: string;
  position: number;
  title: string | null;
  ready: boolean;
  section_count: number;
  done_count: number;
  /** Spec 019: how many sections were passed, apart from done ones. The server says
   *  « done » once done and skipped cover every section; the browser never recomputes it. */
  skipped_count: number;
  state: ChapterState;
  last: boolean;
  authoring_state: AuthoringState;
  authoring_message: string | null;
  authoring_stage: AuthoringStage | null;
  pages_done: number;
  page_count: number;
  authoring_received_chars: number;
  authoring_quiet_s: number | null;
};

export type CourseSummary = {
  id: string;
  name: string;
  subject: SubjectId;
  subject_label: string;
  language: CourseLanguage;
  chapters_total: number;
  chapters_done: number;
  last_chapter: { id: string; title: string } | null;
  generating: number;
};

export type CoursesResponse = { courses: CourseSummary[] };

export type CourseDetail = CourseSummary & { chapters: ChapterRow[] };

/** A section as the path editor sends it (005 design 4.3). */
export type SectionIn = {
  id: string;
  kind: SectionKind;
  title: string;
  goal: string;
  done_when: string;
  pack: string[];
  beats: string[];
  exercises: string[];
  count: number | null;
};

export type CurriculumIn = { title: string; sections: SectionIn[] };

export type SectionFull = SectionIn & { index: number };

/** `GET …/content`: the student's own view of a chapter, everything included. */
export type ChapterContent = {
  id: string;
  course_id: string;
  subject: SubjectId;
  language: CourseLanguage;
  position: number;
  version: number;
  ready: boolean;
  title: string | null;
  pack: string | null;
  curriculum: { title: string; sections: SectionFull[] } | null;
  source_text: string;
  source_kind: "text" | "document";
  page_count: number;
  authoring_state: AuthoringState;
  authoring_message: string | null;
  has_progress: boolean;
};

/** Which course and chapter a turn or a voice call belongs to (005). */
export type LessonScope = {
  courseId: string;
  chapterId: string;
  /** Discussion mode (007): which mode the voice session is for, and which stored
   *  conversation it seeds from. Absent means the parcours. A révision (spec 020) has no
   *  voice and no chapter scope, so it never appears here. */
  mode?: "parcours" | "discussion";
  conversationId?: string;
};

/** Where the learner is. Owned by the server (004), which sends it with the chapter.
 *  `skipped` (spec 019): the sections the student chose to pass, kept apart from done. */
export type Progress = { done: string[]; active: string | null; skipped: string[] };

export const EMPTY_PROGRESS: Progress = { done: [], active: null, skipped: [] };

/** A progress on the wire: `skipped` may be missing (a backend older than spec 019). */
export type WireProgress = Omit<Progress, "skipped"> & { skipped?: string[] | null | undefined };

/** A progress as the server sent it, made whole: a server older than spec 019 sends no
 *  `skipped`. The one place a server progress enters the browser (the séance read, the
 *  chapter view, the voice tool response), so nothing downstream checks for it. */
export function progressFrom(raw: WireProgress): Progress {
  return { done: raw.done, active: raw.active, skipped: raw.skipped ?? [] };
}

/** Spec 019: no section is locked. `available` is the one Célestin proposes; `open` is
 *  every other section that is neither done, active nor skipped. */
export type SectionState = "done" | "active" | "skipped" | "available" | "open";

/** What the board's page-turn button offers: a step Célestin proposed, the next
 *  section after one closed, or nothing (greyed). */
export type NextStep = { kind: "step" } | { kind: "section"; sectionId: string } | null;

/* -------------------------------- events --------------------------------- */

export type TurnEndReason = "end" | "max_rounds" | "cancelled";

export type TutorEvent =
  | { event: "turn.start"; turn_id: string }
  | { event: "text.delta"; block_id: number; text: string }
  | { event: "board.set"; card: BoardCard; marker: string }
  | { event: "board.clear"; marker: string }
  | { event: "section.start"; section_id: string; review: boolean; marker: string }
  | { event: "section.done"; section_id: string; next_section_id: string | null; marker: string }
  /** Spec 019: `active_section_id` is the section still being worked after the skip (null
   *  when none); `next_section_id` the proposed next section when nothing is active, else
   *  null. Both null: the skip finished the chapter. */
  | {
      event: "section.skipped";
      section_id: string;
      next_section_id: string | null;
      active_section_id: string | null;
      marker: string;
    }
  | { event: "step.ready"; marker: string }
  /** Spec 020: a self-assessment Célestin noted in a révision (`record_result`). The marker
   *  says what was noted, so the student sees everything recorded about them. */
  | {
      event: "revision.result";
      chapter_id: string;
      section_id: string;
      outcome: RevisionOutcome;
      marker: string;
    }
  | { event: "turn.end"; reason: TurnEndReason; usage: Record<string, unknown> }
  | { event: "error"; code: string; message: string };

/* ------------------------------ transcript ------------------------------- */

/** The model-facing view of the conversation, kept by the session: what a spoken turn
 *  reports to the server (007 D1, 018). Markers and errors are presentation only. */
export type HistoryEntry =
  | { kind: "learner"; text: string }
  | { kind: "tutor"; text: string }
  | {
      kind: "tool";
      name: string;
      arguments: Record<string, unknown>;
      ok: boolean;
      /** On a `start_section` entry only: whether the call was a review (spec 018). The
       *  server keeps it with the stored séance and never sends it to the model. */
      review?: boolean;
      /** What a `complete_section` (`next_section_id`) or a `skip_section` (both) call
       *  answered at the time, from its event (spec 019): the server replays the stored
       *  call from them, never from a later progress. Never sent to the model. */
      next_section_id?: string | null;
      active_section_id?: string | null;
    };

/** A stored entry of a discussion (007 §4.3) or a parcours séance (018), as the server
 *  reads it back. The `marker` is the label the transcript shows for a tool call, in the
 *  account's interface language; the backend owns its wording, so it comes over the wire
 *  rather than being rebuilt here. Only ok calls are returned. */
export type StoredEntry = {
  kind: "learner" | "tutor" | "tool";
  text?: string | null;
  name?: string | null;
  arguments?: Record<string, unknown> | null;
  marker?: string | null;
  /** `start_section` only: the call was a review. */
  review?: boolean | null;
  /** `complete_section` and `skip_section` (spec 019) only: the section the page-turn
   *  button offers next, read from the student's current progress (null while a section
   *  is active). */
  next_section_id?: string | null;
  /** `skip_section` only: the section active now, null when none. */
  active_section_id?: string | null;
  /** `record_result` only (spec 020): what was noted, beside the model's own `arguments`
   *  (which name the chapter by its number). */
  chapter_id?: string | null;
  section_id?: string | null;
  outcome?: RevisionOutcome | null;
};

/** The live parcours séance of one chapter (spec 018 D2): the stretch of work the lesson
 *  view is in. The server also sends its `id` and its `section_id` (null while it holds only
 *  a greeting); the lesson reads only the entries it folds back. */
export type Seance = { entries: StoredEntry[] };

/** One thing the cahier shows for a section: a card as it was shown, or a line said. */
export type NotebookItem =
  { kind: "card"; card: BoardCard } | { kind: "tutor" | "learner"; text: string };

/** `GET …/notebook` (spec 018 D8): per section in path order, everything shown and said in
 *  its stored séances, oldest first; only sections with at least one item. */
export type NotebookSection = { section_id: string; items: NotebookItem[] };
export type Notebook = { sections: NotebookSection[] };

/** One stored discussion on one chapter (007 §4.3). */
export type Conversation = {
  id: string;
  chapter_id: string;
  entries: StoredEntry[];
  entry_count: number;
  created_at: string;
};

/* -------------------------------- révision -------------------------------- */

/** The student's own judgement of a question (spec 020 D3): acquis, fragile, à revoir. */
export type RevisionOutcome = "solid" | "shaky" | "todo";

export const REVISION_OUTCOMES = [
  "solid",
  "shaky",
  "todo",
] as const satisfies readonly RevisionOutcome[];

/** A self-assessment noted this session, as the `revision.result` event carries it. */
export type RevisionMark = { chapter_id: string; section_id: string; outcome: RevisionOutcome };

/** The latest self-assessment of a section, as `GET …/revision` returns it. */
export type RevisionResult = RevisionMark & { at: string };

/** The live révision of a course (spec 020): its chosen chapters and its stored entries. */
export type Revision = {
  id: string;
  chapter_ids: string[];
  entries: StoredEntry[];
  entry_count: number;
  created_at: string;
};

/** A section of a chapter as the révision page shows it: where the path stands, never its
 *  beats or exercises. `todo` is never done nor skipped. */
export type RevisionSection = {
  id: string;
  index: number;
  kind: SectionKind;
  title: string;
  state: "done" | "skipped" | "todo";
};

/** Every chapter of the course; `sections` is empty for one that is not ready. */
export type RevisionChapter = {
  id: string;
  position: number;
  title: string | null;
  ready: boolean;
  section_count: number;
  done_count: number;
  skipped_count: number;
  sections: RevisionSection[];
};

/** `GET /api/courses/{c}/revision`. */
export type RevisionView = {
  revision: Revision | null;
  chapters: RevisionChapter[];
  results: RevisionResult[];
};

/** What the browser renders. */
export type TranscriptEntry =
  | { id: string; role: "learner"; text: string; spoken?: true }
  | {
      id: string;
      role: "tutor";
      text: string;
      blockId: number;
      interrupted?: boolean;
      spoken?: true;
    }
  | { id: string; role: "marker"; text: string; boardIndex: number | null }
  | { id: string; role: "error"; text: string; code?: string };
