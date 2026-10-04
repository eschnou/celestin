import React, { useEffect, useLayoutEffect, useRef } from "react";
import { continueRender, delayRender, useCurrentFrame, useVideoConfig } from "remotion";

/**
 * The product's components animate with CSS keyframes (a card slides in, a chart grows,
 * a flowchart appears row by row). Remotion captures frames independently, so CSS time
 * must be driven by the frame: every animation under this wrapper is paused and set to
 * the local time of the sequence it sits in. Mount it inside the <Sequence> where the
 * component appears.
 */
export const Scrub: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const ref = useRef<HTMLDivElement>(null);
  const ms = (frame / fps) * 1000;

  const sync = () => {
    const animations = ref.current?.getAnimations({ subtree: true }) ?? [];
    for (const animation of animations) {
      if (!(animation instanceof CSSAnimation)) continue;
      animation.pause();
      animation.currentTime = ms;
    }
  };

  useLayoutEffect(sync);

  // Components that measure themselves (flowcharts, charts) mount animated children one
  // render later: settle, sync again, then let the frame be captured.
  useEffect(() => {
    const handle = delayRender("scrub");
    let second = 0;
    const first = requestAnimationFrame(() => {
      second = requestAnimationFrame(() => {
        sync();
        continueRender(handle);
      });
    });
    return () => {
      cancelAnimationFrame(first);
      cancelAnimationFrame(second);
      continueRender(handle);
    };
  });

  return (
    <div ref={ref} className="contents">
      {children}
    </div>
  );
};
