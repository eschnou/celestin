/**
 * The chapter's path as the lesson shows it: the position strip, and the map it
 * opens. It owns the map's open state, so the lesson can mount it where the frame
 * wants it: under the tutor's header on desktop, above the board on a phone (015).
 */

import { useCallback, useState } from "react";

import { ChapterMapSheet } from "@/components/celestin/chapter-map";
import { ChapterStrip } from "@/components/celestin/chapter-strip";
import { useCompactLayout } from "@/components/celestin/compact-layout";
import type { ChapterView, Progress } from "@/lib/tutor/types";

export function ChapterPath({
  chapter,
  progress,
  streaming,
  onSend,
  onReset,
  rereadable,
  begun,
}: {
  chapter: Pick<ChapterView, "id" | "course_id" | "title" | "sections">;
  progress: Progress;
  /** A turn is in flight: the map's actions wait. */
  streaming: boolean;
  onSend: (text: string) => void;
  onReset: () => void;
  /** The sections with boards in the cahier (018): their rows offer « Relire ». */
  rereadable: ReadonlySet<string>;
  /** The sections with a stored séance (spec 019): the map offers « Reprendre » there. */
  begun: ReadonlySet<string>;
}) {
  const compact = useCompactLayout();
  const [open, setOpen] = useState(false);
  const openMap = useCallback(() => setOpen(true), []);
  return (
    <>
      <ChapterStrip chapter={chapter} progress={progress} onOpen={openMap} compact={compact} />
      <ChapterMapSheet
        open={open}
        onOpenChange={setOpen}
        chapter={chapter}
        progress={progress}
        streaming={streaming}
        onSend={onSend}
        onReset={onReset}
        rereadable={rereadable}
        begun={begun}
      />
    </>
  );
}
