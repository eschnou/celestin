import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, getRouteApi } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { AuthPage } from "@/components/celestin/app-bar";
import { ChapterStateCard } from "@/components/celestin/chapter-state-card";
import { LessonScreen } from "@/components/celestin/lesson";
import { NotFoundCard } from "@/components/celestin/not-found";
import { chapterQuery } from "@/lib/tutor/chapter";
import { ApiError, apiMessage, apiStatus } from "@/lib/tutor/client";
import { courseQuery, retryChapter } from "@/lib/tutor/courses";
import { m } from "@/paraglide/messages";

const authRoute = getRouteApi("/_auth");

export const Route = createFileRoute("/_auth/courses/$courseId/chapters/$chapterId/")({
  head: () => ({ meta: [{ title: m.chapter_head_title() }] }),
  // Progress comes with the chapter (004 R6.4); the lesson mounts once it is here.
  loader: ({ context, params }) =>
    context.queryClient
      .ensureQueryData(chapterQuery(params.courseId, params.chapterId))
      .catch(() => null),
  component: ChapterPage,
});

function ChapterPage() {
  const { user } = authRoute.useRouteContext();
  const { courseId, chapterId } = Route.useParams();
  const chapter = useQuery(chapterQuery(courseId, chapterId));
  // `data` first: React Query keeps the last good data on a failed background
  // refetch, and tearing the screen down there would lose the whole session.
  if (chapter.data) {
    return <LessonScreen key={`${courseId}/${chapterId}`} chapter={chapter.data} user={user} />;
  }
  if (chapter.error instanceof ApiError && chapter.error.code === "chapter_not_ready") {
    return (
      <AuthPage user={user}>
        <NotReady courseId={courseId} chapterId={chapterId} />
      </AuthPage>
    );
  }
  if (chapter.isError) {
    return (
      <AuthPage user={user}>
        <NotFoundCard status={apiStatus(chapter.error)} />
      </AuthPage>
    );
  }
  return (
    <main className="flex h-screen w-full items-center justify-center bg-paper text-sm text-muted-foreground">
      {m.chapter_loading()}
    </main>
  );
}

/** Follows the course page's polling, and opens the lesson once the chapter is ready. */
function NotReady({ courseId, chapterId }: { courseId: string; chapterId: string }) {
  const queryClient = useQueryClient();
  const course = useQuery(courseQuery(courseId));
  const row = course.data?.chapters.find((c) => c.id === chapterId);
  const ready = row?.ready === true;
  const [error, setError] = useState<string | null>(null);
  const retry = async () => {
    setError(null);
    try {
      await retryChapter(courseId, chapterId);
      await queryClient.invalidateQueries({ queryKey: courseQuery(courseId).queryKey });
    } catch (err) {
      setError(apiMessage(err, m.chapter_retry_failed()));
    }
  };
  useEffect(() => {
    if (ready)
      void queryClient.invalidateQueries({ queryKey: chapterQuery(courseId, chapterId).queryKey });
  }, [ready, queryClient, courseId, chapterId]);
  return (
    <ChapterStateCard courseId={courseId} row={row} onRetry={() => void retry()} error={error} />
  );
}
