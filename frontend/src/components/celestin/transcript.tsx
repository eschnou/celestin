import { memo, useEffect, useState } from "react";
import { AudioLines } from "lucide-react";
import celestinMark from "@/assets/celestin-mark.svg";
import { useCourseLanguage } from "@/lib/course-language";
import { cn } from "@/lib/utils";
import { m } from "@/paraglide/messages";
import { getLocale } from "@/paraglide/runtime";
import { RichText } from "./board-blocks";
import type { TranscriptEntry } from "@/lib/tutor/types";

const mmss = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

/** Ticks on its own, so the rest of the column does not re-render every second. */
export function Countdown({ capAt }: { capAt: number }) {
  const left = () => Math.max(0, Math.round((capAt - Date.now()) / 1000));
  const [remaining, setRemaining] = useState(left);
  useEffect(() => {
    const timer = setInterval(() => setRemaining(left()), 1000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [capAt]);
  return (
    <span className="tabular-nums" title={m.voice_time_left()}>
      · {mmss(remaining)}
    </span>
  );
}

export const Entry = memo(function Entry({
  entry,
  onShowBoard,
}: {
  entry: TranscriptEntry;
  onShowBoard: (i: number) => void;
}) {
  const language = useCourseLanguage();
  if (entry.role === "marker") {
    const clickable = entry.boardIndex !== null;
    return (
      <p className="flex items-center gap-2 text-[11px] tracking-wide text-muted-foreground">
        <span className="h-px flex-1 bg-border" />
        <button
          type="button"
          disabled={!clickable}
          onClick={() => clickable && onShowBoard(entry.boardIndex as number)}
          className={cn("rounded px-1", clickable && "hover:text-foreground hover:underline")}
        >
          → {entry.text}
        </button>
        <span className="h-px flex-1 bg-border" />
      </p>
    );
  }

  if (entry.role === "learner") {
    return (
      <p
        lang={language}
        className="ml-auto w-fit max-w-[85%] rounded-lg rounded-br-sm bg-primary px-3 py-2 text-sm whitespace-pre-wrap text-primary-foreground"
      >
        {entry.spoken && <SpokenMark className="text-primary-foreground/80" />}
        {/* Her own words, but an answer picked on the board carries $…$ (002 R8.3). */}
        <RichText text={entry.text} />
      </p>
    );
  }

  if (entry.role === "error") {
    const signIn = entry.code === "not_authenticated";
    return (
      <p className="rounded-lg border-l-4 border-destructive bg-destructive/10 px-3 py-2 text-sm">
        {entry.text}
        {signIn && (
          <>
            {" "}
            <a
              href={`/login?redirect=${encodeURIComponent(location.pathname)}`}
              className="font-semibold underline"
            >
              {m.auth_sign_in()}
            </a>
          </>
        )}
      </p>
    );
  }

  return (
    <div className="flex max-w-[92%] gap-2.5">
      <img src={celestinMark} alt="" className="mt-0.5 size-6 shrink-0" />
      <p lang={language} className="text-sm leading-relaxed text-foreground">
        {entry.spoken && <SpokenMark className="text-muted-foreground" />}
        {/* The tutor writes maths inline, the same way it does on the board. */}
        <RichText text={entry.text} />
        {entry.interrupted && (
          <span lang={getLocale()} className="ml-1 text-xs text-muted-foreground italic">
            {m.lesson_interrupted()}
          </span>
        )}
      </p>
    </div>
  );
});

/** Marks an entry that was said rather than written (003 R4.2). */
function SpokenMark({ className }: { className?: string }) {
  return (
    <AudioLines
      className={cn("mr-1 inline size-3.5 align-[-2px]", className)}
      role="img"
      aria-label={m.voice_spoken()}
      lang={getLocale()}
    />
  );
}
