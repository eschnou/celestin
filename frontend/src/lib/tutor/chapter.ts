/** The chapter overview plus the student's progress (005 design 3.16). */

import { queryOptions } from "@tanstack/react-query";
import { getJson } from "./client";
import { retryOnce } from "./courses";
import type { ChapterView } from "./types";

export const chapterUrl = (courseId: string, chapterId: string) =>
  `/api/courses/${encodeURIComponent(courseId)}/chapters/${encodeURIComponent(chapterId)}`;

export const chapterQuery = (courseId: string, chapterId: string) =>
  queryOptions({
    queryKey: ["chapter", courseId, chapterId],
    queryFn: () => getJson<ChapterView>(chapterUrl(courseId, chapterId)),
    // Progress travels with it: fresh on every entry (the loader fetches, the
    // component reads), never kept once the student leaves. The lesson does not start
    // from this one's progress: it reads its own with the séance (`lessonStartQuery`).
    staleTime: 5_000,
    gcTime: 0,
    retry: retryOnce,
  });
