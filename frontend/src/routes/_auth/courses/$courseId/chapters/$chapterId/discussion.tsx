import { useQuery } from "@tanstack/react-query";
import { createFileRoute, getRouteApi } from "@tanstack/react-router";

import { AuthPage } from "@/components/celestin/app-bar";
import { ChapterBar } from "@/components/celestin/chapter-bar";
import { DiscussionPanel } from "@/components/celestin/discussion-panel";
import { LessonFrame } from "@/components/celestin/tutor-board-split";
import { NotFoundCard } from "@/components/celestin/not-found";
import { CourseLanguageProvider } from "@/lib/course-language";
import { chapterQuery } from "@/lib/tutor/chapter";
import { ApiError, apiStatus } from "@/lib/tutor/client";
import { m } from "@/paraglide/messages";

const authRoute = getRouteApi("/_auth");

export const Route = createFileRoute("/_auth/courses/$courseId/chapters/$chapterId/discussion")({
  head: () => ({ meta: [{ title: m.discussion_head_title() }] }),
  loader: ({ context, params }) =>
    context.queryClient
      .ensureQueryData(chapterQuery(params.courseId, params.chapterId))
      .catch(() => null),
  component: DiscussionPage,
});

function DiscussionPage() {
  const { user } = authRoute.useRouteContext();
  const { courseId, chapterId } = Route.useParams();
  const chapter = useQuery(chapterQuery(courseId, chapterId));

  if (chapter.data) {
    return (
      <CourseLanguageProvider language={chapter.data.language}>
        <LessonFrame>
          <ChapterBar chapter={chapter.data} user={user} mode="discussion" />
          <div className="min-h-0 flex-1">
            <DiscussionPanel key={`${courseId}/${chapterId}`} chapter={chapter.data} />
          </div>
        </LessonFrame>
      </CourseLanguageProvider>
    );
  }
  if (chapter.isError) {
    const notReady =
      chapter.error instanceof ApiError && chapter.error.code === "chapter_not_ready";
    return (
      <AuthPage user={user}>
        <NotFoundCard status={notReady ? 409 : apiStatus(chapter.error)} />
      </AuthPage>
    );
  }
  return (
    <main className="flex h-screen w-full items-center justify-center bg-paper text-sm text-muted-foreground">
      {m.discussion_loading()}
    </main>
  );
}
