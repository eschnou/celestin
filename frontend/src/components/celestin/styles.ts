/** Class names shared by the course pages, so cards and buttons look alike everywhere. */

export const panel = "rounded-xl border border-border bg-background p-4 shadow-sheet";
export const card = `flex h-full flex-col ${panel}`;
export const button =
  "inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-semibold transition-opacity hover:opacity-90 disabled:opacity-50";
export const primary = `${button} bg-primary text-primary-foreground`;
export const secondary = `${button} border border-border bg-card`;
export const danger = `${button} border border-destructive/40 bg-card text-destructive`;
export const field =
  "w-full rounded-md border border-input bg-card px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/25";
export const label = "mb-1 block text-sm font-semibold";
export const fieldError = "mt-1 text-xs text-destructive";
export const muted = "text-sm text-muted-foreground";
/** A message box: something went wrong, something to know, something that needs doing. */
const box = "rounded-md border-l-4 px-3 py-2 text-sm";
export const alertBox = `${box} border-destructive bg-destructive/10`;
export const noticeBox = `${box} border-primary bg-primary/10`;
export const warningBox = `${box} border-warning bg-warning/10`;
/** A borderless icon button, as in the tutor column's header. */
export const iconButton =
  "inline-flex size-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-50";
