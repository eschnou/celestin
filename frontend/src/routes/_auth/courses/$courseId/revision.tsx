import { useQuery } from "@tanstack/react-query";
import { createFileRoute, getRouteApi } from "@tanstack/react-router";

import { AuthPage } from "@/components/celestin/app-bar";
import { NotFoundCard } from "@/components/celestin/not-found";
import { RevisionBar } from "@/components/celestin/revision/revision-bar";
import { RevisionPanel } from "@/components/celestin/revision/revision-panel";
import { LessonFrame } from "@/components/celestin/tutor-board-split";
import { CourseLanguageProvider } from "@/lib/course-language";
import { apiStatus } from "@/lib/tutor/client";
import { courseQuery } from "@/lib/tutor/courses";
import { m } from "@/paraglide/messages";

const authRoute = getRouteApi("/_auth");

/** Révision (spec 020): the whole course, the chapters the student chose. `?chapter=` is the
 *  chapter she came from, ticked alone in the chooser. */
export const Route = createFileRoute("/_auth/courses/$courseId/revision")({
  head: () => ({ meta: [{ title: m.revision_head_title() }] }),
  validateSearch: (search: Record<string, unknown>): { chapter?: string } =>
    typeof search["chapter"] === "string" && search["chapter"]
      ? { chapter: search["chapter"] }
      : {},
  // The course gives the name, the subject and the language. The révision (its chapters,
  // its transcript, the results) is read by the panel, which has its loading state: that read
  // also closes a changed révision, so it happens once, and a prefetch held by no one
  // (`gcTime: 0`) could be dropped before the panel subscribes and read a second time.
  loader: ({ context, params }) =>
    context.queryClient.ensureQueryData(courseQuery(params.courseId)).catch(() => null),
  component: RevisionPage,
});

function RevisionPage() {
  const { user } = authRoute.useRouteContext();
  const { courseId } = Route.useParams();
  const { chapter } = Route.useSearch();
  const course = useQuery(courseQuery(courseId));

  if (course.data) {
    const data = course.data;
    return (
      <CourseLanguageProvider language={data.language}>
        <LessonFrame>
          <RevisionBar course={data} user={user} />
          <div className="min-h-0 flex-1">
            <RevisionPanel key={courseId} course={data} {...(chapter ? { wanted: chapter } : {})} />
          </div>
        </LessonFrame>
      </CourseLanguageProvider>
    );
  }
  if (course.isError) {
    return (
      <AuthPage user={user}>
        <NotFoundCard status={apiStatus(course.error)} />
      </AuthPage>
    );
  }
  return (
    <main className="flex h-screen w-full items-center justify-center bg-paper text-sm text-muted-foreground">
      {m.revision_loading()}
    </main>
  );
}
