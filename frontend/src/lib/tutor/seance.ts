/**
 * Stored séances (spec 018): the parcours transcript lives on the server, one row per
 * stretch of work on a section. The lesson reads the live one to resume where it stopped
 * (D6); the cahier reads every stored one to reread the boards (D8).
 */

import { queryOptions } from "@tanstack/react-query";

import { chapterUrl } from "./chapter";
import { getJson } from "./client";
import {
  progressFrom,
  type Notebook,
  type Progress,
  type Seance,
  type WireProgress,
} from "./types";

/** Where the browser reports a parcours turn the server did not see to its end (018 D7): a
 *  spoken one (the same deviation as 007 D1), or one the learner stopped. */
export const SEANCE_REPORT_URL = "/api/seance/report";

export const seanceUrl = (courseId: string, chapterId: string) =>
  `${chapterUrl(courseId, chapterId)}/seance`;
export const notebookUrl = (courseId: string, chapterId: string) =>
  `${chapterUrl(courseId, chapterId)}/notebook`;

/** `GET …/seance`, what the lesson starts from: the live séance and, read in the same
 *  handler, the progress and the stored card count per section, so they cannot come from
 *  different moments (D6). */
export type LessonStart = {
  seance: Seance | null;
  progress: Progress;
  seances: Record<string, { cards: number }>;
};

/**
 * The live séance and the chapter's progress, read together when the lesson mounts.
 *
 * The lesson starts from this progress, not the chapter view's, which is cached for a few
 * seconds: a lesson remounted from it could restore a fresh séance over a stale progress.
 * Read once per mount (the session owns the transcript from then on, so a refetch would
 * fetch the whole thing to discard it) and dropped on unmount, like the discussion's
 * `conversationQuery`. The chapter route's loader starts it beside `chapterQuery`.
 */
export const lessonStartQuery = (courseId: string, chapterId: string) =>
  queryOptions({
    queryKey: ["seance", courseId, chapterId],
    queryFn: async (): Promise<LessonStart> => {
      const start = await getJson<Omit<LessonStart, "progress"> & { progress: WireProgress }>(
        seanceUrl(courseId, chapterId),
      );
      return { ...start, progress: progressFrom(start.progress) };
    },
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    gcTime: 0,
    retry: false,
  });

/** The cahier: every stored séance of the chapter at its current content version, per
 *  section in path order. Read on every visit (the loader fetches, the page reads: a
 *  lesson in between adds to it), never kept once the student leaves. */
export const notebookQuery = (courseId: string, chapterId: string) =>
  queryOptions({
    queryKey: ["notebook", courseId, chapterId],
    queryFn: () => getJson<Notebook>(notebookUrl(courseId, chapterId)),
    staleTime: 5_000,
    gcTime: 0,
    retry: false,
  });
