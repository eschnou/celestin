import { describe, expect, it } from "vitest";
import { DEFAULT_VAD, Vad, type StopReason } from "../vad";

const TICK = 50;
const ROOM = 0.004;
const VOICE = 0.08;

/** Feeds the VAD `[ms, rms]` stretches at 50 ms a tick; the first stop it gives, and when. */
function run(segments: [number, number][], config = DEFAULT_VAD) {
  const vad = new Vad(0, config);
  let now = 0;
  for (const [ms, rms] of segments) {
    for (let t = 0; t < ms; t += TICK) {
      now += TICK;
      const verdict = vad.push(rms, now);
      if (verdict.stop) return { stop: verdict.stop as StopReason, at: now, vad };
    }
  }
  return { stop: null, at: now, vad };
}

describe("Vad", () => {
  it("ends the take a pause after a phrase", () => {
    const { stop, at, vad } = run([
      [500, ROOM],
      [2000, VOICE],
      [5000, ROOM],
    ]);
    expect(stop).toBe("silence");
    // 2 s of speech earns 1300 + 2000 × 0.15 = 1600 ms of patience.
    expect(vad.patienceMs).toBeCloseTo(1600 + 0, -2);
    expect(at).toBeGreaterThanOrEqual(2500 + 1300);
    expect(at).toBeLessThanOrEqual(2500 + 1800);
    expect(vad.heard).toBe(true);
  });

  it("gives a long phrase more room to think than a short one", () => {
    const short = run([
      [500, ROOM],
      [1000, VOICE],
      [5000, ROOM],
    ]);
    const long = run([
      [500, ROOM],
      [12_000, VOICE],
      [5000, ROOM],
    ]);
    expect(long.vad.patienceMs).toBeGreaterThan(short.vad.patienceMs);
    expect(long.vad.patienceMs).toBeLessThanOrEqual(DEFAULT_VAD.silenceMaxMs);
  });

  it("does not cut a phrase at a short pause", () => {
    const { stop } = run([
      [500, ROOM],
      [1500, VOICE],
      [900, ROOM], // a breath, under the patience
      [1500, VOICE],
      [200, ROOM],
    ]);
    expect(stop).toBeNull();
  });

  it("gives up when nothing is said", () => {
    const { stop, at, vad } = run([[20_000, ROOM]]);
    expect(stop).toBe("no-speech");
    expect(at).toBeGreaterThanOrEqual(DEFAULT_VAD.noSpeechMs);
    expect(vad.heard).toBe(false);
  });

  it("does not take a cough for speech", () => {
    const { stop, vad } = run([
      [500, ROOM],
      [150, VOICE], // too short: forgotten
      [20_000, ROOM],
    ]);
    expect(stop).toBe("no-speech");
    expect(vad.heard).toBe(false);
  });

  it("measures a noisy room first, and wants speech clearly above it", () => {
    const noise = 0.03; // a fan: above the absolute minimum
    const { stop: noisy } = run([
      [500, noise],
      [3000, noise * 1.5], // not 3 × the floor: still the room
      [10_000, noise],
    ]);
    expect(noisy).toBe("no-speech");
    const { stop: spoken } = run([
      [500, noise],
      [2000, noise * 4],
      [5000, noise],
    ]);
    expect(spoken).toBe("silence");
  });

  it("follows a room that gets louder while nobody speaks", () => {
    const vad = new Vad(0);
    let now = 0;
    const feed = (ms: number, rms: number) => {
      for (let t = 0; t < ms; t += TICK) vad.push(rms, (now += TICK));
    };
    feed(500, 0.004);
    const before = vad.threshold;
    feed(4000, 0.008); // the fan comes on, under the threshold at first
    expect(vad.threshold).toBeGreaterThanOrEqual(before);
  });

  it("stops at the cap even in the middle of a phrase", () => {
    const { stop, at } = run([
      [500, ROOM],
      [120_000, VOICE],
    ]);
    expect(stop).toBe("max");
    expect(at).toBeGreaterThanOrEqual(DEFAULT_VAD.maxMs);
    expect(at).toBeLessThan(DEFAULT_VAD.maxMs + 200);
  });

  it("does not stop on a quiet word inside a phrase (a lower bar to stay than to enter)", () => {
    const { stop } = run([
      [500, ROOM],
      [1000, VOICE],
      [3000, 0.009], // soft: under the bar to start (0.012) but over the bar to stay (60 % of it)
      [200, VOICE],
    ]);
    expect(stop).toBeNull();
  });
});
