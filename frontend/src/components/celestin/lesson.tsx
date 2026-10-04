/**
 * The lesson screen: tutor column left, whiteboard right (001–003). Since 004 it
 * is mounted by the chapter route with the class and chapter from the URL, and
 * the progress it starts from comes from the server.
 */

import { CourseLanguageProvider } from "@/lib/course-language";
import { useCallback, useMemo, useState } from "react";
import { ChapterBar, type ChapterMode } from "@/components/celestin/chapter-bar";
import { DiscussionPanel } from "@/components/celestin/discussion-panel";
import { ChapterPath } from "@/components/celestin/chapter-path";
import { LessonFrame, TutorBoardSplit } from "@/components/celestin/tutor-board-split";
import { TutorColumn } from "@/components/celestin/tutor-column";
import { useTutorSession } from "@/components/celestin/use-tutor-session";
import { useVoiceSession } from "@/components/celestin/use-voice-session";
import type { User } from "@/lib/auth";
import { useHealth } from "@/lib/tutor/health";
import { useLearnerSentences } from "@/lib/tutor/prompts";
import type { ChapterView, Option } from "@/lib/tutor/types";
import { Whiteboard } from "@/components/celestin/whiteboard";

export function LessonScreen(props: { chapter: ChapterView; user: User }) {
  return (
    <CourseLanguageProvider language={props.chapter.language}>
      <Lesson {...props} />
    </CourseLanguageProvider>
  );
}

function Lesson({ chapter, user }: { chapter: ChapterView; user: User }) {
  // The route remounts the screen on a new course or chapter, so this is fixed for its life.
  const scope = useMemo(
    () => ({ courseId: chapter.course_id, chapterId: chapter.id }),
    [chapter.course_id, chapter.id],
  );
  const session = useTutorSession({ ...scope, initialProgress: chapter.progress });
  // A discussion opens over the lesson rather than instead of it: the séance's
  // transcript and board live in memory only, so unmounting would throw them away
  // (007 R1.3). Mounted on first open, then kept and merely hidden.
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
      send(title ? said.start(title) : said.nextSection);
    } else {
      send(said.nextStep);
    }
  }, [chapter, nextStep, send, said]);

  // The same element for both frames: under the tutor's header on desktop, above the board on a phone.
  const path = (
    <ChapterPath
      chapter={chapter}
      progress={session.progress}
      streaming={session.status === "streaming"}
      onSend={send}
      onReset={session.resetProgress}
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
