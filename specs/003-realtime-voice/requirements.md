# 003 — Talking to Célestin: a voice mode on the OpenAI Realtime API

## 1. Introduction

Today the learner types to Célestin and reads his answers next to the board. This feature lets her talk to him instead: she presses the mic, speaks, hears Célestin answer in French, and sees the board fill up exactly as it does in text mode. Voice is closer to how a private teacher works ("dis-moi ce que tu vois", "pourquoi ce signe ?") and it is the engagement lever the product brief says everything else depends on (§2, §9).

The feature is deliberately an *exploration*: prove that the same tutor, the same rules and the same board work over speech, and measure what a spoken session costs. It is built on the generally available OpenAI Realtime API (speech-to-speech, model family `gpt-realtime-2.1`), reached from the browser over WebRTC.

The architecture, in one paragraph. The backend mints a short-lived Realtime client secret whose session configuration carries **the same prompt (with the course pack and curriculum) and the same five tool declarations** as the text pipeline. The browser opens a WebRTC connection to OpenAI with that secret: audio flows browser ↔ OpenAI; JSON events flow over the data channel. When the model calls a tool, the call arrives *in the browser*, which executes it by calling a new backend tool endpoint. The backend validates the arguments, applies the locked-path rules and returns the tool result plus the board/section event the browser already knows how to reduce. The backend stays stateless; the browser stays the owner of the transcript, which is one transcript across text and voice. The tool endpoint is designed to carry the learner's identity (a bearer token) as soon as authentication exists; today it is anonymous, like every other route.

Scope:

- A voice session toggle in the tutor column, with listening / speaking / working states, mute, and end.
- A backend route that mints the ephemeral client secret with the tutor's prompt and tools.
- A backend route that executes one tool call, with the same validation, path rules and result strings as the text loop.
- Live captions: what she said and what Célestin said, appended to the same transcript as text turns.
- Mode switching in both directions without losing the conversation or the board.
- Cost and duration controls: per-session cap, idle cut-off, model and voice configurable.

Out of scope, stated so the boundary is unambiguous:

- Authentication itself. The tool endpoint reserves the place for a bearer token; issuing and verifying one is a later spec.
- Telephony (SIP), a video avatar, speech input for maths *answers* (an answer widget stays typed or photographed).
- A mechanical checker, mastery, or any persistence beyond what 002 has. Voice changes the channel, not the pedagogy engine.
- Server-side execution of tool calls by attaching the backend to the call. It is discussed as an option in §4.1 and left to the design document.

## 2. Alignment with product vision

| Product requirement | How this feature serves it |
|---|---|
| §2, §9 Engagement is the binding constraint | Talking is lower effort than typing on a laptop next to squared paper. A session she can *hold* while writing by hand is more likely to happen four times a week. |
| §5.6 It is a lesson, not a chat | Célestin still drives: sections, board cards and « Étape suivante » work unchanged. The voice is another way to interrupt and answer, not a new product. |
| §6.3 Discuss | "Pourquoi ?", "j'ai fait autrement" are said, not typed. Speech is where the product brief expects most learning to happen and where the dialogue-quality metric (§9) is measured. |
| §5.1 It teaches her course | Same prompt, same pack, same vocabulary. The board keeps the teacher's notation; the voice reads it in words. |
| §5.2 It withholds answers by construction | Same tools, same refusals, executed by the same backend code. The prompt rules against stating an open answer apply to speech. |
| §6.5 Input: free text at any time, camera on every card | The mic joins the composer's controls. Typing stays available during a voice session. |
| §6.6 Transcripts readable in full | Every spoken turn is transcribed into the transcript with a voice marker, so the parent view of a later spec sees voice sessions like text ones. |
| §11 "Out of scope for now: voice" | This spec revises that line: voice moves from out of scope to an exploration, gated on cost and quality measured here. |

Deliberate deviations, for a POC:

- §5.3 "never grades from memory" remains unmet, as in 001 and 002. Voice does not make it worse: nothing in the voice path issues a verdict.
- §8 answer leakage is still enforced by prompt, not by a filter. Spoken output cannot be screened before it is heard, so a leak filter is *harder* in voice. Recorded as a known limitation (§4.6).

## 3. Requirements

### R1 — Start and end a voice session

**As a** learner, **I want** to press the mic and talk to Célestin, **so that** I can work with him the way I would with a teacher sitting next to me.

Acceptance criteria:

1. The inert mic button in the composer becomes the voice toggle. Pressing it asks for microphone permission (first time), opens a voice session, and shows the session state; pressing it again ends the session and returns to text mode.
2. Voice session states are visible at all times while a session is open: *connecting*, *listening*, *Célestin speaks*, *Célestin works* (a tool call is in flight), *muted*, *error*. Copy is French, tutoiement.
3. A mute control stops sending audio without ending the session. A muted session still plays Célestin's audio.
4. Ending the session stops the microphone, closes the connection and leaves the transcript, the board and the progress exactly as they were at the last completed turn.
5. The browser tab shows the microphone as in use only while a session is open and unmuted.
6. A voice session opens on top of the existing conversation: the transcript so far is given to the Realtime session as prior conversation items, so Célestin continues rather than restarts. A voice session opened on an empty transcript performs the same opening move as a text session (situate her on the path, start the next section).
7. Text mode is restored on session end, on any unrecoverable error, and on page reload. A voice session never survives a reload.

### R2 — The same tutor

**As a** parent, **I want** the voice Célestin to be the same Célestin, **so that** what I reviewed in the prompt and the pack is what she hears.

Acceptance criteria:

1. The Realtime session instructions are the rendered tutor prompt: `prompts/tutor.fr.md` with the course pack and curriculum overview substituted, the same text the text pipeline sends as its cached developer message. There is no second prompt file for voice.
2. Voice-specific guidance (speak maths in words, keep spoken turns short, put every formula on the board rather than reading LaTeX aloud) lives in a clearly delimited block of the same prompt file. The block is included in the voice session and omitted from the text session, or included in both if measured harmless to the text cache. The design decides; the requirement is one file, parent-readable.
3. The five tool declarations sent to the Realtime session are produced by the same registry as the text loop, in the same order, with the same names, descriptions and JSON schemas. A test asserts byte-equality of the two declaration lists (modulo the `strict` field if the Realtime API does not accept it).
4. The path state (« État du parcours », active or next section, `start_section("id")` instruction) is given to the voice session at open time and refreshed after every section tool call, so the voice Célestin knows where she is exactly as the text Célestin does.
5. Adding a tool to the registry later makes it available to both channels without a second registration.
6. The tutor speaks French. The session pins French for both recognition and speech; the input transcription language is `fr`.

### R3 — Tools called from the browser, executed by the backend

**As a** developer, **I want** every tool call to run through the backend, **so that** the rules that make Célestin a tutor (path enforcement, argument validation, typed board content) hold in voice mode without being re-implemented in the browser.

Acceptance criteria:

1. When the Realtime model emits a function call, the browser sends it to a backend tool endpoint with: the tool name, the raw JSON arguments string, the current progress `{done, active}`, and a client-side call id.
2. The backend validates the arguments with the same Pydantic models as the text loop, applies the same path rules, mutates nothing it does not already mutate in text mode, and returns: the tool output as the model should see it (the same `{"ok":…}` payload the text loop puts in `function_call_output`), the resulting event (`board.set`, `board.clear`, `section.start`, `section.done`, `step.ready`, or none), and the updated progress.
3. The browser feeds the tool output back to the Realtime session as a `function_call_output` item and requests the next response, and reduces the returned event through the same reducer as an SSE event. Board cards, markers, section state and the « Étape suivante » button behave identically in both modes.
4. A refused tool call (`ok: false`) is returned to the model as in text mode and produces no event and no learner-visible failure. A malformed arguments string is a refusal, never a 4xx.
5. Executing a tool this way appends the same `tool` history entry as the text loop, so a transcript built in voice mode is valid input to the text endpoint.
6. The tool endpoint accepts an optional `Authorization: Bearer …` header and ignores it today. Its request and response shapes contain nothing that would change when the bearer becomes mandatory and identifies the learner. The design document names the field and the check point.
7. Tool execution latency is visible to the learner as *Célestin works* and to the model as an ordinary tool round trip; the browser does not time out a tool call before the backend does.
8. The learner's two board interactions (check-question answer, « Étape suivante ») reach the voice Célestin as user text items with the same French messages as in text mode, followed by a response request.

### R4 — One transcript, two channels

**As a** learner, **I want** to see what I said and what Célestin said, **so that** I can re-read a spoken explanation and switch to typing without losing the thread.

Acceptance criteria:

1. Each spoken learner turn appears in the transcript as a learner entry carrying the input transcription, once the transcription is final. Each spoken Célestin turn appears as a tutor entry built from the output transcript, streamed as it is spoken.
2. Voice entries are marked as spoken (an icon or label, French copy), so a reader can tell "she wrote" from "she said". The marker is part of the transcript entry, not only styling, so a later parent view can carry it.
3. Typing during a voice session is allowed. A typed message goes to the Realtime session as a user text item and Célestin answers by voice.
4. When she interrupts Célestin mid-sentence, playback stops at once, the Realtime item is truncated to what was actually heard, and the transcript keeps only the heard part.
5. Switching from voice to text and back keeps the whole transcript; the text endpoint receives voice turns as ordinary learner and tutor entries. A transcript containing voice turns passes the same validation as one without.
6. The board history strip and the current board are unaffected by the channel: a card set by voice is the same object as a card set by text.
7. Retry after an error in voice mode rolls back to the start of the failed turn, as in text mode.

