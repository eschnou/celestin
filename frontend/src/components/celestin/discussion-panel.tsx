/**
 * Discussion mode (spec 007): a free conversation about one chapter, with the
 * board and without the path.
 *
 * Two things differ from the lesson and nothing else does. The transcript lives
 * on the server, so it is loaded here and restored through `sessionFromEntries`
 * rather than started empty; and the session runs on the discussion transport,
 * which posts the message instead of the transcript. The reducer, the board, the
 * cards and the markers are the lesson's.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { SquarePen } from "lucide-react";
import { useCallback, useEffect, useMemo } from "react";

import { ConfirmDialog } from "@/components/celestin/confirm-dialog";
import { TutorBoardSplit } from "@/components/celestin/tutor-board-split";
import { TutorColumn } from "@/components/celestin/tutor-column";
import { sessionFromEntries, useTutorSession } from "@/components/celestin/use-tutor-session";
import { useVoiceSession } from "@/components/celestin/use-voice-session";
import { Whiteboard } from "@/components/celestin/whiteboard";
import { useCourseLanguage } from "@/lib/course-language";
import { apiMessage } from "@/lib/tutor/client";
import { conversationQuery, discussionTransport, startConversation } from "@/lib/tutor/discussion";
import { useHealth } from "@/lib/tutor/health";
import { useLearnerSentences } from "@/lib/tutor/prompts";
import { iconButton } from "@/components/celestin/styles";
import type { ChapterView, Conversation, Option } from "@/lib/tutor/types";
import { m } from "@/paraglide/messages";

/** The mode switch in the chapter bar is the way back to the parcours; the lesson
 *  hosts this panel hidden beside itself rather than navigating away (007 R1.3). */
export function DiscussionPanel({ chapter }: { chapter: ChapterView }) {
  const client = useQueryClient();
  const query = useQuery(conversationQuery(chapter.course_id, chapter.id));

  const create = useMutation({
    mutationFn: () => startConversation(chapter.course_id, chapter.id),
    onSuccess: (conversation) =>
      client.setQueryData(conversationQuery(chapter.course_id, chapter.id).queryKey, conversation),
  });

  // A first open reads null and creates one — the same call « Nouvelle
  // conversation » makes, so there is one creation path.
  const conversation = query.data ?? null;
  const missing = query.isSuccess && conversation === null;
  const { mutate, reset, isIdle } = create;
  useEffect(() => {
    if (missing && isIdle) mutate();
  }, [missing, isIdle, mutate]);

  if (query.isError || create.isError) {
    return (
      <Empty>
        {apiMessage(query.error ?? create.error, m.discussion_failed())}{" "}
        <button
          type="button"
          className="underline"
          onClick={() => {
            // The mutation has to go back to idle, or the auto-create effect stays
            // parked on its error and « Réessayer » does nothing.
            reset();
            void query.refetch();
          }}
        >
          {m.error_retry()}
        </button>
      </Empty>
    );
  }
  if (!conversation) return <Empty>{m.discussion_loading()}</Empty>;

  return (
    <Discussion
      // A new conversation is a new session: keyed, so the hook starts from the
      // new transcript instead of keeping the replaced one.
      key={conversation.id}
      chapter={chapter}
      conversation={conversation}
      onNew={() => create.mutate()}
      replacing={create.isPending}
    />
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full items-center justify-center p-6 text-center text-sm text-muted-foreground">
      <p>{children}</p>
    </div>
  );
}

function Discussion({
  chapter,
  conversation,
  onNew,
  replacing,
}: {
  chapter: ChapterView;
  conversation: Conversation;
  onNew: () => void;
  replacing: boolean;
}) {
  const scope = useMemo(
    () =>
      ({
        courseId: chapter.course_id,
        chapterId: chapter.id,
        mode: "discussion",
        conversationId: conversation.id,
      }) as const,
    [chapter.course_id, chapter.id, conversation.id],
  );
  const transport = useMemo(() => discussionTransport(scope), [scope]);
  const session = useTutorSession({
    ...scope,
    initialProgress: chapter.progress,
    transport,
    // Read once: the component is keyed on the conversation, so a new one is a
    // new mount rather than a new initial state.
    initialState: sessionFromEntries(conversation.entries),
  });
  const said = useLearnerSentences();
  const health = useHealth();
  const voice = useVoiceSession(session.handle, {
    enabled: health.data?.voice === true,
    scope,
  });
  const send = voice.phase !== "off" ? voice.sendText : session.send;
  const onAnswer = useCallback((option: Option) => send(said.answer(option.text)), [send, said]);

  const tutor = (
    <TutorColumn
      entries={session.entries}
      status={session.status}
      voice={voice}
      onSend={send}
      onCancel={session.cancel}
      onRetry={session.retry}
      onShowBoard={session.showBoard}
      dictation={health.data?.dictation === true}
      courseId={chapter.course_id}
      mixedLanguages={chapter.subject === "languages"}
      headerAction={<NewConversation onNew={onNew} replacing={replacing} />}
    />
  );
  const board = (
    <Whiteboard
      card={session.board}
      cards={session.boards}
      onSelect={session.showBoard}
      onAnswer={onAnswer}
    />
  );

  return (
    <div className="h-full min-h-0 w-full bg-paper">
      <TutorBoardSplit tutor={tutor} board={board} top={<ChapterTitle chapter={chapter} />} />
    </div>
  );
}

/** Starts over, after saying what is lost and what is not. */
function NewConversation({ onNew, replacing }: { onNew: () => void; replacing: boolean }) {
  return (
    <ConfirmDialog
      trigger={
        <button
          type="button"
          title={m.discussion_new()}
          aria-label={m.discussion_new()}
          className={`${iconButton} max-lg:size-10`}
          disabled={replacing}
        >
          <SquarePen className="size-4" />
        </button>
      }
      title={m.discussion_new_title()}
      description={m.discussion_new_description()}
      confirm={m.discussion_new()}
      onConfirm={onNew}
    />
  );
}

/** A phone's line above the board: which chapter this conversation is about. */
function ChapterTitle({ chapter }: { chapter: ChapterView }) {
  const language = useCourseLanguage();
  return (
    <p lang={language} className="truncate px-3 py-2 text-sm font-semibold">
      {chapter.title}
    </p>
  );
}
