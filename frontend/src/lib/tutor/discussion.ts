/**
 * Discussion mode (spec 007): the conversation lives on the server, so the turn
 * request names it instead of carrying the transcript. The parcours posts its message
 * to `/api/chat` (018); these are the routes for the other mode. A spoken turn is
 * reported through `voice/client.ts`'s `reportTurn`, which serves both modes.
 */

import { queryOptions } from "@tanstack/react-query";

import { getJson, sendJson, streamEvents } from "@/lib/tutor/client";
import type { Conversation, LessonScope, TutorEvent } from "@/lib/tutor/types";

export const TURN_URL = "/api/discussion/turn";
export const VOICE_TURN_URL = "/api/discussion/voice/turn";

const discussionUrl = (courseId: string, chapterId: string) =>
  `/api/courses/${encodeURIComponent(courseId)}/chapters/${encodeURIComponent(chapterId)}/discussion`;

/** The live conversation, or null. A pure read: creating one is the POST below,
 *  which is also what « Nouvelle conversation » calls. */
export const conversationQuery = (courseId: string, chapterId: string) =>
  queryOptions({
    queryKey: ["discussion", courseId, chapterId],
    queryFn: () =>
      getJson<{ conversation: Conversation | null }>(discussionUrl(courseId, chapterId)).then(
        (body) => body.conversation,
      ),
    // Read once when the panel mounts: the live transcript belongs to the session
    // hook from then on, so a refetch would fetch the whole thing to discard it.
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    gcTime: 0,
    retry: false,
  });

export async function startConversation(
  courseId: string,
  chapterId: string,
): Promise<Conversation> {
  const response = await sendJson(discussionUrl(courseId, chapterId));
  return ((await response.json()) as { conversation: Conversation }).conversation;
}

/** The turn transport for `useTutorSession`: the message, not the transcript. */
export function discussionTransport(scope: LessonScope & { conversationId: string }) {
  return (input: { message: string | null }, signal: AbortSignal): AsyncGenerator<TutorEvent> =>
    streamEvents(
      TURN_URL,
      {
        course_id: scope.courseId,
        chapter_id: scope.chapterId,
        conversation_id: scope.conversationId,
        message: input.message,
      },
      signal,
    );
}
