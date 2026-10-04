import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, getRouteApi, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { AuthPage } from "@/components/celestin/app-bar";
import { CurriculumEditor } from "@/components/celestin/content/curriculum-editor";
import { CurriculumView } from "@/components/celestin/content/curriculum-view";
import { PackEditor } from "@/components/celestin/content/pack-editor";
import { PackView } from "@/components/celestin/content/pack-view";
import { SourceEditor, sourceLabel } from "@/components/celestin/content/source-editor";
import { chapterName } from "@/components/celestin/chapter-row";
import { DocumentPicker } from "@/components/celestin/document-picker";
import { NotFoundCard } from "@/components/celestin/not-found";
import { secondary, panel } from "@/components/celestin/styles";
import { CourseLanguageProvider } from "@/lib/course-language";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { chapterQuery } from "@/lib/tutor/chapter";
import { apiStatus } from "@/lib/tutor/client";
import {
  chapterContentQuery,
  courseQuery,
  replaceDocument,
  saveCurriculum,
  savePack,
  saveSource,
  subjectsQuery,
} from "@/lib/tutor/courses";
import type { ChapterContent } from "@/lib/tutor/types";
import { m } from "@/paraglide/messages";

const authRoute = getRouteApi("/_auth");

export const Route = createFileRoute("/_auth/courses/$courseId/chapters/$chapterId/content")({
  head: () => ({ meta: [{ title: m.content_head_title() }] }),
  // « Redéposer le document » opens the source tab directly.
  validateSearch: (search: Record<string, unknown>): { tab?: "source" } =>
    search["tab"] === "source" ? { tab: "source" } : {},
  loader: ({ context, params }) =>
    context.queryClient
      .ensureQueryData(chapterContentQuery(params.courseId, params.chapterId))
      .catch(() => null),
  component: ContentPage,
});

type Tab = "pack" | "path" | "source";
type Editing = Tab | "document";

function ContentPage() {
  const { user } = authRoute.useRouteContext();
  const { courseId, chapterId } = Route.useParams();
  const content = useQuery(chapterContentQuery(courseId, chapterId));
  const data = content.data;
  return (
    <AuthPage user={user}>
      <Link
        to="/courses/$courseId"
        params={{ courseId }}
        className="text-sm text-muted-foreground hover:underline"
      >
        {m.content_back()}
      </Link>
      {content.isError && !data && <NotFoundCard status={apiStatus(content.error)} />}
      {data && (
        <CourseLanguageProvider language={data.language}>
          <ChapterContentPanel content={data} />
        </CourseLanguageProvider>
      )}
    </AuthPage>
  );
}

