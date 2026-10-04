import type { RefObject } from "react";
import { RichText } from "../board-blocks";
import { LADDER, type MeasureItem } from "./measure";
import type { Metrics } from "./shapes";

/**
 * Measures every label once, hidden, in the fonts it is drawn with.
 *
 * The layer is a 0 × 0 clipped box: it adds nothing to the board's scroll height,
 * and its children still lay out. Each node label is a `w-max min-w-min` block
 * capped by its rung, so an unbreakable word or formula still reports its real
 * width; `measuredSize` reads the width of its widest line from the RichText span
 * inside (the block itself is as wide as the rung once the text wraps).
 */
export function MeasureLayer({
  items,
  m,
  layerRef,
}: {
  items: readonly MeasureItem[];
  m: Metrics;
  layerRef: RefObject<HTMLDivElement | null>;
}) {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none invisible absolute top-0 left-0 h-0 w-0 overflow-hidden"
    >
      <div ref={layerRef}>
        {items.map((item, i) =>
          item.kind === "node" ? (
            <div
              key={i}
              className="w-max min-w-min text-left"
              style={{
                maxWidth: LADDER[item.rung],
                fontSize: m.font,
                lineHeight: `${m.line}px`,
              }}
            >
              <RichText text={item.text} />
            </div>
          ) : (
            <div
              key={i}
              className="w-max font-semibold whitespace-nowrap"
              style={{ fontSize: m.edgeFont, lineHeight: `${m.edgeLine}px` }}
            >
              <RichText text={item.text} />
            </div>
          ),
        )}
      </div>
    </div>
  );
}
