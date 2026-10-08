# Voice mode

Talking to Célestin instead of typing (spec 003). Same prompt, same pack, same five tools, same board;
only the channel changes. The browser holds a WebRTC call with a Realtime API server (OpenAI's, or the voice connection's, spec 014:
the session response carries `calls_url` and the browser holds no URL of its own); the backend never touches
audio. Voice is on only when the default connection is OpenAI's or the voice role has a connection of its own:
see [ai-providers.md](./ai-providers.md).

## The shape

```
browser                                         backend                       OpenAI
───────                                         ───────                       ──────
useVoiceSession
  ├─ POST /api/voice/session {history,progress} ─▶ VoiceService ──────────────▶ POST /v1/realtime/client_secrets
  │                                                 · session config            (prompt + pack + tools)
  │  ◀── {secret, seed[], limits, opening} ────────  · seed items
  ├─ VoiceSession: getUserMedia, RTCPeerConnection ─────────────────────────▶ POST /v1/realtime/calls (SDP)
  │      audio ◀──────────────────────────────────────────────────────────────▶ audio
  │      data channel "oai-events" ◀─────────────────────────────────────────▶ JSON events
  ├─ bridge(): Realtime events → TutorEvent  ──▶ useTutorSession.dispatch (the text-mode reducer)
  ├─ on a function call: POST /api/voice/tool ──▶ registry.execute + event_of ─▶ {output, event, progress}
  │      then function_call_output + response.create over the data channel
  └─ on stop: POST /api/voice/usage ───────────▶ a usage ledger row (and a log line with a cost estimate)
```

Three facts drive the design:

- **Instructions and tools are session-level** in the Realtime API. The backend sets them once in
  the client-secret request; the browser cannot widen them. The prior transcript is *seeded* as
  conversation items (built server-side, because replayed `start_section` results need the
  curriculum brief), followed by a `system` item carrying the path state.
- **A function call ends a Realtime response.** The browser answers it and asks for a new response.
  The bridge treats that continuation as the *same* tutor turn: no second `turn.start`, and the
  text `block_id` increments, exactly like a tool round in the text loop. That is what keeps the
  « Étape suivante » button alive after `propose_next_step`.
- **One transcript.** Spoken turns land in the same `entries`/`history` as typed ones (with a
  `spoken` flag on the transcript entry only), so switching back to text posts a valid history to
  `/api/chat`. Verified end to end: voice session → typed message → bridged `display_board` →
  stop → text turn with the whole history.

## Routes

| Route | Body | Returns |
|---|---|---|
| `POST /api/voice/session` | `{course_id, chapter_id, history}` (same as chat), plus `mode` and `conversation_id` in discussion mode | `201` `{session_id, secret, expires_at, model, voice, limits, seed, opening}`, `Cache-Control: no-store` |
| `POST /api/voice/tool` | `{session_id, call_id, name, arguments, course_id, chapter_id, mode}` | `200` `{output, event, progress, state_text}` |
| `POST /api/voice/usage` | `{session_id, reason, duration_s, responses, usage}` | `204`, always (each token total is bounded, a session is stored once, reports are limited per user: see [ai-usage.md](./ai-usage.md)) |

`/tool` is the text loop's tool round as a request: `registry.execute` in a `TurnContext` from the
posted progress, `tool_events.event_of` for the event, `registry.output_of` for what the model reads.
A refusal is `200` with `event: null` and `{"ok": false}` in `output`, never a 4xx. `state_text` is
set after a section tool; the browser injects it as a `system` item before the tool output.

Every voice route requires a signed-in student (spec 004: the session cookie, or the same token as
`Authorization: Bearer …`) who owns the course of a chapter with content (spec 005). The mint limit
(`VOICE_SESSIONS_PER_HOUR`) is per user. Progress for the seed and for the tool endpoint comes from
the student's stored record, and a section tool persists its transition before answering.

## The seed

`VoiceService.seed` maps `history.to_provider_input` (trimming and replay included) onto Realtime
items: user text → `input_text`, assistant text → `output_text` (the API rejects `text`),
`function_call` / `function_call_output` unchanged. Budget: `VOICE_SEED_TOKEN_BUDGET` (12 000 by
default, below the text budget because audio shares the context). On an empty transcript the seed
is the state item only and `opening` is true: the browser requests the first response itself and
Célestin opens the session as in text mode.

