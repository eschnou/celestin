import { cn } from "@/lib/utils";

/** A thin bar for how far along a chapter is. `label` is what a screen reader hears.
 *  `skipped` sections (spec 019) count as covered and are drawn apart, after the done ones. */
export function ProgressBar({
  done,
  skipped = 0,
  total,
  label,
  tone = "primary",
  className,
}: {
  done: number;
  skipped?: number;
  total: number;
  label: string;
  tone?: "primary" | "success";
  className?: string;
}) {
  const share = (n: number) => (total > 0 ? Math.min(100, Math.max(0, (n / total) * 100)) : 0);
  const percent = share(done);
  const passed = Math.min(share(skipped), 100 - percent);
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={total}
      aria-valuenow={Math.min(done + skipped, total)}
      className={cn("flex h-1.5 overflow-hidden rounded-full bg-foreground/10", className)}
    >
      <div
        className={cn("h-full rounded-full", tone === "success" ? "bg-success" : "bg-primary")}
        style={{ width: `${percent}%` }}
      />
      {passed > 0 && (
        <div
          data-part="skipped"
          className="h-full rounded-full bg-muted-foreground/40"
          style={{ width: `${passed}%` }}
        />
      )}
    </div>
  );
}
