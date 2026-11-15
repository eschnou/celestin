/**
 * Révision (spec 020): a course-scoped conversation over the chapters the student chose.
 * The same stored-conversation machinery as a discussion (007, 018): the server keeps the
 * transcript, the page reads it once and restores it through `sessionFromEntries`, and a
 * turn posts the message. What is new is the record: the student's own self-assessment of
 * each question, per section, which the « Bilan » reads.
 */

import { queryOptions } from "@tanstack/react-query";

import { getJson, sendJson, streamEvents } from "@/lib/tutor/client";
import type {
  Revision,
  RevisionChapter,
  RevisionMark,
  RevisionOutcome,
  RevisionResult,
  RevisionView,
  TutorEvent,
} from "@/lib/tutor/types";

export const REVISION_TURN_URL = "/api/revision/turn";

export const revisionUrl = (courseId: string) =>
  `/api/courses/${encodeURIComponent(courseId)}/revision`;

/** The live révision (or null), every chapter of the course with its path, and the latest
 *  self-assessment per section. Read once when the page mounts, like the discussion's
 *  `conversationQuery`: the live transcript belongs to the session hook from then on. */
export const revisionQuery = (courseId: string) =>
  queryOptions({
    queryKey: ["revision", courseId],
    queryFn: () => getJson<RevisionView>(revisionUrl(courseId)),
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    gcTime: 0,
    retry: false,
  });

/** Starts a révision on these chapters, closing the live one (`replaced`). The server
 *  refuses an empty or too large selection, a chapter not ready, or a spent daily quota.
 *  It answers with the read the `GET` gives (the new révision, the chapters, the results the
 *  closed one noted), so the page sets it as the query's data and reads nothing again. */
export async function startRevision(
  courseId: string,
  chapterIds: string[],
): Promise<RevisionView & { revision: Revision }> {
  const response = await sendJson(revisionUrl(courseId), { chapter_ids: chapterIds });
  return (await response.json()) as RevisionView & { revision: Revision };
}

/** The turn transport for `useTutorSession`: the message, never the transcript. */
export function revisionTransport(scope: { courseId: string; revisionId: string }) {
  return (input: { message: string | null }, signal: AbortSignal): AsyncGenerator<TutorEvent> =>
    streamEvents(
      REVISION_TURN_URL,
      { course_id: scope.courseId, revision_id: scope.revisionId, message: input.message },
      signal,
    );
}

/**
 * The chapters the chooser ticks first: only `wanted` when it names a ready chapter (the
 * chapter bar's link), else the ready chapters with some progress (done or skipped), else
 * every ready chapter.
 */
export function preselected(chapters: RevisionChapter[], wanted?: string): string[] {
  const ready = chapters.filter((c) => c.ready);
  if (wanted && ready.some((c) => c.id === wanted)) return [wanted];
  const worked = ready.filter((c) => c.done_count + c.skipped_count > 0);
  return (worked.length > 0 ? worked : ready).map((c) => c.id);
}

export type Assessment = { outcome: RevisionOutcome; at: string };

export const resultKey = (chapterId: string, sectionId: string) => `${chapterId}/${sectionId}`;

/**
 * The latest self-assessment per section, as the « Bilan » shows it: the server's read,
 * then what was noted on this page since (in order, so the last one counts), dated `now`.
 * Results restored with the transcript are already in the server's read, with their date.
 */
export function latestResults(
  stored: RevisionResult[],
  noted: RevisionMark[],
  now: string,
): Map<string, Assessment> {
  const latest = new Map<string, Assessment>();
  for (const r of stored) latest.set(resultKey(r.chapter_id, r.section_id), r);
  for (const r of noted)
    latest.set(resultKey(r.chapter_id, r.section_id), { outcome: r.outcome, at: now });
  return latest;
}
