/**
 * Révision (spec 020): the third mode, over a whole course. Without a live révision (or after
 * « Nouvelle révision ») the student picks the chapters; with one, she works in the same
 * screen as a discussion: the tutor column and the board, no strip, no map, no page-turn
 * button, and no telephone (D5). The révision's own pieces are the three quick replies under
 * the composer, the « Bilan » sheet, and « Nouvelle révision ».
 *
 * The transcript lives on the server, read once and restored through `sessionFromEntries`;
 * the session posts the message on the révision transport. A result Célestin notes arrives as
 * `revision.result`, which the reducer keeps in the session's `results`, so the « Bilan »
 * shows it the moment it is noted.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ListChecks } from "lucide-react";
import { useMemo, useState } from "react";

import { useCompactLayout } from "@/components/celestin/compact-layout";
import {
  ConversationScreen,
  NewSessionButton,
  PanelMessage,
  PhoneTitle,
} from "@/components/celestin/conversation-screen";
import { ErrorRetry } from "@/components/celestin/not-found";
import { iconButton, primary, warningBox } from "@/components/celestin/styles";
import { sessionFromEntries, useTutorSession } from "@/components/celestin/use-tutor-session";
import { apiMessage } from "@/lib/tutor/client";
import { useLearnerSentences } from "@/lib/tutor/prompts";
import {
  latestResults,
  revisionQuery,
  revisionTransport,
  startRevision,
} from "@/lib/tutor/revision";
import { OUTCOME_LABEL } from "@/lib/tutor/labels";
import {
  EMPTY_PROGRESS,
  REVISION_OUTCOMES,
  type CourseDetail,
  type Revision,
  type RevisionView,
  type TranscriptEntry,
} from "@/lib/tutor/types";
import { cn } from "@/lib/utils";
import { m } from "@/paraglide/messages";
import { OutcomeDot } from "./outcome";
import { RevisionBilan } from "./revision-bilan";
import { RevisionChooser } from "./revision-chooser";

type CourseInfo = Pick<CourseDetail, "id" | "subject">;

export function RevisionPanel({ course, wanted }: { course: CourseInfo; wanted?: string }) {
  const client = useQueryClient();
  const query = useQuery(revisionQuery(course.id));
  const [choosing, setChoosing] = useState(false);
  /** « Revenir à la révision en cours »: the server's read is in flight. */
  const [returning, setReturning] = useState(false);
  const [backError, setBackError] = useState<string | null>(null);

  const start = useMutation({
    mutationFn: (chapterIds: string[]) => startRevision(course.id, chapterIds),
    // The answer is the read itself (the new révision, the chapters, and the results the
    // closed one noted): nothing to fetch again.
    onSuccess: (view) => {
      client.setQueryData<RevisionView>(revisionQuery(course.id).queryKey, view);
      setChoosing(false);
    },
  });

  /** Back to the révision in progress, as the server has it now: the cached read is the page
   *  load's, without the turns made since (and empty for a révision started on this page),
   *  and the server may have closed it. With no live révision in the answer, the chooser
   *  stays, without the way back. */
  const back = async () => {
    start.reset();
    setBackError(null);
    setReturning(true);
    const read = await query.refetch();
    setReturning(false);
    if (read.isError) setBackError(apiMessage(read.error, m.revision_failed()));
    else if (read.data?.revision) setChoosing(false);
  };

  const view = query.data;
  if (!view) {
    return query.isError ? (
      <PanelMessage>
        <ErrorRetry
          message={apiMessage(query.error, m.revision_failed())}
          onRetry={() => void query.refetch()}
        />
      </PanelMessage>
    ) : (
      <PanelMessage>{m.revision_loading()}</PanelMessage>
    );
  }
  if (returning) return <PanelMessage>{m.revision_loading()}</PanelMessage>;

  if (!view.revision || choosing) {
    return (
      <RevisionChooser
        chapters={view.chapters}
        wanted={wanted}
        pending={start.isPending}
        error={start.isError ? apiMessage(start.error, m.revision_start_failed()) : backError}
        onStart={(ids) => {
          setBackError(null);
          start.mutate(ids);
        }}
        onBack={view.revision ? () => void back() : undefined}
      />
    );
  }

  return (
    <LiveRevision
      // A new révision is a new session: keyed, so the hook starts from its transcript.
      key={view.revision.id}
      course={course}
      view={view}
      revision={view.revision}
      onNew={() => {
        start.reset();
        setBackError(null);
        setChoosing(true);
      }}
    />
  );
}

/** The server's word on a révision it closed (`409 conversation_closed`), when the last error
 *  of the transcript is that one; its own fallback when the server said nothing. Walks back
 *  from the end, to the last error only. */
