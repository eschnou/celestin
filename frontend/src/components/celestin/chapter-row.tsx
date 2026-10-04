/** One chapter on the course page: its preparation or progress state, and what can be done (005 R4.1). */

import { Link } from "@tanstack/react-router";
import { Check, Ellipsis, FileText, Trash2 } from "lucide-react";
import { useState } from "react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useCourseLanguage } from "@/lib/course-language";
import type { ChapterRow as Row, ChapterState } from "@/lib/tutor/types";
import { cn } from "@/lib/utils";
import { m } from "@/paraglide/messages";
import { ConfirmDialog } from "./confirm-dialog";
import { ProgressBar } from "./progress-bar";
import { primary, secondary } from "./styles";

/** Message functions, not strings: the language is read when the label is shown. */
const STATE_LABEL: Record<ChapterState, () => string> = {
  not_started: m.chapter_state_not_started,
  in_progress: m.chapter_state_in_progress,
  done: m.chapter_state_done,
};

/** « Reprendre » belongs to the chapter worked on last; other chapters in progress continue. */
export function actionLabel(row: Row): string {
  if (row.state === "done") return m.chapter_action_review();
  if (row.state === "not_started") return m.chapter_action_start();
  return row.last ? m.chapter_action_resume() : m.chapter_action_continue();
}

export function chapterTitle(row: Row): string {
  return row.title ?? m.chapter_untitled({ position: row.position });
}

/** How a chapter is named outside its own list: « Chapitre 2 — Les suites ». The number
 *  is its position in the course, never something the authoring model wrote (006). */
export function chapterName(chapter: { position: number; title: string | null }): string {
  return chapter.title
    ? m.chapter_name({ position: chapter.position, title: chapter.title })
    : m.chapter_untitled({ position: chapter.position });
}

/** What a running preparation is doing: reading pages, then preparing (006 R3.1). */
export function preparingLabel(row: Row): string {
  return row.authoring_stage === "transcription"
    ? m.chapter_reading_pages({ done: row.pages_done, total: row.page_count })
    : m.chapter_preparing();
}

/** A run that failed before its transcription was stored cannot be retried: the
 *  document is not kept, so the student drops it again (006 R3.4). */
export function needsDocument(row: Row): boolean {
  return row.authoring_state === "failed" && row.authoring_stage === "transcription";
}

/** After a failure: « Réessayer », or « Redéposer le document » when the pages were never read. */
export function FailedAction({
  courseId,
  row,
  onRetry,
  disabled = false,
  className,
}: {
  courseId: string;
  row: Row;
  onRetry: () => void;
  disabled?: boolean;
  className: string;
}) {
  if (row.authoring_state !== "failed") return null;
  if (needsDocument(row))
    return (
      <Link
        to="/courses/$courseId/chapters/$chapterId/content"
        params={{ courseId, chapterId: row.id }}
        search={{ tab: "source" }}
        className={className}
      >
        {m.chapter_redeposit()}
      </Link>
    );
  return (
    <button type="button" onClick={onRetry} disabled={disabled} className={className}>
      {m.error_retry()}
    </button>
  );
}

/** The section she is on, counted from 1: the one after those done, never past the last. */
export function currentSection(row: Row): number {
  return Math.min(row.done_count + 1, Math.max(row.section_count, 1));
}

/** « Section 3 sur 9 », « 9 sections »: how far along, in words. */
export function progressText(row: Row): string {
  return row.state === "in_progress"
    ? m.chapter_progress_section({ current: currentSection(row), total: row.section_count })
    : m.chapter_status_sections({ count: row.section_count });
}

