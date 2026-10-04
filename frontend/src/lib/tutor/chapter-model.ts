/** What the strip and the map both derive from the chapter and the progress
 *  (002 design 3.11): one computation, so their counts cannot disagree. */

import { sectionStates } from "./path";
import type { Chapter, Progress, SectionOverview, SectionState } from "./types";

export type ChapterModel = {
  doneCount: number;
  total: number;
  segments: SectionState[];
  /** What the bottom line talks about. */
  focus:
    | { kind: "active"; section: SectionOverview }
    | { kind: "next"; section: SectionOverview }
    | { kind: "complete" };
};

export function chapterModel(chapter: Chapter, progress: Progress): ChapterModel {
  const states = sectionStates(chapter.sections, progress);
  const segments = chapter.sections.map((s) => states[s.id] ?? "locked");
  const active = chapter.sections.find((s) => states[s.id] === "active");
  const next = chapter.sections.find((s) => states[s.id] === "available");
  return {
    doneCount: segments.filter((s) => s === "done").length,
    total: chapter.sections.length,
    segments,
    focus: active
      ? { kind: "active", section: active }
      : next
        ? { kind: "next", section: next }
        : { kind: "complete" },
  };
}
