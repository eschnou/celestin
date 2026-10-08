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
   *  conversation it seeds from. Absent means the parcours. */
  mode?: "parcours" | "discussion";
  conversationId?: string;
};

/** Where the learner is. Held by the browser, posted with every turn. */
export type Progress = { done: string[]; active: string | null };

export const EMPTY_PROGRESS: Progress = { done: [], active: null };

export type SectionState = "done" | "active" | "available" | "locked";

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
  | { event: "step.ready"; marker: string }
  | { event: "turn.end"; reason: TurnEndReason; usage: Record<string, unknown> }
  | { event: "error"; code: string; message: string };

/* ------------------------------ transcript ------------------------------- */

/** What the browser posts back. Markers and errors are presentation only. */
export type HistoryEntry =
  | { kind: "learner"; text: string }
  | { kind: "tutor"; text: string }
  | { kind: "tool"; name: string; arguments: Record<string, unknown>; ok: boolean };

/** A stored discussion entry, as the server reads it back (007 §4.3). The
 *  `marker` is the French label the transcript shows for a tool call; the backend
 *  owns its wording, so it comes over the wire rather than being rebuilt here. */
export type StoredEntry = {
  kind: "learner" | "tutor" | "tool";
  text?: string | null;
  name?: string | null;
  arguments?: Record<string, unknown> | null;
  marker?: string | null;
};

/** One stored discussion on one chapter (007 §4.3). */
export type Conversation = {
  id: string;
  chapter_id: string;
  entries: StoredEntry[];
  entry_count: number;
  created_at: string;
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
