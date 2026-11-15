/**
 * The lesson screen: tutor column left, whiteboard right (001–003). Since 004 it
 * is mounted by the chapter route with the class and chapter from the URL, and
 * the progress it starts from comes from the server. Since 018 the séance does too:
 * the screen reads the live one with the progress, folds it back, and resumes where
 * it stopped instead of opening again.
 */

import { useQuery } from "@tanstack/react-query";
import { CourseLanguageProvider } from "@/lib/course-language";
import { useCallback, useMemo, useState } from "react";
import { ChapterBar, type ChapterMode } from "@/components/celestin/chapter-bar";
import { DiscussionPanel } from "@/components/celestin/discussion-panel";
import { ErrorRetry } from "@/components/celestin/not-found";
import { ChapterPath } from "@/components/celestin/chapter-path";
import { LessonFrame, TutorBoardSplit } from "@/components/celestin/tutor-board-split";
import { TutorColumn } from "@/components/celestin/tutor-column";
import {
  appendMarker,
  sessionFromEntries,
  useTutorSession,
  type SessionState,
} from "@/components/celestin/use-tutor-session";
import { useVoiceSession } from "@/components/celestin/use-voice-session";
import type { User } from "@/lib/auth";
import { apiMessage } from "@/lib/tutor/client";
import { useHealth } from "@/lib/tutor/health";
import { useLearnerSentences } from "@/lib/tutor/prompts";
import { lessonStartQuery, type LessonStart } from "@/lib/tutor/seance";
import type { ChapterView, Option, Seance } from "@/lib/tutor/types";
import { Whiteboard } from "@/components/celestin/whiteboard";
import { m } from "@/paraglide/messages";

export function LessonScreen(props: { chapter: ChapterView; user: User }) {
  return (
    <CourseLanguageProvider language={props.chapter.language}>
      <LessonLoader {...props} />
    </CourseLanguageProvider>
  );
}

/** Reads the live séance and the progress before the session mounts (018 D6), so the
 *  hook starts from them synchronously and never has a pre-restore state to guard. */
function LessonLoader({ chapter, user }: { chapter: ChapterView; user: User }) {
  const start = useQuery(lessonStartQuery(chapter.course_id, chapter.id));
  if (start.data) return <Lesson chapter={chapter} user={user} start={start.data} />;
  return (
    <main className="flex h-screen w-full items-center justify-center bg-paper p-6 text-center text-sm text-muted-foreground">
      {start.isError ? (
        <p>
          <ErrorRetry
            message={apiMessage(start.error, m.lesson_restore_failed())}
            onRetry={() => void start.refetch()}
          />
        </p>
      ) : (
        m.chapter_loading()
      )}
    </main>
  );
}

/** A stored séance as the session resumes it: as it was, then « séance reprise ». None
 *  for an empty or missing one, which the opening turn starts instead. */
function resumed(seance: Seance | null): SessionState | null {
  if (!seance || seance.entries.length === 0) return null;
  return appendMarker(sessionFromEntries(seance.entries), m.lesson_resumed_marker());
}

/** The sections the cahier can reread: those with stored cards when the lesson
 *  mounted, plus the one on the board now once a card has been shown in it. */
function rereadable(
  stored: Record<string, { cards: number }>,
  section: string | null,
  shown: boolean,
): ReadonlySet<string> {
  const sections = new Set(
    Object.entries(stored)
      .filter(([, { cards }]) => cards > 0)
      .map(([id]) => id),
  );
  if (section && shown) sections.add(section);
  return sections;
}

/** The sections with a stored séance (spec 019: the map's « Reprendre »): those the server
 *  listed when the lesson mounted, plus those started, not reviewed, since. */
function begunSections(
  stored: Record<string, { cards: number }>,
  started: readonly string[],
): ReadonlySet<string> {
  return new Set([...Object.keys(stored), ...started]);
}

function Lesson({
  chapter,
  user,
  start,
}: {
  chapter: ChapterView;
  user: User;
  start: LessonStart;
}) {
  // The route remounts the screen on a new course or chapter, so this is fixed for its life.
  const scope = useMemo(
    () => ({ courseId: chapter.course_id, chapterId: chapter.id }),
    [chapter.course_id, chapter.id],
  );
  // Read once: the session owns the transcript from here on.
  const [restored] = useState(() => resumed(start.seance));
  const session = useTutorSession({
    ...scope,
    // The server's progress, read with the séance, not the one the replay computed.
    initialProgress: start.progress,
    ...(restored ? { initialState: restored } : {}),
  });
  const [stored, setStored] = useState(start.seances);
  const { resetProgress } = session;
  // The reset deletes the stored séances with the progress (018 D9): nothing to reread.
  const reset = useCallback(() => {
    void resetProgress().then((saved) => {
      if (saved) setStored({});
    });
  }, [resetProgress]);
  // On whether a card has been shown, not how many: a new card must not rebuild the set
  // and re-render the memoized map.
  const shown = session.boards.length > 0;
  const reread = useMemo(
    () => rereadable(stored, session.section, shown),
    [stored, session.section, shown],
  );
  const { started } = session;
  const begun = useMemo(() => begunSections(stored, started), [stored, started]);
  // A discussion opens over the lesson rather than instead of it (007 R1.3): mounted
  // on first open, then kept and merely hidden, so switching back is instant and a
  // turn in flight is not cut. (Since 018 the séance would survive a remount too.)
  const [discussionOpen, setDiscussionOpen] = useState(false);
  const [discussionMounted, setDiscussionMounted] = useState(false);
  const switchMode = useCallback((mode: ChapterMode) => {
    if (mode === "discussion") setDiscussionMounted(true);
    setDiscussionOpen(mode === "discussion");
  }, []);
  const said = useLearnerSentences();
  const health = useHealth();
  const voice = useVoiceSession(session.handle, { enabled: health.data?.voice === true, scope });
  // While a voice session is open, everything she says or clicks goes to the call.
  const send = voice.phase !== "off" ? voice.sendText : session.send;
  const onAnswer = useCallback((option: Option) => send(said.answer(option.text)), [send, said]);
  const { nextStep } = session;
  const onNextStep = useCallback(() => {
    if (nextStep?.kind === "section") {
      const title = chapter.sections.find((s) => s.id === nextStep.sectionId)?.title;
      const opening = begun.has(nextStep.sectionId) ? said.resume : said.start;
      send(title ? opening(title) : said.nextSection);
    } else {
      send(said.nextStep);
    }
  }, [begun, chapter, nextStep, send, said]);

  // The same element for both frames: under the tutor's header on desktop, above the board on a phone.
  const path = (
    <ChapterPath
      chapter={chapter}
      progress={session.progress}
      streaming={session.status === "streaming"}
      onSend={send}
      onReset={reset}
      rereadable={reread}
      begun={begun}
    />
  );
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
      path={path}
    />
  );
  const board = (
    <Whiteboard
      card={session.board}
      cards={session.boards}
      onSelect={session.showBoard}
      onAnswer={onAnswer}
      nextStep={session.nextStep}
      onNextStep={onNextStep}
    />
  );

  return (
    <LessonFrame>
      <ChapterBar
        chapter={chapter}
        user={user}
        mode={discussionOpen ? "discussion" : "parcours"}
        onMode={switchMode}
      />
      {discussionMounted && (
        <div className="min-h-0 flex-1" hidden={!discussionOpen}>
          <DiscussionPanel chapter={chapter} />
        </div>
      )}
      <div className="min-h-0 flex-1" hidden={discussionOpen}>
        <TutorBoardSplit tutor={tutor} board={board} top={path} />
      </div>
    </LessonFrame>
  );
}