export function ChapterRowItem({
  courseId,
  row,
  index,
  onRetry,
  onDelete,
  busy,
}: {
  courseId: string;
  row: Row;
  index: number;
  onRetry: () => void;
  onDelete: () => void;
  busy: boolean;
}) {
  const language = useCourseLanguage();
  const title = chapterTitle(row);
  const [confirming, setConfirming] = useState(false);
  const done = row.ready && row.state === "done";
  return (
    <li
      aria-current={row.last ? "true" : undefined}
      className={cn(
        "rounded-2xl border bg-background p-4 shadow-sheet sm:p-5",
        row.last ? "border-primary" : "border-border",
      )}
    >
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "mt-0.5 grid size-8 shrink-0 place-items-center rounded-full text-sm font-bold",
            done ? "bg-success text-success-foreground" : "bg-secondary text-muted-foreground",
          )}
        >
          {done ? <Check className="size-4" strokeWidth={3} aria-hidden /> : index}
        </span>
        <div className="min-w-0 flex-1">
          {row.last && (
            <p className="text-[11px] font-bold tracking-wide text-primary uppercase">
              {m.chapter_status_here()}
            </p>
          )}
          {/* The chapter's own title is course text; the placeholder for an untitled one is ours. */}
          <p lang={row.title ? language : undefined} className="text-base font-semibold">
            {title}
          </p>
          <p className="mt-0.5 text-sm text-muted-foreground" aria-live="polite">
            <Status row={row} />
          </p>
          {row.authoring_state === "failed" && row.authoring_message && (
            <p className="mt-1 text-sm text-destructive">{row.authoring_message}</p>
          )}
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger
            aria-label={m.chapter_menu({ title })}
            className="-mt-1 -mr-1 inline-flex size-10 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          >
            <Ellipsis className="size-5" aria-hidden />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem asChild>
              <Link
                to="/courses/$courseId/chapters/$chapterId/content"
                params={{ courseId, chapterId: row.id }}
              >
                <FileText /> {m.chapter_content()}
              </Link>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              disabled={busy}
              onSelect={() => setConfirming(true)}
              className="text-destructive focus:text-destructive"
            >
              <Trash2 /> {m.chapter_delete()}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      {row.ready && row.state !== "not_started" && (
        <ProgressBar
          done={row.done_count}
          total={row.section_count}
          label={progressText(row)}
          tone={done ? "success" : "primary"}
          className="mt-3"
        />
      )}
      {(row.ready || row.authoring_state === "failed") && (
        <div className="mt-4 flex flex-wrap gap-2">
          {row.ready && (
            <Link
              to="/courses/$courseId/chapters/$chapterId"
              params={{ courseId, chapterId: row.id }}
              className={cn(done ? secondary : primary, "min-h-10 flex-1 px-4 sm:flex-none")}
            >
              {actionLabel(row)}
            </Link>
          )}
          {/* The light door (007 R1.1): secondary to the parcours, which stays the
              way progress is made. */}
          {row.ready && (
            <Link
              to="/courses/$courseId/chapters/$chapterId/discussion"
              params={{ courseId, chapterId: row.id }}
              className={cn(secondary, "min-h-10 px-4")}
            >
              {m.chapter_discuss()}
            </Link>
          )}
          <FailedAction
            courseId={courseId}
            row={row}
            onRetry={onRetry}
            disabled={busy}
            className={cn(row.ready ? secondary : primary, "min-h-10 px-4")}
          />
        </div>
      )}
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={m.chapter_delete_title({ title })}
        description={m.chapter_delete_description()}
        confirm={m.chapter_delete_confirm()}
        onConfirm={onDelete}
        destructive
      />
    </li>
  );
}

function Status({ row }: { row: Row }) {
  if (!row.ready) {
    return row.authoring_state === "failed" ? (
      <Badge tone="bg-destructive/15 text-destructive">{m.chapter_status_failed()}</Badge>
    ) : (
      <Badge tone="bg-secondary text-muted-foreground">{preparingLabel(row)}</Badge>
    );
  }
  const tone =
    row.state === "done"
      ? "bg-success/15 text-success"
      : row.state === "in_progress"
        ? "bg-primary/15 text-primary"
        : "bg-secondary text-muted-foreground";
  return (
    <>
      <Badge tone={tone}>{STATE_LABEL[row.state]()}</Badge>
      {" · "}
      {progressText(row)}
      {row.authoring_state === "generating" &&
        ` · ${m.chapter_status_new_version({ status: preparingLabel(row).toLowerCase() })}`}
      {row.authoring_state === "failed" && ` · ${m.chapter_status_new_version_failed()}`}
    </>
  );
}

function Badge({ tone, children }: { tone: string; children: React.ReactNode }) {
  return (
    <span className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${tone}`}>{children}</span>
  );
}
