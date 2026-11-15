/** A section's number and its kind badge, as the chapter map and the cahier head a section;
 *  and the dot the map and the strip mark a section with. */

import { KIND_LABEL } from "@/lib/tutor/labels";
import type { SectionOverview } from "@/lib/tutor/types";
import { cn } from "@/lib/utils";

/** The number takes the size the caller gives; the badge is always small. `children` follow
 *  the badge (the map's state, for a screen reader). */
export function SectionLabel({
  section,
  className,
  children,
}: {
  section: Pick<SectionOverview, "index" | "kind">;
  className?: string;
  children?: React.ReactNode;
}) {
  return (
    <span className={cn("flex items-center gap-1.5 text-muted-foreground tabular-nums", className)}>
      <span>{section.index}</span>
      <span className="rounded border border-border px-1 text-[11px] font-semibold tracking-wide uppercase">
        {KIND_LABEL[section.kind]()}
      </span>
      {children}
    </span>
  );
}

/** The ring of a section not yet finished: the one worked (filled), the one Célestin
 *  proposes (spec 019: the primary at half strength), any other (plain). The map and the
 *  strip draw it; the caller gives the size. */
const RING = {
  active: "border-primary bg-primary/20",
  available: "border-primary/50 bg-card",
  open: "border-border bg-card",
} as const;

export function SectionRing({
  state,
  className,
}: {
  state: keyof typeof RING;
  className?: string;
}) {
  return <span className={cn("shrink-0 rounded-full border-2", RING[state], className)} />;
}