function closedMessage(entries: TranscriptEntry[]): string | null {
  for (let i = entries.length - 1; i >= 0; i--) {
    const entry = entries[i]!;
    if (entry.role !== "error") continue;
    return entry.code === "conversation_closed" ? entry.text || m.revision_closed() : null;
  }
  return null;
}

function LiveRevision({
  course,
  view,
  revision,
  onNew,
}: {
  course: CourseInfo;
  view: RevisionView;
  revision: Revision;
  onNew: () => void;
}) {
  const transport = useMemo(
    () => revisionTransport({ courseId: course.id, revisionId: revision.id }),
    [course.id, revision.id],
  );
  const session = useTutorSession({
    courseId: course.id,
    initialProgress: EMPTY_PROGRESS,
    transport,
    // Read once: the component is keyed on the révision. Its stored results are in the
    // server's read (`view.results`); the session's are the ones noted from here on.
    initialState: sessionFromEntries(revision.entries),
  });
  const [bilan, setBilan] = useState(false);
  // The day a result noted on this page shows: today.
  const [today] = useState(() => new Date().toISOString());
  const results = useMemo(
    () => latestResults(view.results, session.results, today),
    [view.results, session.results, today],
  );
  const chapters = useMemo(
    () => view.chapters.filter((c) => revision.chapter_ids.includes(c.id)),
    [view.chapters, revision.chapter_ids],
  );
  // Only a failed turn can end on the closed error: no scan of the transcript while one streams.
  const failed = session.status === "error";
  const closed = useMemo(
    () => (failed ? closedMessage(session.entries) : null),
    [failed, session.entries],
  );
  const streaming = session.status === "streaming";

  return (
    <div className="flex h-full min-h-0 flex-col">
      {closed && (
        <div
          role="alert"
          className={cn(warningBox, "m-3 flex flex-wrap items-center gap-x-3 gap-y-2")}
        >
          <span className="min-w-0 flex-1">{closed}</span>
          <button type="button" className={primary} onClick={onNew}>
            {m.revision_new()}
          </button>
        </div>
      )}
      <div className="min-h-0 flex-1">
        <ConversationScreen
          session={session}
          courseId={course.id}
          subject={course.subject}
          headerAction={<Actions onBilan={() => setBilan(true)} onNew={onNew} />}
          composerFooter={<QuickReplies disabled={streaming} onSend={session.send} />}
          top={<PhoneTitle>{m.revision_scope({ count: chapters.length })}</PhoneTitle>}
        />
      </div>
      <RevisionBilan
        open={bilan}
        onOpenChange={setBilan}
        courseId={course.id}
        chapters={chapters}
        results={results}
      />
    </div>
  );
}

/** The tutor header's actions: the « Bilan », and starting over after saying what is kept. */
function Actions({ onBilan, onNew }: { onBilan: () => void; onNew: () => void }) {
  const compact = useCompactLayout();
  return (
    <>
      <button
        type="button"
        onClick={onBilan}
        title={m.revision_bilan_title()}
        className={cn(
          iconButton,
          "w-auto gap-1.5 px-2 text-xs font-semibold",
          compact && "h-10 min-w-10",
        )}
      >
        <ListChecks className="size-4" aria-hidden />
        <span className={compact ? "sr-only" : undefined}>{m.revision_bilan()}</span>
      </button>
      <NewSessionButton
        label={m.revision_new()}
        title={m.revision_new_title()}
        description={m.revision_new_description()}
        onConfirm={onNew}
      />
    </>
  );
}

/** How the question went, in one tap: the student's sentence, in the course's language. */
function QuickReplies({ disabled, onSend }: { disabled: boolean; onSend: (text: string) => void }) {
  const said = useLearnerSentences();
  const compact = useCompactLayout();
  return (
    <div
      role="group"
      aria-label={m.revision_quick_label()}
      className="flex flex-wrap items-center gap-1.5"
    >
      {!compact && (
        <span className="mr-1 text-xs text-muted-foreground" aria-hidden>
          {m.revision_quick_label()}
        </span>
      )}
      {REVISION_OUTCOMES.map((outcome) => (
        <button
          key={outcome}
          type="button"
          disabled={disabled}
          onClick={() => onSend(said.assess(outcome))}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-2.5 text-xs font-semibold transition-colors hover:bg-secondary disabled:opacity-50",
            compact ? "min-h-9" : "py-1",
          )}
        >
          <OutcomeDot outcome={outcome} />
          {OUTCOME_LABEL[outcome]()}
        </button>
      ))}
    </div>
  );
}
