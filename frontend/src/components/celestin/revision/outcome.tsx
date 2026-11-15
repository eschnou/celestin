/** A self-assessment as the révision shows it (spec 020): a small chip whose word carries the
 *  meaning, its colour only repeating it, in the board's status palette. */

import { tone } from "@/components/celestin/styles";
import { OUTCOME_LABEL } from "@/lib/tutor/labels";
import type { RevisionOutcome } from "@/lib/tutor/types";
import { cn } from "@/lib/utils";

const OUTCOME_TONE: Record<RevisionOutcome, string> = {
  solid: tone.success,
  shaky: tone.warning,
  todo: tone.danger,
};

const OUTCOME_DOT: Record<RevisionOutcome, string> = {
  solid: "bg-success",
  shaky: "bg-warning",
  todo: "bg-destructive",
};

/** The dot a quick reply leads with: the same colour as the chip it will become. */
export function OutcomeDot({ outcome }: { outcome: RevisionOutcome }) {
  return <span className={cn("size-2 rounded-full", OUTCOME_DOT[outcome])} aria-hidden />;
}

export function OutcomeChip({ outcome }: { outcome: RevisionOutcome }) {
  return (
    <span
      data-outcome={outcome}
      className={cn("rounded px-1.5 py-0.5 text-[11px] font-semibold", OUTCOME_TONE[outcome])}
    >
      {OUTCOME_LABEL[outcome]()}
    </span>
  );
}
