import { memo, useId, useMemo, useRef } from "react";
import type { FigureBlock } from "@/lib/tutor/types";
import { m } from "@/paraglide/messages";
import { getLocale } from "@/paraglide/runtime";
import { RichText } from "../board-blocks";
import { useNotation } from "../charts/format";
import { useWidth } from "../charts/use-width";
import { ariaLabel, describe } from "./describe";
import { NumberLineDrawing } from "./number-line";
import { PlaneDrawing } from "./plane";
import { sanitise, type CleanFigure } from "./sanitise";
import { SetDrawing } from "./sets";

/**
 * A figure on the board: plane geometry, a number line or a diagram of sets.
 * Célestin gives points and relations; this draws them to scale and writes the
 * notation itself (decimal comma, `A(2 ; 3)`, `]−∞ ; 2]`), coordinates and
 * intervals only when Célestin sets `show_values`.
 *
 * Nothing on a figure reacts to the pointer: no handler, no tooltip, no
 * `<title>`, so a reading exercise shows exactly what is drawn. Stored cards
 * are cleaned once here (`sanitise`), and anything unusable is « Figure vide »
 * rather than an error on the board.
 */

function Drawing({ fig, width, uid }: { fig: CleanFigure; width: number; uid: string }) {
  switch (fig.kind) {
    case "plane":
      return <PlaneDrawing fig={fig} width={width} uid={uid} />;
    case "number_line":
      return <NumberLineDrawing fig={fig} width={width} uid={uid} />;
    case "sets":
      return <SetDrawing fig={fig} width={width} uid={uid} />;
  }
}

export const FigureView = memo(function FigureView({ block }: { block: FigureBlock }) {
  const ref = useRef<HTMLDivElement>(null);
  const width = useWidth(ref);
  const fig = useMemo(() => sanitise((block as { figure?: unknown } | null)?.figure), [block]);
  // Ids for clip paths, masks and patterns: unique per figure, even two on a card.
  const uid = "fig" + useId().replace(/[^A-Za-z0-9_-]/g, "");
  const notation = useNotation();
  const lines = useMemo(() => describe(fig, notation), [fig, notation]);

  return (
    <figure className="rounded-lg border border-border bg-card px-5 py-4">
      <div ref={ref} role="img" aria-label={ariaLabel(fig)} aria-describedby={`${uid}-desc`}>
        {fig ? (
          <Drawing fig={fig} width={width} uid={uid} />
        ) : (
          <p className="py-8 text-center text-sm text-muted-foreground">
            {m.describe_figure_empty()}
          </p>
        )}
      </div>
      {fig?.caption && (
        <figcaption className="mt-3 text-center text-xs text-muted-foreground">
          {/* KaTeX's html is aria-hidden: screen readers get a MathML copy. */}
          <span aria-hidden="true">
            <RichText text={fig.caption} />
          </span>
          <span className="sr-only">
            <RichText text={fig.caption} mathOutput="mathml" />
          </span>
        </figcaption>
      )}
      {/* Our sentences, in the interface language, around the course's notation. */}
      <ul id={`${uid}-desc`} lang={getLocale()} className="sr-only">
        {lines.map((line, i) => (
          <li key={i}>
            <RichText text={line} mathOutput="mathml" />
          </li>
        ))}
      </ul>
    </figure>
  );
});
