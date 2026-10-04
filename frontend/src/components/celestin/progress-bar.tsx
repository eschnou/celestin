import { cn } from "@/lib/utils";

/** A thin bar for how far along a chapter is. `label` is what a screen reader hears. */
export function ProgressBar({
  done,
  total,
  label,
  tone = "primary",
  className,
}: {
  done: number;
  total: number;
  label: string;
  tone?: "primary" | "success";
  className?: string;
}) {
  const percent = total > 0 ? Math.min(100, Math.max(0, (done / total) * 100)) : 0;
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={total}
      aria-valuenow={done}
      className={cn("h-1.5 overflow-hidden rounded-full bg-foreground/10", className)}
    >
      <div
        className={cn("h-full rounded-full", tone === "success" ? "bg-success" : "bg-primary")}
        style={{ width: `${percent}%` }}
      />
    </div>
  );
}
