/** The chapter overview plus the student's progress (005 design 3.16). */

import { queryOptions } from "@tanstack/react-query";
import { getJson } from "./client";
import { retryOnce } from "./courses";
import type { ChapterView } from "./types";

export const chapterQuery = (courseId: string, chapterId: string) =>
  queryOptions({
    queryKey: ["chapter", courseId, chapterId],
    queryFn: () =>
      getJson<ChapterView>(
        `/api/courses/${encodeURIComponent(courseId)}/chapters/${encodeURIComponent(chapterId)}`,
      ),
    // Progress travels with it: fresh on every entry (the loader fetches, the
    // component reads), never kept once the student leaves.
    staleTime: 5_000,
    gcTime: 0,
    retry: retryOnce,
  });
