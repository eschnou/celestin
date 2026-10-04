/** Courses, chapters, their content and the authoring actions (005 design 3.16, 006 design 3.9). */

import type { CourseLanguage } from "@/lib/course-language";
import { queryOptions } from "@tanstack/react-query";
import { ApiError, getJson, sendForm, sendJson } from "./client";
import type {
  ChapterContent,
  ChapterRow,
  CourseDetail,
  CoursesResponse,
  CourseSummary,
  CurriculumIn,
  SubjectId,
  SubjectsResponse,
} from "./types";

export const COURSES_URL = "/api/courses";

/** A 4xx is an answer (not found, not ready, not signed in); only a 5xx or a network error is retried once. */
export const retryOnce = (count: number, error: unknown): boolean =>
  count < 1 && !(error instanceof ApiError && error.status < 500);

/** The loader has just fetched: the component's own query must not refetch on mount. */
const JUST_LOADED_MS = 5_000;

/** While a chapter is being prepared the course page asks again, no faster (005 NFR 4.2.4). */
export const GENERATING_POLL_MS = 3_000;

const course = (courseId: string) => `${COURSES_URL}/${encodeURIComponent(courseId)}`;
const chapter = (courseId: string, chapterId: string) =>
  `${course(courseId)}/chapters/${encodeURIComponent(chapterId)}`;

export const subjectsQuery = queryOptions({
  queryKey: ["subjects"],
  queryFn: () => getJson<SubjectsResponse>("/api/subjects"),
  staleTime: Infinity,
  retry: retryOnce,
});

export const coursesQuery = queryOptions({
  queryKey: ["courses"],
  queryFn: () => getJson<CoursesResponse>(COURSES_URL),
  staleTime: JUST_LOADED_MS,
  retry: retryOnce,
});

export function pollWhileGenerating(data: { chapters: ChapterRow[] } | undefined): number | false {
  return data?.chapters.some((c) => c.authoring_state === "generating")
    ? GENERATING_POLL_MS
    : false;
}

export const courseQuery = (courseId: string) =>
  queryOptions({
    queryKey: ["courses", courseId],
    queryFn: () => getJson<CourseDetail>(course(courseId)),
    staleTime: JUST_LOADED_MS,
    retry: retryOnce,
    refetchInterval: (query) => pollWhileGenerating(query.state.data),
  });

export const chapterContentQuery = (courseId: string, chapterId: string) =>
  queryOptions({
    queryKey: ["chapter-content", courseId, chapterId],
    queryFn: () => getJson<ChapterContent>(`${chapter(courseId, chapterId)}/content`),
    staleTime: 0,
    retry: retryOnce,
    // No polling here: the content page follows the light course query while a
    // preparation runs, and refetches this once it ends.
  });

export async function createCourse(
  name: string,
  subject: SubjectId,
  language: CourseLanguage,
): Promise<CourseSummary> {
  return (await (await sendJson(COURSES_URL, { name, subject, language })).json()) as CourseSummary;
}

export async function renameCourse(courseId: string, name: string): Promise<CourseSummary> {
  return (await (
    await sendJson(course(courseId), { name }, { method: "PATCH" })
  ).json()) as CourseSummary;
}

export async function deleteCourse(courseId: string): Promise<void> {
  await sendJson(course(courseId), undefined, { method: "DELETE" });
}

/** The files under one field, in page order: one PDF, or photos (006 R1). */
function documentForm(files: File[]): FormData {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  return form;
}

export async function addChapter(courseId: string, files: File[]): Promise<ChapterRow> {
  return (await (
    await sendForm(`${course(courseId)}/chapters`, documentForm(files))
  ).json()) as ChapterRow;
}

export async function replaceDocument(
  courseId: string,
  chapterId: string,
  files: File[],
): Promise<ChapterRow> {
  return (await (
    await sendForm(`${chapter(courseId, chapterId)}/document`, documentForm(files), "PUT")
  ).json()) as ChapterRow;
}

export async function retryChapter(courseId: string, chapterId: string): Promise<ChapterRow> {
  return (await (await sendJson(`${chapter(courseId, chapterId)}/retry`)).json()) as ChapterRow;
}

export async function deleteChapter(courseId: string, chapterId: string): Promise<void> {
  await sendJson(chapter(courseId, chapterId), undefined, { method: "DELETE" });
}

export async function resetChapter(courseId: string, chapterId: string): Promise<void> {
  await sendJson(`${chapter(courseId, chapterId)}/progress`, undefined, { method: "DELETE" });
}

export async function savePack(
  courseId: string,
  chapterId: string,
  version: number,
  pack: string,
): Promise<ChapterContent> {
  return (await (
    await sendJson(`${chapter(courseId, chapterId)}/pack`, { version, pack }, { method: "PUT" })
  ).json()) as ChapterContent;
}

export async function saveCurriculum(
  courseId: string,
  chapterId: string,
  version: number,
  curriculum: CurriculumIn,
): Promise<ChapterContent> {
  return (await (
    await sendJson(
      `${chapter(courseId, chapterId)}/curriculum`,
      { version, curriculum },
      { method: "PUT" },
    )
  ).json()) as ChapterContent;
}

export async function saveSource(
  courseId: string,
  chapterId: string,
  sourceText: string,
): Promise<ChapterRow> {
  return (await (
    await sendJson(
      `${chapter(courseId, chapterId)}/source`,
      { source_text: sourceText },
      { method: "PUT" },
    )
  ).json()) as ChapterRow;
}
