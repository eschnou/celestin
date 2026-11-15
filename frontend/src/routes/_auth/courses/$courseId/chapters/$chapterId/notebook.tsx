import { useQuery } from "@tanstack/react-query";
import { createFileRoute, getRouteApi, Link, useLocation } from "@tanstack/react-router";

import { AuthPage } from "@/components/celestin/app-bar";
import { NotebookView } from "@/components/celestin/notebook";
import { ErrorRetry, NotFoundCard } from "@/components/celestin/not-found";
import { CourseLanguageProvider } from "@/lib/course-language";
import { chapterQuery } from "@/lib/tutor/chapter";
import { apiMessage, chapterErrorStatus } from "@/lib/tutor/client";
import { notebookQuery } from "@/lib/tutor/seance";
import { m } from "@/paraglide/messages";

const authRoute = getRouteApi("/_auth");

/** The cahier (spec 018 D8): the chapter's stored boards, reread without Célestin. */
export const Route = createFileRoute("/_auth/courses/$courseId/chapters/$chapterId/notebook")({
  head: () => ({ meta: [{ title: m.notebook_head_title() }] }),
  // Titles, order and language come with the chapter; the boards with the notebook.
  loader: ({ context, params }) =>
    Promise.all([
      context.queryClient.ensureQueryData(chapterQuery(params.courseId, params.chapterId)),
      context.queryClient.ensureQueryData(notebookQuery(params.courseId, params.chapterId)),
    ]).catch(() => null),
  component: NotebookPage,
});

function NotebookPage() {
  const { user } = authRoute.useRouteContext();
  const { courseId, chapterId } = Route.useParams();
  const anchor = useLocation({ select: (location) => location.hash });
  const chapter = useQuery(chapterQuery(courseId, chapterId));
  const notebook = useQuery(notebookQuery(courseId, chapterId));

  return (
    <AuthPage user={user}>
      <Link
        to="/courses/$courseId/chapters/$chapterId"
        params={{ courseId, chapterId }}
        className="text-sm text-muted-foreground hover:underline print:hidden"
      >
        {m.notebook_back()}
      </Link>
      {chapter.isError ? (
        <NotFoundCard status={chapterErrorStatus(chapter.error)} />
      ) : notebook.isError ? (
        <p className="mt-6 text-sm text-muted-foreground">
          <ErrorRetry
            message={apiMessage(notebook.error, m.notebook_failed())}
            onRetry={() => void notebook.refetch()}
          />
        </p>
      ) : chapter.data && notebook.data ? (
        <CourseLanguageProvider language={chapter.data.language}>
          <NotebookView
            chapter={chapter.data}
            notebook={notebook.data}
            anchor={anchor || undefined}
          />
        </CourseLanguageProvider>
      ) : (
        <p className="mt-6 text-sm text-muted-foreground">{m.notebook_loading()}</p>
      )}
    </AuthPage>
  );
}