function ChapterContentPanel({ content }: { content: ChapterContent }) {
  const { courseId, chapterId } = Route.useParams();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const subjects = useQuery(subjectsQuery);
  const search = Route.useSearch();
  const [tab, setTab] = useState<Tab>(search.tab ?? (content.ready ? "pack" : "source"));
  const [editing, setEditing] = useState<Editing | null>(null);
  const contentKey = chapterContentQuery(courseId, chapterId).queryKey;

  // While a preparation runs, follow the light course query (it polls) instead of
  // polling this page's heavy content; refetch the content once the run ends.
  const generating = content.authoring_state === "generating";
  const course = useQuery({ ...courseQuery(courseId), enabled: generating });
  const runState = course.data?.chapters.find((c) => c.id === chapterId)?.authoring_state;
  useEffect(() => {
    if (generating) setEditing(null);
  }, [generating]);
  useEffect(() => {
    if (generating && runState && runState !== "generating") {
      void queryClient.invalidateQueries({ queryKey: contentKey });
    }
  }, [generating, runState, queryClient, contentKey]);

  const adopt = (next: ChapterContent) => {
    queryClient.setQueryData(contentKey, next);
    void queryClient.invalidateQueries({ queryKey: ["courses"] });
    queryClient.removeQueries({ queryKey: chapterQuery(courseId, chapterId).queryKey });
    setEditing(null);
  };
  const afterNewRun = async () => {
    await queryClient.invalidateQueries({ queryKey: ["courses"] });
    await navigate({ to: "/courses/$courseId", params: { courseId } });
  };
  const reload = () => {
    setEditing(null);
    void queryClient.invalidateQueries({ queryKey: contentKey });
  };

  return (
    <div className="mt-3 space-y-4">
      <div>
        <p className="text-xs tracking-wide text-muted-foreground uppercase">
          {m.chapter_content()}
        </p>
        <h1 className="text-xl font-bold">{chapterName(content)}</h1>
      </div>
      {content.authoring_state === "generating" && (
        <p className="rounded-md bg-secondary p-3 text-sm" aria-live="polite">
          {content.ready ? m.content_generating_new() : m.content_generating_first()}
        </p>
      )}
      {content.authoring_state === "failed" && content.authoring_message && (
        <p role="alert" className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
          {content.authoring_message}
        </p>
      )}
      <Tabs
        value={tab}
        onValueChange={(value) => {
          setTab(value as Tab);
          setEditing(null);
        }}
      >
        <TabsList>
          <TabsTrigger value="pack" disabled={!content.pack}>
            {m.content_tab_pack()}
          </TabsTrigger>
          <TabsTrigger value="path" disabled={!content.curriculum}>
            {m.content_tab_path()}
          </TabsTrigger>
          <TabsTrigger value="source">{sourceLabel(content)}</TabsTrigger>
        </TabsList>

        <TabsContent value="pack" className="mt-4">
          {content.pack &&
            (editing === "pack" ? (
              <PackEditor
                content={content}
                onSave={async (pack) =>
                  adopt(await savePack(courseId, chapterId, content.version, pack))
                }
                onCancel={() => setEditing(null)}
                onReload={reload}
              />
            ) : (
              <Readonly
                actions={[{ label: m.content_edit_pack(), onClick: () => setEditing("pack") }]}
                locked={generating}
              >
                <div className={`${panel}`}>
                  <PackView markdown={content.pack} />
                </div>
              </Readonly>
            ))}
        </TabsContent>

        <TabsContent value="path" className="mt-4">
          {content.curriculum &&
            (editing === "path" ? (
              <CurriculumEditor
                content={content}
                onSave={async (curriculum) =>
                  adopt(await saveCurriculum(courseId, chapterId, content.version, curriculum))
                }
                onCancel={() => setEditing(null)}
                onReload={reload}
              />
            ) : (
              <Readonly
                actions={[{ label: m.content_edit_path(), onClick: () => setEditing("path") }]}
                locked={generating}
              >
                <CurriculumView sections={content.curriculum.sections} />
              </Readonly>
            ))}
        </TabsContent>

        <TabsContent value="source" className="mt-4">
          {editing === "source" && subjects.data ? (
            <SourceEditor
              content={content}
              limits={subjects.data.limits}
              onSave={async (text) => {
                await saveSource(courseId, chapterId, text);
                await afterNewRun();
              }}
              onCancel={() => setEditing(null)}
            />
          ) : editing === "document" && subjects.data ? (
            <DocumentPicker
              id="replace-document"
              limits={subjects.data.limits}
              submitLabel={m.content_submit_again()}
              confirm={content.ready ? m.content_document_warning() : null}
              onSubmit={async (files) => {
                await replaceDocument(courseId, chapterId, files);
                await afterNewRun();
              }}
              onCancel={() => setEditing(null)}
            />
          ) : (
            <Readonly
              actions={[
                ...(content.source_text
                  ? [{ label: m.content_edit_source(), onClick: () => setEditing("source") }]
                  : []),
                { label: m.content_replace_document(), onClick: () => setEditing("document") },
              ]}
              locked={generating}
            >
              {content.source_kind === "document" && (
                <p className="text-xs text-muted-foreground">
                  {m.content_document_note({ count: content.page_count })}
                </p>
              )}
              {content.source_text ? (
                <pre className="max-h-[60vh] overflow-auto rounded-xl border border-border bg-background p-4 text-xs whitespace-pre-wrap">
                  {content.source_text}
                </pre>
              ) : (
                <p className="text-sm text-muted-foreground">{m.content_source_unread()}</p>
              )}
            </Readonly>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

/** A read view with its edit buttons. While a new version is being prepared the
 *  buttons are off: the run would overwrite the edit when it finishes. */
function Readonly({
  actions,
  locked,
  children,
}: {
  actions: { label: string; onClick: () => void }[];
  locked: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-end gap-3">
        {locked && <span className="text-xs text-muted-foreground">{m.content_locked()}</span>}
        {actions.map((action) => (
          <button
            key={action.label}
            type="button"
            onClick={action.onClick}
            disabled={locked}
            className={secondary}
          >
            {action.label}
          </button>
        ))}
      </div>
      {children}
    </div>
  );
}
