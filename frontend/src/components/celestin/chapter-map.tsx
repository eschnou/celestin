/**
 * The chapter map (002 design 3.11): the full path, on demand.
 *
 * Rows only display; the backend decides what may start. A done row offers a
 * review, the next row an opening, both as ordinary learner messages.
 */

import { memo, useState } from "react";
import { Check, Lock } from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { useCourseLanguage } from "@/lib/course-language";
import { cn } from "@/lib/utils";
import { m } from "@/paraglide/messages";
import { chapterModel } from "@/lib/tutor/chapter-model";
import { KIND_LABEL, STATE_LABEL } from "@/lib/tutor/labels";
import { useLearnerSentences } from "@/lib/tutor/prompts";
import type { Chapter, Progress, SectionOverview, SectionState } from "@/lib/tutor/types";

type ChapterMapProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  chapter: Chapter;
  progress: Progress;
  /** A turn is in flight: actions wait. */
  streaming: boolean;
  onSend: (text: string) => void;
  onReset: () => void;
};

function Dot({ state }: { state: SectionState }) {
  if (state === "done") {
    return (
      <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-success text-success-foreground">
        <Check className="size-3" strokeWidth={3} />
      </span>
    );
  }
  if (state === "locked") {
    return (
      <span className="flex size-5 shrink-0 items-center justify-center rounded-full border border-border text-muted-foreground">
        <Lock className="size-2.5" />
      </span>
    );
  }
  return (
    <span
      className={cn(
        "size-5 shrink-0 rounded-full border-2",
        state === "active" ? "border-primary bg-primary/20" : "border-primary/50 bg-card",
      )}
    />
  );
}

function Row({
  section,
  state,
  last,
  streaming,
  onAction,
}: {
  section: SectionOverview;
  state: SectionState;
  last: boolean;
  streaming: boolean;
  onAction: (text: string) => void;
}) {
  const language = useCourseLanguage();
  const said = useLearnerSentences();
  const action =
    state === "done"
      ? { label: m.chapter_action_review(), text: said.review(section.title) }
      : state === "available"
        ? { label: m.chapter_action_start(), text: said.start(section.title) }
        : null;
  return (
    <li
      className={cn("relative flex gap-3 pb-4", state === "locked" && "opacity-55")}
      aria-disabled={state === "locked" || undefined}
      data-state={state}
    >
      {/* the rail */}
      {!last && (
        <span
          aria-hidden="true"
          className={cn(
            "absolute top-5 left-[9px] h-full w-0.5",
            state === "done" ? "bg-primary" : "bg-border",
          )}
        />
      )}
      <div className="relative">
        <Dot state={state} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-start gap-2">
          <div className="min-w-0 flex-1">
            <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground tabular-nums">
              <span>{section.index}</span>
              <span className="rounded border border-border px-1 font-semibold tracking-wide uppercase">
                {KIND_LABEL[section.kind]()}
              </span>
              <span className="sr-only">{STATE_LABEL[state]()}</span>
            </p>
            <p
              lang={language}
              className={cn(
                "text-sm leading-tight",
                state === "active" ? "font-bold" : "font-semibold",
                state === "done" && "text-muted-foreground",
              )}
            >
              {section.title}
            </p>
            {state === "active" && (
              <p lang={language} className="mt-1 text-xs leading-snug text-muted-foreground">
                {section.goal}
              </p>
            )}
          </div>
          {action && (
            <button
              type="button"
              disabled={streaming}
              onClick={() => onAction(action.text)}
              className="shrink-0 rounded-md border border-border bg-card px-2 py-1 text-xs font-semibold transition-colors hover:bg-secondary disabled:opacity-50"
            >
              {action.label}
            </button>
          )}
        </div>
      </div>
    </li>
  );
}

export const ChapterMapSheet = memo(function ChapterMapSheet({
  open,
  onOpenChange,
  chapter,
  progress,
  streaming,
  onSend,
  onReset,
}: ChapterMapProps) {
  const language = useCourseLanguage();
  const [confirmReset, setConfirmReset] = useState(false);
  const { segments, doneCount, total } = chapterModel(chapter, progress);

  const act = (text: string) => {
    onSend(text);
    onOpenChange(false);
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="left" className="flex w-full flex-col gap-0 p-0 sm:max-w-sm">
        <SheetHeader className="border-b border-border px-5 py-4 text-left">
          <SheetTitle lang={language} className="text-base">
            {chapter.title}
          </SheetTitle>
          <SheetDescription>{m.lesson_map_progress({ done: doneCount, total })}</SheetDescription>
        </SheetHeader>

        <ol className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {chapter.sections.map((section, i) => (
            <Row
              key={section.id}
              section={section}
              state={segments[i] ?? "locked"}
              last={i === total - 1}
              streaming={streaming}
              onAction={act}
            />
          ))}
        </ol>

        <div className="border-t border-border px-5 py-3">
          <button
            type="button"
            onClick={() => setConfirmReset(true)}
            className="text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
          >
            {m.lesson_reset()}
          </button>
        </div>

        <AlertDialog open={confirmReset} onOpenChange={setConfirmReset}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{m.lesson_reset_title()}</AlertDialogTitle>
              <AlertDialogDescription>{m.lesson_reset_description()}</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>{m.common_cancel()}</AlertDialogCancel>
              <AlertDialogAction
                onClick={() => {
                  setConfirmReset(false);
                  onOpenChange(false);
                  onReset();
                }}
              >
                {m.lesson_reset_confirm()}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </SheetContent>
    </Sheet>
  );
});
