import { cn } from "@/lib/utils";
import { RichText } from "../board-blocks";
import { Math as Tex } from "../math";
import { anchorTransform, type Flow, type LabelPart, type PlacedLabel } from "./labels";

/**
 * Every text a figure writes, as HTML over its SVG: a `$…$` label is typeset by
 * KaTeX (trust: false) like the rest of the board, and Célestin's strings reach the
 * DOM only as React text. Drawings are pixel-wide, so SVG units are CSS pixels
 * and the layer lines up with the geometry exactly.
 *
 * `w-max` keeps each label one line wide wherever it is anchored: without it an
 * absolutely placed box near the right edge would shrink to the room left and
 * wrap at every space. The layer is aria-hidden: the figure's description says it.
 */

function Part({ part }: { part: LabelPart }) {
  switch (part.kind) {
    case "tex":
      return <Tex tex={part.text} />;
    case "rich":
      return <RichText text={part.text} />;
    case "plain":
      return <span>{part.text}</span>;
  }
}

export function LabelLayer({ labels, flows = [] }: { labels: PlacedLabel[]; flows?: Flow[] }) {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 text-xs leading-none text-foreground"
    >
      {labels.map((label) => (
        <span
          key={label.key}
          className={cn("absolute w-max whitespace-nowrap", label.className)}
          style={{ left: label.x, top: label.y, transform: anchorTransform(label.dir) }}
        >
          {label.parts.map((part, i) => (
            <Part key={i} part={part} />
          ))}
        </span>
      ))}
      {flows.map((flow) => (
        <div
          key={flow.key}
          className={cn(
            "absolute flex items-center justify-center gap-x-1.5 leading-[18px]",
            flow.column ? "flex-col flex-nowrap" : "flex-wrap content-center",
          )}
          style={{ left: flow.left, top: flow.top, width: flow.width, height: flow.height }}
        >
          {flow.items.map((item, i) => (
            <span key={i} className="w-max shrink-0 whitespace-nowrap">
              <RichText text={item} />
            </span>
          ))}
        </div>
      ))}
    </div>
  );
}