## The prompt

`backend/prompts/tutor.fr.md` carries a `<!-- VOICE -->` … `<!-- /VOICE -->` block (« Quand on se
parle à voix haute »: short sentences, announce tools, ask to repeat), and since spec 005 each
subject prompt carries its own (« Les mathématiques à voix haute », « Les sciences à voix haute », « La langue à voix haute », « Le cours à
voix haute »: how formulas, units, chemical formulas, foreign words and dates are said). `prompt_service.render_system_text(..., voice=True)` keeps both
blocks without their markers; `voice=False` drops each block, its markers and the following blank
line, so the text-mode cached prefix never contains them. A test pins the sha256 of the text
rendering for chapter 1 (`tests/fixtures/render/system_text_sha.txt`); regenerate it only for an
intended prompt or content change.

**Course language** (spec 011): the session is built from the chapter's language. The instructions
are the language's prompt files (`tutor.en.md` carries « When we talk out loud »; the English subject
prompts say « x squared », « u sub n », « two point five »), the tools are
`realtime_declarations(mode, language)`, the state text of a path move is in that language, and
`audio.input.transcription.language` is the course's (`"fr"` or `"en"`) — a bias for the
transcriber, not a constraint; the instructions say which language Célestin speaks. The French session
configuration is byte-identical to what it was.

Tool declarations for the Realtime session come from `registry.realtime_declarations(mode)`: the
same list minus `strict`, which the Realtime function-tool schema does not define. In a discussion
that is the two board tools, and `/api/voice/tool` refuses anything else whatever the browser sends
— which matters, because the browser is what names the tool ([discussion.md](./discussion.md)). A test asserts the
two lists are otherwise equal; the text-mode snapshot already pins the bytes.

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `VOICE_ENABLED` | `true` | `false`: `/api/health` reports `voice: false`, the mic stays inert, `/session` answers 503. |
| `VOICE_MODEL` | `gpt-realtime-2.1` | `gpt-realtime-2.1-mini` for the cost comparison. |
| `VOICE_NAME` / `VOICE_SPEED` | `marin` / `1.0` | Speed 0,25–1,5. |
| `VOICE_REASONING_EFFORT` | `low` | Empty string omits the field; set it blank for a model that rejects `reasoning`. |
| `VOICE_TRANSCRIPTION_MODEL` | `gpt-4o-mini-transcribe` | Must be one the session schema lists (see the SDK's `AudioTranscriptionParam`). |
| `VOICE_TURN_DETECTION` | `semantic_vad` | or `server_vad`. Both with `create_response` and `interrupt_response`. |
| `VOICE_MAX_OUTPUT_TOKENS` | `1024` | One spoken turn. |
| `VOICE_SECRET_TTL_S` | `90` | Lifetime of the `ek_` secret; only the SDP exchange needs it. |
| `VOICE_SESSION_MAX_S` / `VOICE_IDLE_S` | `1500` / `180` | Hard cap (countdown in the header) and idle cut-off. Both enforced in the browser. |
| `VOICE_SESSIONS_PER_HOUR` | `6` | Per client IP; `TRUST_PROXY=true` reads `X-Forwarded-For`. |
| `VOICE_SEED_TOKEN_BUDGET` | `12000` | See above. |
| `VOICE_PRICE_*` | published list prices | USD per million tokens, for the cost estimate in the log. |

The session configuration is built in `VoiceService.session_config()`: `output_modalities:
["audio"]`, `parallel_tool_calls: false` (tool calls are executed serially in the browser),
`truncation: "auto"`, `tracing: null`, no audio `format` keys (WebRTC negotiates Opus).

## What a session costs

`voice_usage` is logged at session end (and by `sendBeacon` on page unload) with the six token
totals by modality and `cost_estimate_usd` (the log line only), and stored as one row of the usage ledger
(`ai_usage`, spec 015: [ai-usage.md](./ai-usage.md)) with the user id, the course and chapter the session was minted
for, the model and the folded token totals; the figures are the browser's report, and no cost is stored (Realtime
reports none). The `voice_usage` table is gone. A one-minute check session with two responses and a
silent microphone logged 27 738 input text tokens of which 13 824 cached, 156 output text and 193
output audio tokens: about 0,08 USD, almost all of it the uncached first read of the prompt prefix.
Audio input is billed per token of speech (roughly 600 per minute); expect a 25-minute lesson in
the order of one to two euros until measured otherwise.

