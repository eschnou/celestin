import { describe, expect, it, vi } from "vitest";
import {
  defaultFetchSdp,
  VoiceSession,
  VoiceSessionError,
  type VoiceSessionDeps,
} from "../session";

const CALLS = "https://api.openai.com/v1/realtime/calls";

class FakeTrack {
  enabled = true;
  stopped = false;
  kind = "audio";
  stop() {
    this.stopped = true;
  }
}

class FakeStream {
  constructor(readonly tracks: FakeTrack[]) {}
  getAudioTracks() {
    return this.tracks;
  }
  getTracks() {
    return this.tracks;
  }
}

class FakeChannel {
  readyState: "connecting" | "open" | "closed" = "connecting";
  sent: string[] = [];
  onmessage: ((e: { data: string }) => void) | null = null;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.readyState = "closed";
  }
  open() {
    this.readyState = "open";
    this.onopen?.();
  }
}

class FakePeer {
  log: string[] = [];
  channel = new FakeChannel();
  connectionState = "new";
  ontrack: ((e: { streams: unknown[]; track: unknown }) => void) | null = null;
  onconnectionstatechange: (() => void) | null = null;
  closed = false;
  constructor(private readonly openOnAnswer = true) {}
  addTrack(track: unknown) {
    this.log.push("addTrack");
    void track;
  }
  createDataChannel(label: string) {
    this.log.push(`createDataChannel:${label}`);
    return this.channel;
  }
  async createOffer() {
    this.log.push("createOffer");
    return { type: "offer", sdp: "OFFER" };
  }
  async setLocalDescription() {
    this.log.push("setLocalDescription");
  }
  async setRemoteDescription(desc: { sdp: string }) {
    this.log.push(`setRemoteDescription:${desc.sdp}`);
    if (this.openOnAnswer) queueMicrotask(() => this.channel.open());
  }
  close() {
    this.closed = true;
  }
}

function setup(opts: { openOnAnswer?: boolean; sdpFails?: boolean } = {}) {
  const peer = new FakePeer(opts.openOnAnswer ?? true);
  const track = new FakeTrack();
  const audioEl = { srcObject: null } as unknown as HTMLAudioElement;
  const fetchSdp = vi.fn(async (offer: string, secret: string, _callsUrl: string) => {
    if (opts.sdpFails) throw new VoiceSessionError("sdp", "401");
    return `ANSWER(${offer},${secret})`;
  });
  const mic = new FakeStream([track]) as unknown as MediaStream;
  const deps: VoiceSessionDeps = {
    createPeer: () => peer as unknown as RTCPeerConnection,
    audioEl,
    fetchSdp,
    openTimeoutMs: 20,
  };
  const events: unknown[] = [];
  const closes: string[] = [];
  const session = new VoiceSession(
    deps,
    (e) => events.push(e),
    (r) => closes.push(r),
  );
  return { session, peer, track, audioEl, fetchSdp, events, closes, mic };
}

describe("VoiceSession", () => {
  it("connects in the documented order and posts the offer with the secret", async () => {
    const { session, peer, fetchSdp, mic } = setup();
    await session.connect("ek_1", mic, CALLS);
    expect(peer.log).toEqual([
      "addTrack",
      "createDataChannel:oai-events",
      "createOffer",
      "setLocalDescription",
      "setRemoteDescription:ANSWER(OFFER,ek_1)",
    ]);
    expect(fetchSdp).toHaveBeenCalledWith("OFFER", "ek_1", CALLS);
    expect(session.open).toBe(true);
  });

  it("wires the remote track to the audio element and parses channel messages", async () => {
    const { session, peer, audioEl, events, mic } = setup();
    await session.connect("ek", mic, CALLS);
    const stream = { id: "remote" };
    peer.ontrack?.({ streams: [stream], track: {} });
    expect(audioEl.srcObject).toBe(stream);
    peer.channel.onmessage?.({ data: '{"type":"response.created","response":{"id":"r"}}' });
    peer.channel.onmessage?.({ data: "garbage" });
    expect(events).toEqual([{ type: "response.created", response: { id: "r" } }]);
  });

  it("sends JSON over the channel and refuses once closed", async () => {
    const { session, peer, mic } = setup();
    await session.connect("ek", mic, CALLS);
    session.send({ type: "response.create" });
    expect(peer.channel.sent).toEqual(['{"type":"response.create"}']);
    session.close();
    expect(() => session.send({ type: "response.create" })).toThrow();
  });

  it("mute toggles the track without stopping it", async () => {
    const { session, track, mic } = setup();
    await session.connect("ek", mic, CALLS);
    session.setMuted(true);
    expect(track.enabled).toBe(false);
    session.setMuted(false);
    expect(track.enabled).toBe(true);
    expect(track.stopped).toBe(false);
  });

  it("close stops the mic, closes peer and channel, reports once", async () => {
    const { session, peer, track, closes, audioEl, mic } = setup();
    await session.connect("ek", mic, CALLS);
    session.close();
    session.close();
    expect(track.stopped).toBe(true);
    expect(peer.closed).toBe(true);
    expect(peer.channel.readyState).toBe("closed");
    expect(audioEl.srcObject).toBeNull();
    expect(closes).toEqual(["local"]);
  });

  it("a remote channel close is reported as remote", async () => {
    const { session, peer, closes, mic } = setup();
    await session.connect("ek", mic, CALLS);
    peer.channel.onclose?.();
    expect(closes).toEqual(["remote"]);
  });

  it("a failed peer connection is reported as failed", async () => {
    const { session, peer, closes, mic } = setup();
    await session.connect("ek", mic, CALLS);
    peer.connectionState = "failed";
    peer.onconnectionstatechange?.();
    expect(closes).toEqual(["failed"]);
  });

  it("an SDP failure tears down and rethrows", async () => {
    const { session, peer, track, closes, mic } = setup({ sdpFails: true });
    await expect(session.connect("ek", mic, CALLS)).rejects.toMatchObject({ code: "sdp" });
    expect(track.stopped).toBe(true);
    expect(peer.closed).toBe(true);
    expect(closes).toEqual(["local"]);
  });

  it("a channel that never opens times out", async () => {
    const { session, closes, mic } = setup({ openOnAnswer: false });
    await expect(session.connect("ek", mic, CALLS)).rejects.toMatchObject({ code: "timeout" });
    expect(closes).toEqual(["local"]);
  });
});

describe("defaultFetchSdp", () => {
  it("posts the offer to the URL the backend gave, with the secret as the bearer", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue({ ok: true, status: 201, text: async () => "ANSWER" });
    vi.stubGlobal("fetch", fetchMock);
    try {
      const answer = await defaultFetchSdp("OFFER", "ek_1", "https://rt.example/v1/realtime/calls");
      expect(answer).toBe("ANSWER");
      const [url, init] = fetchMock.mock.calls[0]!;
      expect(url).toBe("https://rt.example/v1/realtime/calls");
      expect(init.headers).toMatchObject({
        Authorization: "Bearer ek_1",
        "Content-Type": "application/sdp",
      });
      expect(init.body).toBe("OFFER");
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("raises an sdp error when the server refuses the offer", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 401, text: async () => "" }),
    );
    try {
      await expect(
        defaultFetchSdp("O", "s", "http://localhost:8000/v1/realtime/calls"),
      ).rejects.toMatchObject({
        code: "sdp",
      });
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