### R5 — Ephemeral credentials, minted by the backend

**As a** parent, **I want** the API key to stay on the server, **so that** nobody can run up a bill from the browser.

Acceptance criteria:

1. A backend route creates a Realtime client secret via `POST /v1/realtime/client_secrets` and returns to the browser only the secret value, its expiry, and the non-secret session parameters the browser needs (model, voice, session cap). The `OPENAI_API_KEY` never reaches the browser.
2. The client secret expiry is the shortest that lets the SDP exchange succeed reliably (the API allows 10 s to 7200 s; target under two minutes). The secret is single-use by design of the browser code: the browser requests a new one for every session.
3. The session configuration (instructions, tools, voice, language, turn detection, output modalities, token and truncation limits, reasoning effort) is set server-side in the client-secret request, not by the browser. The browser can send `session.update` for runtime state only (mute-related turn detection, nothing that widens the tool set or changes instructions).
4. The route is the only place, besides the existing provider adapter, that knows about OpenAI, and it lives behind the provider protocol like the text client. The layering test keeps `openai` out of everything above `app/providers/`.
5. The route accepts an optional bearer token like the tool endpoint (R3.6). Until authentication exists, it is rate-limited per origin or per IP to a small number of sessions per hour (configurable), since it is the first route that spends money on request.
6. The route refuses to mint when the API key is missing or the prompt or pack cannot be rendered, with the same HTTP statuses as the chat endpoint.

### R6 — Cost and duration controls

**As a** parent, **I want** a spoken session to be bounded, **so that** the exploration cannot surprise me on the bill.

Acceptance criteria:

1. A voice session has a hard duration cap (configurable, default 25 minutes, aligned with the product's session length, below the API's 60-minute limit). At the cap the browser ends the session, Célestin's last sentence is allowed to finish, and the transcript gets a marker saying why.
2. An idle cut-off ends the session after a configurable silence (default 3 minutes) with a marker.
3. The session cap is visible as a countdown alongside the session timer the brief asks for.
4. Every voice session logs, server-side, at session end or at intervals: session id, duration, and token usage by modality (text / audio, input / cached / output) as reported by the Realtime `response.done` usage payloads, forwarded by the browser to a backend usage route. Logged usage is enough to compute the cost of a session from the published price list.
5. The Realtime model, voice, speed, reasoning effort, transcription model and turn-detection type are configuration values with documented defaults. Default model `gpt-realtime-2.1`; the mini variant is a one-line change for cost comparison.
6. Conversation truncation is enabled so a long session does not grow the context without bound; the prompt and tools are the retained prefix.
7. Session end for any reason (cap, idle, error, learner) closes the peer connection and releases the microphone; no session keeps billing after the UI shows it closed.

### R7 — Failure handling

**As a** learner, **I want** a broken voice session to fall back to text cleanly, **so that** a network hiccup does not cost me the lesson.

Acceptance criteria:

1. Microphone permission denied: the toggle explains in one French sentence how to allow it and stays in text mode.
2. Client-secret request failure, SDP exchange failure, expired secret, ICE failure: one French error entry in the transcript, text mode restored, retry available.
3. Data channel or peer connection lost mid-session: the session ends with a marker; the transcript keeps every completed turn; a tool call that was in flight is either completed and reflected, or dropped together with its Célestin turn, never half-applied (a section marked started with no `section.start` reflected, or the reverse).
4. Tool endpoint failure (5xx, network): the browser returns an `ok: false` output to the model with a French error so Célestin can say so, and shows nothing more alarming than the existing error entry.
5. Unsupported browser (no WebRTC, no `getUserMedia`): the mic button stays inert with its current tooltip.
6. Two tabs cannot hold two voice sessions at once from the same browser; the second attempt is refused with a message.

## 4. Non-functional requirements

### 4.1 Architecture

1. The backend stays stateless. Progress arrives with each tool call and leaves with the result; the transcript lives in the browser; no session store. The only server-held state is the OpenAI-side conversation, which lasts as long as the WebRTC call.
2. The tool endpoint reuses the registry's `execute` path and the `TurnContext`; the event mapping from tool result to event is one function shared by the SSE turn loop and the tool endpoint, so the two cannot drift.
3. The prompt rendering (`prompt_service`) has one function that returns the instructions text, used by both the cached developer message and the client-secret request.
4. The Realtime provider (client-secret minting) is a second implementation behind the provider protocol, so tests run offline against a fake, as the text loop does.
5. The frontend gets a `voice` module under `src/lib/tutor/` (connection, data-channel event parsing, tool bridge) with a pure event-to-reducer mapping that is unit-tested against recorded Realtime event fixtures, mirroring `sse.ts`.
6. The SSE event set does not change. Voice reuses the reducer and the `TutorEvent` types as its internal event vocabulary.
7. **Design option to evaluate, not decided here:** the Realtime API also lets the backend perform the SDP exchange and attach to the call by its call id, which would move tool execution server-side and keep the browser out of the tool loop. The design document compares it with the browser-bridge approach on latency, stateless-ness and authentication, and picks one. The requirements above are written for the browser bridge because it is the documented WebRTC path and keeps the backend stateless.

