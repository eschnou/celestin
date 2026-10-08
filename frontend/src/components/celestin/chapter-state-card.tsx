/** What the lesson URL shows for a chapter that has no content yet (005 R4.4). */

import { Link } from "@tanstack/react-router";
import type { ChapterRow } from "@/lib/tutor/types";
import { m } from "@/paraglide/messages";
import { FailedAction, isSlow, preparingDetail } from "./chapter-row";
import { primary } from "./styles";

export function ChapterStateCard({
  courseId,
  row,
  onRetry,
  error,
}: {
  courseId: string;
  row: ChapterRow | undefined;
  onRetry: () => void;
  error: string | null;
}) {
  const failed = row?.authoring_state === "failed";
  const progress = row ? preparingDetail(row) : null;
  const body = failed
    ? row?.authoring_message
    : row?.authoring_stage === "transcription"
      ? m.chapter_card_reading_hint({ progress: progress ?? "" })
      : progress
        ? `${progress} ${m.chapter_card_preparing_hint()}`
        : m.chapter_card_preparing_hint();
  return (
    <div className="mt-6 rounded-xl border border-border bg-background p-6 text-center shadow-sheet">
      <h1 className="text-lg font-bold">
        {failed ? m.chapter_card_failed_title() : m.chapter_card_preparing_title()}
      </h1>
      <div className="mt-2 text-sm text-muted-foreground" aria-live="polite">
        <p>{body}</p>
        {!failed && row && isSlow(row) && <p className="mt-1">{m.chapter_slow()}</p>}
      </div>
      {error && (
        <p role="alert" className="mt-2 text-sm text-destructive">
          {error}
        </p>
      )}
      <div className="mt-4 flex justify-center gap-3">
        {row && (
          <FailedAction courseId={courseId} row={row} onRetry={onRetry} className={primary} />
        )}
        <Link
          to="/courses/$courseId"
          params={{ courseId }}
          className="inline-flex items-center text-sm font-semibold text-primary hover:underline"
        >
          {m.chapter_card_back()}
        </Link>
      </div>
    </div>
  );
}
