import { useEffect, useState } from "react";

/** Below this much lost height, the visual viewport shrank for a browser bar, not a keyboard. */
const KEYBOARD_MIN = 150;

export type VisualViewportState = {
  /** The height the page can actually use; null until measured or without the API. */
  height: number | null;
  /** How far the browser scrolled the layout viewport to show the focused field. */
  offsetTop: number;
  keyboardOpen: boolean;
};

const UNKNOWN: VisualViewportState = { height: null, offsetTop: 0, keyboardOpen: false };

/**
 * What a phone leaves of the screen. `100vh` ignores the on-screen keyboard (and
 * Safari's collapsing bar), so a composer pinned to the bottom ends up behind it;
 * the visual viewport is the one measure that follows both. Without the API
 * (jsdom, old browsers) the state is unknown and callers keep their CSS height.
 */
export function useVisualViewport(): VisualViewportState {
  const [state, setState] = useState<VisualViewportState>(UNKNOWN);

  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return;
    const update = () =>
      setState((previous) => {
        const next = {
          height: Math.round(viewport.height),
          offsetTop: Math.round(viewport.offsetTop),
          keyboardOpen: window.innerHeight - viewport.height > KEYBOARD_MIN,
        };
        return previous.height === next.height &&
          previous.offsetTop === next.offsetTop &&
          previous.keyboardOpen === next.keyboardOpen
          ? previous
          : next;
      });
    update();
    viewport.addEventListener("resize", update);
    viewport.addEventListener("scroll", update);
    return () => {
      viewport.removeEventListener("resize", update);
      viewport.removeEventListener("scroll", update);
    };
  }, []);

  return state;
}
