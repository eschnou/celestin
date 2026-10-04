/**
 * When has the student started, and when has she finished? (dictation)
 *
 * Pure: the recorder feeds it one loudness reading (RMS, 0 to 1) every few tens of milliseconds and gets a
 * verdict back, so the rules are tested without a microphone.
 *
 * - The first moments are the room's noise: they set the floor, and speech is whatever rises clearly above it
 *   (a threshold of 3 × the floor, never below a minimum that a quiet room's hiss cannot reach).
 * - Speech needs a few hundred milliseconds above the threshold to count (a cough, a door, a tap on the glass
 *   are not speech), and a blip shorter than `minSpeechMs` is forgotten.
 * - After speech, a silence ends the take. The silence tolerated grows with what was said: a short phrase is
 *   done after a short pause, a long one gets room to think.
 * - Nothing heard for a while ends the take too (she opened the microphone and said nothing); so does the cap.
 */

export type VadConfig = {
  /** The room's noise is measured over this long, at the start. */
  calibrationMs: number;
  /** Speech is above this many times the floor… */
  speechFactor: number;
  /** …and above this absolute level. */
  minThreshold: number;
  /** Above the threshold this long before it is speech. */
  startMs: number;
  /** Less speech than this in the whole take is not a take. */
  minSpeechMs: number;
  /** The pause that ends a short phrase, and how much more each second said earns, up to the maximum. */
  silenceBaseMs: number;
  silencePerSpeechMs: number;
  silenceMaxMs: number;
  /** Give up when nothing was said this long after the start. */
  noSpeechMs: number;
  /** The longest take. */
  maxMs: number;
};

export const DEFAULT_VAD: VadConfig = {
  calibrationMs: 300,
  speechFactor: 3,
  minThreshold: 0.012,
  startMs: 120,
  minSpeechMs: 350,
  silenceBaseMs: 1300,
  silencePerSpeechMs: 0.15,
  silenceMaxMs: 2500,
  noSpeechMs: 8000,
  maxMs: 60_000,
};

export type StopReason = "silence" | "no-speech" | "max";

export type VadPhase = "calibrating" | "waiting" | "speaking";

export type Verdict = {
  phase: VadPhase;
  /** Set once, when the take should end. */
  stop: StopReason | null;
  /** Whether enough speech has been heard for the take to be worth sending. */
  heard: boolean;
};

export class Vad {
  private floor = 0;
  private floorSamples = 0;
  private last: number;
  private aboveMs = 0;
  private quietMs = 0;
  private speaking = false;
  private speechMs = 0;
  private stopped: StopReason | null = null;

  constructor(
    private readonly startedAt: number,
    private readonly config: VadConfig = DEFAULT_VAD,
  ) {
    this.last = startedAt;
  }

  /** The level above which a reading counts as speech, once the floor is known. */
  get threshold(): number {
    return Math.max(this.config.minThreshold, this.floor * this.config.speechFactor);
  }

  get heard(): boolean {
    return this.speechMs >= this.config.minSpeechMs;
  }

  /** How long she has spoken, in the whole take. */
  get spokenMs(): number {
    return this.speechMs;
  }

  /** The pause that would end the take now. */
  get patienceMs(): number {
    const { silenceBaseMs, silencePerSpeechMs, silenceMaxMs } = this.config;
    return Math.min(silenceMaxMs, silenceBaseMs + this.speechMs * silencePerSpeechMs);
  }

  push(rms: number, now: number): Verdict {
    const elapsed = now - this.startedAt;
    const dt = Math.max(0, now - this.last);
    this.last = now;
    if (this.stopped) return this.verdict("waiting", this.stopped);

    if (elapsed < this.config.calibrationMs) {
      this.floor = (this.floor * this.floorSamples + rms) / (this.floorSamples + 1);
      this.floorSamples += 1;
      return this.verdict("calibrating", null);
    }

    const threshold = this.threshold;
    if (!this.speaking) {
      if (rms > threshold) {
        this.aboveMs += dt;
        if (this.aboveMs >= this.config.startMs) {
          this.speaking = true;
          this.speechMs += this.aboveMs;
          this.quietMs = 0;
        }
      } else {
        this.aboveMs = 0;
        // The room can get louder or quieter: follow it slowly, only while nobody speaks.
        this.floor = this.floor * 0.95 + rms * 0.05;
      }
    } else if (rms > threshold * 0.6) {
      // A lower bar to stay in speech than to enter it, so a soft word does not cut the phrase.
      this.speechMs += dt;
      this.quietMs = 0;
    } else {
      this.quietMs += dt;
      if (this.quietMs >= this.patienceMs) {
        if (this.heard) return this.stop("silence");
        // A blip too short to be speech: forget it and wait again.
        this.speaking = false;
        this.speechMs = 0;
        this.aboveMs = 0;
        this.quietMs = 0;
      }
    }

    if (elapsed >= this.config.maxMs) return this.stop("max");
    if (!this.heard && !this.speaking && elapsed >= this.config.noSpeechMs) {
      return this.stop("no-speech");
    }
    return this.verdict(this.speaking ? "speaking" : "waiting", null);
  }

  private stop(reason: StopReason): Verdict {
    this.stopped = reason;
    return this.verdict(this.speaking ? "speaking" : "waiting", reason);
  }

  private verdict(phase: VadPhase, stop: StopReason | null): Verdict {
    return { phase, stop, heard: this.heard };
  }
}
