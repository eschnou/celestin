/**
 * The chapter map (002 design 3.11): the full path, on demand.
 *
 * Every row is actionable (spec 019: no section is locked); the backend decides what each
 * action does. A done row offers a review, a skipped one a start, every other one a start
 * (« Reprendre » when it has a stored séance) and « Passer », the active one « Passer »:
 * all ordinary learner messages, in the course's language. The proposed next section keeps
 * the primary button. A row whose section has stored boards also offers to reread them in
 * the cahier (018), which is a link, not a message: no model call.
 */

import { Link } from "@tanstack/react-router";
import { memo, useState } from "react";
import { Check, ChevronsRight } from "lucide-react";
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
import { SectionLabel, SectionRing } from "@/components/celestin/section-label";
import { useCourseLanguage } from "@/lib/course-language";
import { cn } from "@/lib/utils";
import { m } from "@/paraglide/messages";
import { chapterModel } from "@/lib/tutor/chapter-model";
import { STATE_LABEL } from "@/lib/tutor/labels";
import { useLearnerSentences, type LearnerSentences } from "@/lib/tutor/prompts";
import type { ChapterView, Progress, SectionOverview, SectionState } from "@/lib/tutor/types";

type ChapterMapProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  chapter: Pick<ChapterView, "id" | "course_id" | "title" | "sections">;
  progress: Progress;
  /** A turn is in flight: actions wait. */
  streaming: boolean;
  onSend: (text: string) => void;
  onReset: () => void;
  /** The sections the cahier has boards for (018): their rows offer « Relire ». */
  rereadable: ReadonlySet<string>;
  /** The sections with a stored séance (spec 019): a start there reads « Reprendre ». */
  begun: ReadonlySet<string>;
};

const ACTION =
  "shrink-0 rounded-md border px-2 py-1 text-xs font-semibold transition-colors disabled:opacity-50";
const SECONDARY = `${ACTION} border-border bg-card hover:bg-secondary`;
const PRIMARY = `${ACTION} border-primary bg-primary text-primary-foreground hover:bg-primary/90`;

function Dot({ state }: { state: SectionState }) {
  if (state === "done") {
    return (
      <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-success text-success-foreground">
        <Check className="size-3" strokeWidth={3} />
      </span>
    );
  }
  if (state === "skipped") {
    return (
      <span className="flex size-5 shrink-0 items-center justify-center rounded-full border border-dashed border-muted-foreground/60 text-muted-foreground">
        <ChevronsRight className="size-3" />
      </span>
    );
  }
  return <SectionRing state={state} className="size-5" />;
}

type Action = { key: string; label: string; text: string; primary?: boolean; title?: string };

/** What a row offers, by state (spec 019 « Interface »), in the order shown. */
function actions(
  section: SectionOverview,
  state: SectionState,
  begun: boolean,
  said: LearnerSentences,
): Action[] {
  const start = begun
    ? { key: "start", label: m.chapter_action_resume(), text: said.resume(section.title) }
    : { key: "start", label: m.chapter_action_start(), text: said.start(section.title) };
  const skip = {
    key: "skip",
    label: m.chapter_action_skip(),
    text: said.skip(section.title),
    title: m.chapter_action_skip_title(),
  };
  switch (state) {
    case "done":
      return [
        { key: "review", label: m.chapter_action_review(), text: said.review(section.title) },
      ];
    case "active":
      return [skip];
    case "skipped":
      return [start];
    case "available":
      return [{ ...start, primary: true }, skip];
    case "open":
      return [start, skip];
  }
}

function Row({
  section,
  state,
  last,
  streaming,
  onAction,
  notebook,
  reread,
  begun,
}: {
  section: SectionOverview;
  state: SectionState;
  last: boolean;
  streaming: boolean;
  onAction: (text: string) => void;
  /** Where the chapter's cahier is, and whether this section has boards to reread there. */
  notebook: { courseId: string; chapterId: string };
  reread: boolean;
  begun: boolean;
}) {
  const language = useCourseLanguage();
  const said = useLearnerSentences();
  return (
    <li className="relative flex gap-3 pb-4" data-state={state}>
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
        <SectionLabel section={section} className="text-[11px]">
          {state === "skipped" ? (
            <span className="rounded bg-secondary px-1 text-[11px] font-semibold text-muted-foreground">
              {STATE_LABEL.skipped()}
            </span>
          ) : (
            <span className="sr-only">{STATE_LABEL[state]()}</span>
          )}
        </SectionLabel>
        <p
          lang={language}
          className={cn(
            "text-sm leading-tight",
            state === "active" ? "font-bold" : "font-semibold",
            (state === "done" || state === "skipped") && "text-muted-foreground",
          )}
        >
          {section.title}
        </p>
        {state === "active" && (
          <p lang={language} className="mt-1 text-xs leading-snug text-muted-foreground">
            {section.goal}
          </p>
        )}
        {/* Under the title, wrapping: two or three actions never squeeze it on a phone. */}
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {reread && (
            <Link
              to="/courses/$courseId/chapters/$chapterId/notebook"
              params={notebook}
              hash={section.id}
              title={m.chapter_action_reread_title()}
              className={SECONDARY}
            >
              {m.chapter_action_reread()}
            </Link>
          )}
          {actions(section, state, begun, said).map((action) => (
            <button
              key={action.key}
              type="button"
              disabled={streaming}
              onClick={() => onAction(action.text)}
              title={action.title}
              className={action.primary ? PRIMARY : SECONDARY}
            >
              {action.label}
            </button>
          ))}
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
  rereadable,
  begun,
}: ChapterMapProps) {
  const language = useCourseLanguage();
  const [confirmReset, setConfirmReset] = useState(false);
  const { segments, doneCount, skippedCount, total } = chapterModel(chapter, progress);
  const notebook = { courseId: chapter.course_id, chapterId: chapter.id };

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
          <SheetDescription>
            {m.lesson_map_progress({ done: doneCount, total })}
            {skippedCount > 0 && ` · ${m.chapter_count_skipped({ count: skippedCount })}`}
          </SheetDescription>
        </SheetHeader>

        <ol className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {chapter.sections.map((section, i) => (
            <Row
              key={section.id}
              section={section}
              state={segments[i] ?? "open"}
              last={i === total - 1}
              streaming={streaming}
              onAction={act}
              notebook={notebook}
              reread={rereadable.has(section.id)}
              begun={begun.has(section.id)}
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
