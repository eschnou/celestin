import type { ChapterRow } from "@/lib/tutor/types";

export type Featured = { row: ChapterRow; resuming: boolean };

/** The chapter to offer: the one worked on last if it is not finished, else one in progress, else the first
 *  not started. None when everything is done (or nothing is ready yet). */
export function featuredChapter(rows: ChapterRow[]): Featured | null {
  const ready = rows.filter((row) => row.ready);
  const last = ready.find((row) => row.last && row.state !== "done");
  if (last) return { row: last, resuming: last.state === "in_progress" };
  const started = ready.find((row) => row.state === "in_progress");
  if (started) return { row: started, resuming: true };
  const next = ready.find((row) => row.state === "not_started");
  return next ? { row: next, resuming: false } : null;
}
