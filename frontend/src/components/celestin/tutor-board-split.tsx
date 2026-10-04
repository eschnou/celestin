/**
 * The frame both modes work in: the tutor column beside the board on desktop;
 * on a small screen the board takes the screen and Célestin shrinks to a caption
 * and the composer at the bottom. The geometry lives here so a lesson and a
 * discussion cannot drift apart (007, 015).
 */

import type { ReactNode } from "react";

import { CompactLayoutProvider } from "@/components/celestin/compact-layout";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { useIsDesktop } from "@/hooks/use-is-desktop";
import { useVisualViewport } from "@/hooks/use-visual-viewport";

export function TutorBoardSplit({
  tutor,
  board,
  top,
}: {
  tutor: ReactNode;
  board: ReactNode;
  /** Small screens only: a line above the board (the path, the chapter's title).
   *  Gone while the keyboard is up, so the board keeps what room is left. */
  top?: ReactNode;
}) {
  const isDesktop = useIsDesktop();
  const { keyboardOpen } = useVisualViewport();
  if (isDesktop) {
    /* Tutor left, whiteboard right, draggable divider. */
    return (
      <ResizablePanelGroup orientation="horizontal" className="flex h-full">
        <ResizablePanel defaultSize="35" minSize="24" maxSize="50">
          {tutor}
        </ResizablePanel>
        <ResizableHandle className="w-px bg-border transition-colors hover:bg-primary/40" />
        <ResizablePanel defaultSize="65" minSize="50">
          {board}
        </ResizablePanel>
      </ResizablePanelGroup>
    );
  }
  /* Small screens: the work comes first, the talk is a caption under it. */
  return (
    <CompactLayoutProvider value={true}>
      <div className="flex h-full flex-col">
        {top && !keyboardOpen && (
          <div className="shrink-0 border-b border-border bg-background">{top}</div>
        )}
        <div className="min-h-0 flex-1">{board}</div>
        <div className="shrink-0 border-t border-border">{tutor}</div>
      </div>
    </CompactLayoutProvider>
  );
}

/**
 * The screen the frame fills. On a phone its height is the visual viewport's, so
 * the composer stays above the keyboard instead of behind it; `dvh` covers the
 * first paint and browsers that do not report one.
 */
export function LessonFrame({ children }: { children: ReactNode }) {
  const isDesktop = useIsDesktop();
  const { height, offsetTop } = useVisualViewport();
  const fitted = !isDesktop && height !== null;
  return (
    <main
      className="flex h-dvh w-full flex-col overflow-hidden bg-paper"
      style={
        fitted
          ? { height, ...(offsetTop > 0 ? { transform: `translateY(${offsetTop}px)` } : {}) }
          : undefined
      }
    >
      {children}
    </main>
  );
}

/** The slim line above either frame: course, chapter, actions, who is signed in. */
export const BAR =
  "flex items-center gap-3 border-b border-border bg-background px-4 py-1.5 text-xs";