### 4.2 Performance

1. Time from pressing the mic to *listening* under 3 s on a home connection; the client-secret round trip and SDP exchange are the only serial steps.
2. Tool execution adds one backend round trip (target under 300 ms locally) to the model's response; the board updates before Célestin finishes the sentence that introduced it.
3. The text pipeline's cached prefix is untouched. The smoke script still passes with zero regressions in `cached_tokens`. If the voice block of the prompt is shared with text (R2.2), its cost is measured before merging.
4. Realtime prompt caching is relied upon for the instructions and tool prefix; the client-secret request keeps them byte-stable across sessions.

### 4.3 Security

1. The API key is server-only (R5.1). Client secrets are short-lived (R5.2) and never logged.
2. The client-secret and tool routes are the first that spend money on request; both carry the optional bearer (R3.6, R5.5) and are rate-limited until it is mandatory. The rate limit and the future auth check are one middleware or dependency, so making auth mandatory is a configuration change.
3. Tool arguments from the Realtime model are untrusted, validated as in text mode. The browser is also untrusted: the tool endpoint never trusts a client-supplied tool *result*, only a tool *call*.
4. The rendered prompt and pack are returned to the browser inside the session object of the client-secret response. This is accepted: the pack is the learner's own course, the prompt is parent-readable by design. The response is served with `Cache-Control: no-store`.
5. Audio is streamed to OpenAI and not stored by this product. Realtime tracing is off. The data-retention terms of the Realtime API apply and are noted in the documentation.
6. Body-size limits and request-id middleware apply to the new routes.

### 4.4 Reliability

1. A tool call is idempotent from the browser's point of view: re-sending the same call id after a network retry does not apply a section change twice (progress is in the request, so a repeat with the same progress yields the same result).
2. The reducer receives voice-originated events in the order the model produced them; a tool result event is applied before the model's next audio for that response starts playing where the API allows, and never after a later tool's event.
3. Session end and error paths release the microphone in every case, verified by a test on the teardown function.

### 4.5 Usability

1. All voice copy is French, tutoiement, consistent with the interface: « Parler à Célestin », « Célestin t'écoute », « Célestin parle », « Célestin écrit au tableau », « Micro coupé », « Fin de la séance vocale ».
2. Spoken maths: Célestin says "u indice n", "q différent de un", "l'intervalle ouvert de moins trois à trois" and puts the notation on the board. Verified by probe transcript, like the R9 guardrails of 001.
3. Captions are readable without looking away from the board: Célestin's live caption is the transcript entry being written, not a separate overlay.
4. The mic toggle, mute and end are keyboard reachable and announce their state.
5. Laptop first. The feature must work in current Chrome, Firefox and Safari on macOS; tablet is checked, not blocking.

### 4.6 Known limitations carried forward

1. **No leak filter in voice.** Spoken output is heard before it can be screened; the prompt is the only guard. Text mode has the same gap today; voice makes the fix harder later.
2. **No checker, no mastery**, as in 002. Practice sections still close on Célestin's judgement.
3. **No authentication.** Rate limiting stands in for it on the two money-spending routes.
4. **Transcripts are per browser and lost on reload**, as today. Voice does not add persistence.
5. **Input transcription is what the transcript records**, not the audio. A misheard "q égale deux" is recorded misheard; she can correct by voice or text.
6. **Cost is an open question this spec exists to answer.** Published prices for the default model are 32 USD per million audio input tokens (0,40 cached) and 64 USD per million audio output tokens, roughly 600 input tokens and 1 200 output tokens per minute of speech; the prompt prefix (about 12 000 text tokens) is cached per session. A 25-minute session is expected in the order of one to two euros before measurement. R6.4 exists so the estimate becomes a number.

## 5. Open questions for the design

1. Browser bridge versus server-attached call (§4.1.7).
2. Whether the voice-specific prompt block is included in text sessions (R2.2) once its cache cost is measured.
3. Semantic versus server voice-activity detection, and whether a push-to-talk fallback is worth having for a noisy room.
4. Which voice, and whether `speed` below 1 helps for maths.
5. How the check-question answer and « Étape suivante » should interrupt or queue behind Célestin's current speech.