## Frontend layout

- `src/lib/tutor/voice/realtime.ts` — the subset of Realtime events the bridge reads, the client
  event builders, `parseServerEvent` (unknown types → `null`).
- `src/lib/tutor/voice/bridge.ts` — pure: `(state, serverEvent) → {state, events, actions}`.
  Tested against `__tests__/fixtures/*.jsonl`; `recorded_tool_round.jsonl` is a real session.
- `src/lib/tutor/voice/session.ts` — `VoiceSession`: mic, peer connection, `oai-events` channel,
  SDP exchange with the ephemeral secret. Every browser object is injectable.
- `src/lib/tutor/voice/client.ts` — the three routes.
- `src/components/celestin/use-voice-session.ts` — the orchestration: phase machine, seed, serial
  tool queue, cap and idle timers, mute, second-tab guard (`BroadcastChannel("celestin.voice")`),
  usage report. Talks to `useTutorSession` through its `handle`.
- `src/components/celestin/call-button.tsx` — the telephone: « Appeler Célestin » starts a session, « Raccrocher »
  ends it. Beside his name on a desktop (`tutor-column.tsx`), beside his caption on a phone (`tutor-caption.tsx`).
- `src/components/celestin/composer.tsx` — during a call the microphone in the composer is the call's mute; typed
  text goes to the call. Outside a call the same microphone is **dictation** (below), not voice.
- `src/components/celestin/tutor-column.tsx` — phase label and countdown, spoken-entry icon.

Two client-internal reducer events, `voice.on` and `voice.off {reason}`, add the markers and set
`state.voice`. They are not part of the SSE contract.

**Recording a session for a fixture:** set `localStorage.celestinVoiceRecord = "1"` and every server
event is logged as a `celestin.voice` console line, one JSON per line. Drop `session.created` (it
carries the whole prompt) before saving.

## Dictation: the composer's microphone

Not the voice call. The microphone in the message field turns a spoken take into **written text in the field**:
she reads it, fixes it and sends it like any message. Talking with Célestin in real time, both ways, is the call
button (above). Dictation costs a transcription, not a Realtime session, and works on a server with no Realtime.

**The take** (`components/celestin/use-dictation.ts`, `lib/tutor/dictation/`). One tap starts it (the browser asks
for the microphone the first time); it ends by itself, or on a second tap:

- `vad.ts` (pure, tested by simulated levels) reads the loudness every 50 ms. The first 300 ms measure the room;
  speech is what stays above 3 × that floor (never below an absolute minimum) for 120 ms, and a take with less
  than 350 ms of speech is not a take. After speech, a silence ends it: 1.3 s for a short phrase, more for a
  long one (+0.15 s per second said, up to 2.5 s), so a student thinking in the middle of a statement is not cut.
  The floor follows a room that gets louder while nobody speaks. Nothing said for 8 s, or 60 s in all, also ends it.
