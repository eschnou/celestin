/**
 * One WebRTC call to the Realtime API (003 design 3.10). Owns the peer
 * connection, the microphone and the data channel; knows nothing about the
 * reducer. Every browser object is injectable so the sequence is testable.
 */

import { parseServerEvent, type RealtimeClientEvent, type RealtimeServerEvent } from "./realtime";

export const OPEN_TIMEOUT_MS = 10_000;

export type VoiceSessionDeps = {
  createPeer: () => RTCPeerConnection;
  audioEl: HTMLAudioElement;
  /** Posts the offer to the voice server's calls URL (the one the backend gave with the session). */
  fetchSdp: (offerSdp: string, secret: string, callsUrl: string) => Promise<string>;
  openTimeoutMs?: number;
};

export type CloseReason = "remote" | "local" | "failed";

export class VoiceSessionError extends Error {
  constructor(
    readonly code: "sdp" | "ice" | "timeout",
    message: string,
  ) {
    super(message);
  }
}

export async function defaultFetchSdp(
  offerSdp: string,
  secret: string,
  callsUrl: string,
): Promise<string> {
  const res = await fetch(callsUrl, {
    method: "POST",
    headers: { Authorization: `Bearer ${secret}`, "Content-Type": "application/sdp" },
    body: offerSdp,
  });
  if (!res.ok) throw new VoiceSessionError("sdp", `SDP exchange failed (${res.status})`);
  return res.text();
}

export function browserDeps(audioEl: HTMLAudioElement): VoiceSessionDeps {
  return { createPeer: () => new RTCPeerConnection(), audioEl, fetchSdp: defaultFetchSdp };
}

/** The one place the audio constraints live. */
export function requestMic(): Promise<MediaStream> {
  return navigator.mediaDevices.getUserMedia({ audio: true });
}

/** Dev aid: `localStorage.celestinVoiceRecord = "1"` logs every server event as a
 *  `celestin.voice` console line, one JSON per line, to turn into a bridge fixture. */
function recording(): boolean {
  try {
    return (
      typeof localStorage !== "undefined" && localStorage.getItem("celestinVoiceRecord") === "1"
    );
  } catch {
    return false;
  }
}

export function voiceSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.RTCPeerConnection === "function" &&
    typeof navigator?.mediaDevices?.getUserMedia === "function"
  );
}

export class VoiceSession {
  private pc: RTCPeerConnection | null = null;
  private dc: RTCDataChannel | null = null;
  private mic: MediaStream | null = null;
  private closed = false;
  private record = false;

  constructor(
    private readonly deps: VoiceSessionDeps,
    private readonly onEvent: (event: RealtimeServerEvent) => void,
    private readonly onClose: (reason: CloseReason) => void,
  ) {}

  /** The peer, the mic track, the channel, then the offer. The caller owns the
   *  permission prompt; the session owns the stream from here on. */
  async connect(secret: string, mic: MediaStream, callsUrl: string): Promise<void> {
    this.mic = mic;
    this.record = recording();
    const pc = this.deps.createPeer();
    this.pc = pc;
    pc.ontrack = (e) => {
      const stream = e.streams[0] ?? new MediaStream([e.track]);
      this.deps.audioEl.srcObject = stream;
    };
    for (const track of mic.getAudioTracks()) pc.addTrack(track, mic);

    const dc = pc.createDataChannel("oai-events");
    this.dc = dc;
    dc.onmessage = (e) => {
      const raw = typeof e.data === "string" ? e.data : "";
      if (this.record) console.log("celestin.voice", raw);
      const event = parseServerEvent(raw);
      if (event) this.onEvent(event);
    };
    dc.onclose = () => this.finish("remote");
    pc.onconnectionstatechange = () => {
      if (pc.connectionState === "failed" || pc.connectionState === "closed") this.finish("failed");
    };

    try {
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      const answer = await this.deps.fetchSdp(offer.sdp ?? "", secret, callsUrl);
      await pc.setRemoteDescription({ type: "answer", sdp: answer });
      await this.waitOpen(dc);
    } catch (error) {
      this.close();
      throw error instanceof VoiceSessionError
        ? error
        : new VoiceSessionError("ice", error instanceof Error ? error.message : "connect failed");
    }
  }

  send(event: RealtimeClientEvent): void {
    if (!this.dc || this.dc.readyState !== "open") throw new Error("voice channel is not open");
    this.dc.send(JSON.stringify(event));
  }

  setMuted(muted: boolean): void {
    for (const track of this.mic?.getAudioTracks() ?? []) track.enabled = !muted;
  }

  get open(): boolean {
    return this.dc?.readyState === "open";
  }

  /** Idempotent. Stops the mic, closes the channel and the peer, reports once. */
  close(): void {
    this.finish("local");
  }

  private finish(reason: CloseReason): void {
    if (this.closed) return;
    this.closed = true;
    for (const track of this.mic?.getTracks() ?? []) track.stop();
    this.mic = null;
    if (this.dc) {
      this.dc.onclose = null;
      this.dc.close();
    }
    if (this.pc) {
      this.pc.onconnectionstatechange = null;
      this.pc.close();
    }
    this.deps.audioEl.srcObject = null;
    this.onClose(reason);
  }

  private waitOpen(dc: RTCDataChannel): Promise<void> {
    if (dc.readyState === "open") return Promise.resolve();
    const timeoutMs = this.deps.openTimeoutMs ?? OPEN_TIMEOUT_MS;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new VoiceSessionError("timeout", "voice channel did not open")),
        timeoutMs,
      );
      dc.onopen = () => {
        clearTimeout(timer);
        resolve();
      };
    });
  }
}
