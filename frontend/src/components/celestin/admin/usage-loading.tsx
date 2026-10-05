import { muted } from "@/components/celestin/styles";
import { cn } from "@/lib/utils";
import { m } from "@/paraglide/messages";

/** Shown while a query has nothing yet (a refetch keeps the previous data on screen, dimmed). */
export function Loading() {
  return (
    <p role="status" className={cn(muted, "mt-4")}>
      {m.usage_loading()}
    </p>
  );
}