- A take in which nothing was said is dropped without a round trip (« Je n'ai rien entendu »). The microphone is
  released the moment the take ends, so the browser's recording indicator goes off.
- Ending it sends the recording whole to `POST /api/dictation`; a tap while it is being transcribed gives up (the
  request is aborted and the text, if it still arrives, is ignored). A voice call, or the page going to the
  background, drops a take in progress. While Célestin is answering, the button waits like the field does.
- The text is appended to what is already in the field; nothing is sent for her.

**The route** (`api/routes/dictation.py`, `services/dictation.py`, `providers/openai_transcription.py`). Multipart:
`audio` (webm, ogg, mp4/m4a, aac, mp3 or wav; the content type's `codecs` parameter is dropped), `language` (the
**course's** language, `fr` or `en`: a hint, never the interface's; absent for a language course, which mixes two
languages, where no hint beats the wrong one) and `duration_ms` (for the cost line). The
recording is read, transcribed and forgotten: nothing is stored, and what was said is never logged. Errors:
`503 dictation_disabled`, `422 invalid_audio` (empty, or not audio), `422 invalid_language`, `413`
(`DICTATION_MAX_BYTES`, enforced while the body streams, like the document limit), `429 dictation_rate_limited`
(per user), and the provider's own (`502`, `504`…). Silence is `200 {"text": ""}`, not an error. The log line
`dictation` carries user, language, bytes, audio seconds, characters, latency and an estimated cost.

**Which model, which server.** The model is the voice role's **speech model** (`VOICE_TRANSCRIPTION_MODEL`, default
`gpt-4o-mini-transcribe`; the field « Modèle de parole » of the voice role in the admin screen), called on the
voice role's own connection if it has one, else the default connection, through `/audio/transcriptions`. As for
voice, it is **not guessed to work on a server that is not OpenAI's**: there it needs a connection of the voice role
or a speech model somebody chose (Groq's `whisper-large-v3-turbo`, say). `GET /api/health` says `dictation: true`
only then; without it the microphone is not shown. Dictation does not need `VOICE_ENABLED` or a Realtime server.
The browser needs `getUserMedia`, `MediaRecorder` and `AudioContext`; without them the microphone is not shown.

| Variable                  | Default   | Notes                                                                                |
| ------------------------- | --------- | ------------------------------------------------------------------------------------ |
| `DICTATION_ENABLED`       | `true`    | `false`: `/api/health` says `dictation: false`, the route answers `503`.             |
| `DICTATION_MAX_BYTES`     | `4194304` | One recording. A minute of Opus is a few hundred kB; Safari's AAC is larger.         |
| `DICTATION_MAX_S`         | `60`      | The longest take the cost line trusts; the browser's own cap is 60 s.                |
| `DICTATION_PER_HOUR`      | `240`     | Per user.                                                                            |
| `DICTATION_PRICE_PER_MIN` | `0.003`   | USD per minute, for the log; shown as 0 on a server that is not OpenAI's unless set. |

**Not done.** Words are not streamed while she speaks (the text arrives when the take ends); the transcription has
no hint of the chapter's vocabulary; the admin's live check does not try the speech model (the test action covers
tutor, authoring, transcription and the Realtime secret); a real iPhone and Android with a real microphone have
not been tried, only a synthetic microphone in Chromium.

## Failure behaviour

| Situation | What she sees |
|---|---|
| Mic refused | « Célestin n'a pas accès à ton micro… », text mode, nothing minted. |
| `/session` 429 / 503 / 5xx | The server's French message; text mode. |
| SDP, ICE or channel-open failure | « La connexion vocale n'a pas abouti… »; text mode. |
| Channel lost mid-session | « connexion vocale perdue » marker; completed turns kept; a tool whose result arrived is applied, the rest dropped. |
| `/tool` failure | The model gets `{"ok": false}` and continues; one error entry. |
| Realtime `error` event | Silent for the racing-class codes (an active response already exists); otherwise one error entry, session stays up. |
| Cap / idle | « fin de la séance vocale : temps écoulé » / « … : silence prolongé ». The cap waits up to 10 s for the current turn to end. |
| Second tab | « Une séance vocale est déjà ouverte dans un autre onglet. » |

## Manual checklist

Run both processes; in the browser:

1. Empty transcript → mic: Célestin opens by voice and starts section 1; the strip shows it active.
2. Say « écris la définition au tableau » (or type it): a card appears while Célestin is still talking.
3. Interrupt Célestin mid-sentence: the entry is marked « (interrompu) », Célestin answers the interruption.
4. Type « Étape suivante. » during voice: Célestin continues by voice.
5. End the session, type a message: Célestin answers by text with the whole history.
6. Reload: text mode, transcript gone, progress kept (as in text mode).
7. Deny the mic once: the sentence appears, text mode intact.

Checked with a synthetic silent microphone through Playwright on 11 September 2026: 2, 4, 5, the
cap, the idle cut-off and the rate limit. A live barge-in (3) needs a real microphone.

## Data retention

No audio is stored by this product and Realtime tracing is off. Audio and transcripts pass through
the voice provider (OpenAI by default) under its API data-retention terms.

## Scripts

```sh
cd backend
uv run python -m scripts.voice_smoke   # mints one real secret: proves the session config is accepted
uv run python -m scripts.voice_probe   # three prompts through the text model with the voice block, flags $…$ in speech
# both take --language en|nl: the English or Dutch chapter, and the probe also flags x^2, u_n, \frac (and, in English, a decimal comma)
```

Both call the real API. The probe is a proxy: it runs the text model, not the Realtime one.
