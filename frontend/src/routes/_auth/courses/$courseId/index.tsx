import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, getRouteApi, Link, useNavigate } from "@tanstack/react-router";
import { Plus } from "lucide-react";
import { useState } from "react";
import { AddChapterForm } from "@/components/celestin/add-chapter-form";
import { AuthPage } from "@/components/celestin/app-bar";
import { ChapterRowItem } from "@/components/celestin/chapter-row";
import { CourseHeader } from "@/components/celestin/course-header";
import { ResumeCard } from "@/components/celestin/course-resume";
import { NotFoundCard } from "@/components/celestin/not-found";
import { CourseLanguageProvider } from "@/lib/course-language";
import { apiMessage, apiStatus } from "@/lib/tutor/client";
import { featuredChapter } from "@/lib/tutor/featured-chapter";
import {
  addChapter,
  courseQuery,
  deleteChapter,
  deleteCourse,
  renameCourse,
  retryChapter,
  subjectsQuery,
} from "@/lib/tutor/courses";
import { m } from "@/paraglide/messages";

const authRoute = getRouteApi("/_auth");

export const Route = createFileRoute("/_auth/courses/$courseId/")({
  head: () => ({ meta: [{ title: m.course_head_title() }] }),
  loader: ({ context, params }) =>
    context.queryClient.ensureQueryData(courseQuery(params.courseId)).catch(() => null),
  component: CoursePage,
});

function CoursePage() {
  const { user } = authRoute.useRouteContext();
  const { courseId } = Route.useParams();
  const course = useQuery(courseQuery(courseId));
  const subjects = useQuery(subjectsQuery);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [adding, setAdding] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["courses"] });
  const fail = (err: unknown) => setActionError(apiMessage(err, m.course_action_failed()));
  const retry = useMutation({
    mutationFn: (chapterId: string) => retryChapter(courseId, chapterId),
    onMutate: () => setActionError(null),
    onSuccess: refresh,
    onError: fail,
  });
  const remove = useMutation({
    mutationFn: (chapterId: string) => deleteChapter(courseId, chapterId),
    onMutate: () => setActionError(null),
    onSuccess: refresh,
    onError: fail,
  });
  const removeCourse = useMutation({
    mutationFn: () => deleteCourse(courseId),
    onSuccess: async () => {
      queryClient.removeQueries({ queryKey: courseQuery(courseId).queryKey });
      await refresh();
      await navigate({ to: "/courses" });
    },
    onError: fail,
  });

  const data = course.data;
  const featured = data && data.chapters.length >= 2 ? featuredChapter(data.chapters) : null;
  return (
    <AuthPage user={user}>
      <Link to="/courses" className="text-sm text-muted-foreground hover:underline">
        {m.course_back()}
      </Link>
      {course.isError && !data && <NotFoundCard status={apiStatus(course.error)} />}
      {data && (
        <CourseLanguageProvider language={data.language}>
          <CourseHeader
            name={data.name}
            subject={data.subject}
            subjectLabel={data.subject_label}
            language={data.language}
            chaptersTotal={data.chapters_total}
            chaptersDone={data.chapters_done}
            onRename={async (name) => {
              await renameCourse(courseId, name);
              await refresh();
            }}
            onDelete={() => removeCourse.mutate()}
          />
          {actionError && (
            <p role="alert" className="mt-3 text-sm text-destructive">
              {actionError}
            </p>
          )}
          {featured && <ResumeCard courseId={courseId} featured={featured} />}
          {data.chapters.length === 0 && !adding && (
            <p className="mt-5 text-sm text-muted-foreground">{m.course_empty()}</p>
          )}
          {data.chapters.length > 0 && (
            <h2 className="mt-6 text-sm font-bold tracking-wide text-muted-foreground uppercase">
              {m.course_chapters_heading()}
            </h2>
          )}
          <ol className="mt-3 space-y-3">
            {data.chapters.map((row, index) => (
              <ChapterRowItem
                key={row.id}
                courseId={courseId}
                row={row}
                index={index + 1}
                busy={retry.isPending || remove.isPending}
                onRetry={() => retry.mutate(row.id)}
                onDelete={() => remove.mutate(row.id)}
              />
            ))}
          </ol>
          <div className="mt-3">
            {adding && subjects.data ? (
              <AddChapterForm
                limits={subjects.data.limits}
                onAdd={async (files) => {
                  await addChapter(courseId, files);
                  setAdding(false);
                  await refresh();
                }}
                onCancel={() => setAdding(false)}
              />
            ) : (
              <button
                type="button"
                onClick={() => setAdding(true)}
                aria-label={m.course_add_chapter()}
                className="flex w-full items-center gap-3 rounded-2xl border-2 border-dashed border-border p-4 text-left transition-colors hover:border-primary hover:bg-primary/5 sm:p-5"
              >
                <span className="grid size-10 shrink-0 place-items-center rounded-full bg-primary/10 text-primary">
                  <Plus className="size-5" aria-hidden />
                </span>
                <span>
                  <span className="block font-semibold">{m.course_add_chapter()}</span>
                  <span className="block text-sm text-muted-foreground">{m.course_add_hint()}</span>
                </span>
              </button>
            )}
          </div>
        </CourseLanguageProvider>
      )}
    </AuthPage>
  );
}
