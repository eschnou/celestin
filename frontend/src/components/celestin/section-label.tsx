/** A section's number and its kind badge, as the chapter map and the cahier head a section. */

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
