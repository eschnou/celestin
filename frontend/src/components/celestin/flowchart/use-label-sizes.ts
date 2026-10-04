import { useEffect, useLayoutEffect, useMemo, useRef, useState, type RefObject } from "react";
import type { Graph } from "./graph";
import { labelSizes, sizesKey, type LabelSizes, type MeasureItem } from "./measure";
import type { Metrics, Size } from "./shapes";

const same = (a: LabelSizes, b: LabelSizes) => JSON.stringify(a) === JSON.stringify(b);

/**
 * What the measure layer reports for one item. A node label's block is `w-max`
 * capped by its rung, so once its text wraps the block is exactly as wide as the
 * rung (shrink-to-fit), not as its widest line. The RichText span inside it is:
 * an inline's offsetWidth spans all its lines, transforms ignored. Display maths
 * is a block inside that span, so there the block's width is kept. The height is
 * always the block's, which counts whole line heights.
 */
export function measuredSize(box: HTMLElement, item: MeasureItem): Size {
  const inner = box.firstElementChild;
  const tight =
    item.kind === "node" &&
    inner instanceof HTMLElement &&
    inner.querySelector(".katex-display") === null
      ? inner.offsetWidth
      : 0;
  return { w: tight > 0 ? tight : box.offsetWidth, h: box.offsetHeight };
}

/**
 * The labels' sizes: estimated on the first render, measured before paint. A
 * label that measures 0 (jsdom, or a lesson hidden with `display: none`) keeps
 * its estimate, and the layer is measured again once the fonts are ready and
 * when the board first gets a width.
 */
export function useLabelSizes(
  g: Graph,
  items: readonly MeasureItem[],
  m: Metrics,
  container: RefObject<HTMLElement | null>,
): { sizes: LabelSizes; layerRef: RefObject<HTMLDivElement | null> } {
  const layerRef = useRef<HTMLDivElement>(null);
  const key = useMemo(() => sizesKey(items, m), [items, m]);
  const estimate = useMemo(() => labelSizes(g, items, [], m).sizes, [g, items, m]);
  const [measured, setMeasured] = useState<{
    key: string;
    sizes: LabelSizes;
    estimated: boolean;
  } | null>(null);
  const [tick, setTick] = useState(0);

  useLayoutEffect(() => {
    const layer = layerRef.current;
    if (!layer) return;
    const boxes = Array.from(layer.children) as HTMLElement[];
    const raw = items.map((item, i): Size | null => {
      const box = boxes[i];
      return box ? measuredSize(box, item) : null;
    });
    const next = { key, ...labelSizes(g, items, raw, m) };
    setMeasured((prev) =>
      prev &&
      prev.key === next.key &&
      prev.estimated === next.estimated &&
      same(prev.sizes, next.sizes)
        ? prev
        : next,
    );
  }, [g, items, m, key, tick]);

  useEffect(() => {
    let live = true;
    void document.fonts?.ready?.then(() => {
      if (live) setTick((t) => t + 1);
    });
    return () => {
      live = false;
    };
  }, []);

  const estimated = measured?.estimated ?? true;
  useEffect(() => {
    const element = container.current;
    if (!estimated || !element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      if ((entry?.contentRect.width ?? 0) > 0) setTick((t) => t + 1);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [estimated, container]);

  const sizes = measured && measured.key === key ? measured.sizes : estimate;
  return { sizes, layerRef };
}
