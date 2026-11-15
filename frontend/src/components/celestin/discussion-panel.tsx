/**
 * Discussion mode (spec 007): a free conversation about one chapter, with the
 * board and without the path.
 *
 * The conversation lives on the server, so it is loaded here and restored through
 * `sessionFromEntries`, and the session runs on the discussion transport. The screen
 * (`conversation-screen.tsx`) is the one a révision uses too; the reducer, the board,
 * the cards and the markers are the lesson's.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";

import {
  ConversationScreen,
  NewSessionButton,
  PanelMessage,
  PhoneTitle,
} from "@/components/celestin/conversation-screen";
import { ErrorRetry } from "@/components/celestin/not-found";
import { sessionFromEntries, useTutorSession } from "@/components/celestin/use-tutor-session";
import { useVoiceSession } from "@/components/celestin/use-voice-session";
import { useCourseLanguage } from "@/lib/course-language";
import { apiMessage } from "@/lib/tutor/client";
import { conversationQuery, discussionTransport, startConversation } from "@/lib/tutor/discussion";
import { useHealth } from "@/lib/tutor/health";
import type { ChapterView, Conversation } from "@/lib/tutor/types";
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
      <PanelMessage>
        <ErrorRetry
          message={apiMessage(query.error ?? create.error, m.discussion_failed())}
          onRetry={() => {
            // The mutation has to go back to idle, or the auto-create effect stays
            // parked on its error and « Réessayer » does nothing.
            reset();
            void query.refetch();
          }}
        />
      </PanelMessage>
    );
  }
  if (!conversation) return <PanelMessage>{m.discussion_loading()}</PanelMessage>;

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
    courseId: chapter.course_id,
    initialProgress: chapter.progress,
    transport,
    // Read once: the component is keyed on the conversation, so a new one is a
    // new mount rather than a new initial state.
    initialState: sessionFromEntries(conversation.entries),
  });
  const health = useHealth();
  const language = useCourseLanguage();
  const voice = useVoiceSession(session.handle, {
    enabled: health.data?.voice === true,
    scope,
  });

  return (
    <ConversationScreen
      session={session}
      voice={voice}
      courseId={chapter.course_id}
      subject={chapter.subject}
      headerAction={
        <NewSessionButton
          label={m.discussion_new()}
          title={m.discussion_new_title()}
          description={m.discussion_new_description()}
          onConfirm={onNew}
          disabled={replacing}
        />
      }
      top={<PhoneTitle lang={language}>{chapter.title}</PhoneTitle>}
    />
  );
}
