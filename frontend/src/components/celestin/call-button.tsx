import { Phone, PhoneOff } from "lucide-react";

import type { SessionStatus } from "@/components/celestin/use-tutor-session";
import type { VoiceControls } from "@/components/celestin/use-voice-session";
import { cn } from "@/lib/utils";
import { m } from "@/paraglide/messages";

/**
 * The telephone: calling Célestin opens the real-time, two-way voice session; hanging up ends it. It is not
 * the composer's microphone, which only dictates a written message. Beside his name on a desktop, beside his
 * caption on a phone.
 */
export function CallButton({
  voice,
  status,
  className,
}: {
  voice: VoiceControls;
  status: SessionStatus;
  className?: string;
}) {
  const base =
    "inline-flex shrink-0 items-center justify-center rounded-md transition-colors disabled:opacity-40";
  if (voice.phase !== "off") {
    return (
      <button
        type="button"
        onClick={voice.stop}
        title={m.voice_end()}
        aria-label={m.voice_end()}
        className={cn(
          base,
          "bg-destructive/10 text-destructive hover:bg-destructive/20",
          className,
        )}
      >
        <PhoneOff className="size-4" />
      </button>
    );
  }
  if (!voice.supported) {
    return (
      <button
        type="button"
        title={m.voice_talk_soon()}
        aria-label={m.voice_talk_soon()}
        className={cn(
          base,
          "text-muted-foreground hover:bg-secondary hover:text-foreground",
          className,
        )}
      >
        <Phone className="size-4" />
      </button>
    );
  }
  return (
    <button
      type="button"
      onClick={() => void voice.start()}
      disabled={status === "streaming"}
      title={m.voice_talk()}
      aria-label={m.voice_talk()}
      className={cn(
        base,
        "text-muted-foreground hover:bg-secondary hover:text-foreground",
        className,
      )}
    >
      <Phone className="size-4" />
    </button>
  );
}
