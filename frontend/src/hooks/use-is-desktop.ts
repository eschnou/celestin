import { useEffect, useState } from "react";

/** Matches the `lg` breakpoint the lesson layout switches on. */
const DESKTOP_BREAKPOINT = 1024;

/**
 * Drives the lesson layout from JS rather than CSS, so only one tree is mounted.
 * Rendering both and hiding one with CSS meant two of every component, two KaTeX
 * board trees, and two of every render during a stream.
 *
 * Defaults to desktop, which is what the product targets; a narrow viewport
 * corrects on the first effect.
 */
export function useIsDesktop(): boolean {
  const [isDesktop, setIsDesktop] = useState(true);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia(`(min-width: ${DESKTOP_BREAKPOINT}px)`);
    const update = () => setIsDesktop(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  return isDesktop;
}
