import { useLayoutEffect, useState, type RefObject } from "react";

/** Without a measurable element (jsdom, SSR) charts draw at this width. */
const FALLBACK_WIDTH = 560;

/**
 * The element's content width in pixels. Charts draw at their real size rather
 * than scaling a `viewBox`, so 12 px text stays 12 px on a phone. The first
 * measure is taken before paint, so a chart never flashes at the fallback width.
 */
export function useWidth(ref: RefObject<HTMLElement | null>): number {
  const [width, setWidth] = useState(FALLBACK_WIDTH);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    if (element.clientWidth > 0) setWidth(element.clientWidth);
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      const next = Math.round(entry?.contentRect.width ?? 0);
      if (next > 0) setWidth(next);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);
  return width;
}
