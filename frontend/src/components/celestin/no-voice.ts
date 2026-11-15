import type { VoiceControls } from "@/components/celestin/use-voice-session";

/** The voice controls of a mode without voice (a révision, spec 020 D5): never on, never
 *  supported. A screen that passes no `voice` to the tutor column gets these, and no telephone. */
export const NO_VOICE: VoiceControls = {
  phase: "off",
  muted: false,
  capAt: null,
  supported: false,
  start: async () => {},
  stop: () => {},
  toggleMute: () => {},
  sendText: () => {},
};
