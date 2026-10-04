/**
 * The chapter strip (002 design 3.11): constant position awareness in ~72 px.
 *
 * A pure view of the chapter overview and the progress. Tapping it opens the map.
 */

import { memo } from "react";
import { Check, ChevronRight, Lock } from "lucide-react";
import { useCourseLanguage } from "@/lib/course-language";
import { cn } from "@/lib/utils";
import { m } from "@/paraglide/messages";
import { KIND_LABEL } from "@/lib/tutor/labels";
import { chapterModel } from "@/lib/tutor/chapter-model";
import type { Chapter, Progress, SectionState } from "@/lib/tutor/types";

const SEGMENT: Record<SectionState, string> = {
  done: "bg-success",
  active: "bg-primary",
  available: "bg-border",
  locked: "bg-border",
};

type ChapterStripProps = {
  chapter: Chapter | null;
  progress: Progress;
  /** The chapter query failed. */
  unavailable?: boolean;
  onOpen: () => void;
  /** The small-screen strip: no card, no chapter title (the bar says where we are),
   *  the count beside the current section. */
  compact?: boolean;
};

export const ChapterStrip = memo(function ChapterStrip({
  chapter,
  progress,
  unavailable = false,
  onOpen,
  compact = false,
}: ChapterStripProps) {
  const language = useCourseLanguage();
  if (!chapter) {
    return (
      <div
        className={cn(
          "text-xs text-muted-foreground",
          compact ? "px-3 py-2" : "rounded-lg border border-border bg-card p-3 shadow-sheet",
        )}
        aria-busy={!unavailable}
      >
        {unavailable ? m.lesson_path_unavailable() : m.chapter_loading()}
      </div>
    );
  }

  const model = chapterModel(chapter, progress);
  const count = (
    <span className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground tabular-nums">
      {model.doneCount} / {model.total}
      <ChevronRight className="size-3.5" />
    </span>
  );
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={m.lesson_strip_open()}
      className={cn(
        "block w-full text-left transition-colors hover:bg-secondary/60",
        compact ? "px-3 py-2" : "rounded-lg border border-border bg-card p-3 shadow-sheet",
      )}
    >
      {!compact && (
        <div className="flex items-baseline justify-between gap-2">
          <h2
            lang={language}
            className="truncate text-[11px] font-bold tracking-[0.12em] text-muted-foreground uppercase"
          >
            {chapter.title}
          </h2>
          {count}
        </div>
      )}
      <div className={cn("flex gap-0.5", !compact && "mt-2")} aria-hidden="true">
        {model.segments.map((state, i) => (
          <span
            key={i}
            data-state={state}
            className={cn("flex-1 rounded-sm", compact ? "h-1" : "h-1.5", SEGMENT[state])}
          />
        ))}
      </div>
      <p className={cn("flex items-center gap-1.5 truncate text-sm", compact ? "mt-1.5" : "mt-2")}>
        {model.focus.kind === "complete" ? (
          <>
            <Check className="size-3.5 shrink-0 text-success" strokeWidth={3} />
            <span className="font-semibold">{m.lesson_strip_complete()}</span>
          </>
        ) : (
          <>
            {model.focus.kind === "active" ? (
              <span className="size-2.5 shrink-0 rounded-full bg-primary" />
            ) : (
              <Lock className="size-3.5 shrink-0 text-muted-foreground" />
            )}
            <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
              {model.focus.kind === "next" && `${m.lesson_strip_next()} · `}
              {model.focus.section.index} · {KIND_LABEL[model.focus.section.kind]()}
            </span>
            <span
              lang={language}
              className={cn(
                "truncate",
                model.focus.kind === "active" ? "font-bold" : "font-semibold",
              )}
            >
              {model.focus.section.title}
            </span>
          </>
        )}
        {compact && <span className="ml-auto pl-2">{count}</span>}
      </p>
    </button>
  );
});
