# 001 — Implementation plan: agentic tutor in the chat column

Reference: `requirements.md` (R*, NFR §4.x), `design.md` (§1–10).

## Status

| Phase | Goal | State |
|---|---|---|
| 0 | Backend skeleton, config, health | Done |
| 1 | Prompt file and course pack injection | Done |
| 2 | Domain models and tool registry | Done |
| 3 | Provider adapter and test double | Done |
| 4 | Turn loop and SSE endpoint | Done |
| 5 | Chat column wired, text only | Done |
| 6 | Board driven by tools | Done |
| 7 | Failure paths and observability | Done |
| 8 | Prompt quality pass | Done |
| 9 | Documentation | Done |

Pinned versions at planning time: `fastapi` 0.141.1, `openai` 3.12.0, `pydantic-settings` 2.15.0, `vitest` 5.0.0 (peer `vite ^8`). Python ≥3.12, managed with `uv`.

---

## Phase 0 — Backend skeleton, config, health

**Goal.** A FastAPI app that starts, reads configuration from the repo-root `.env`, and answers a health check. No LLM, no prompt.

**Verify.** `uv run uvicorn app.main:app --reload --port 8000`, then `curl localhost:8000/api/health` returns `{"status":"ok", ...}`. Unset `OPENAI_API_KEY` and confirm startup aborts with an explicit message.

- [x] **0.1 Project scaffold.** `backend/pyproject.toml` via `uv init`, `requires-python = ">=3.12"`. Dependencies: `fastapi`, `uvicorn[standard]`, `pydantic-settings`, `openai`. Dev group: `pytest`, `pytest-asyncio`, `httpx`.
- [x] **0.2 Settings.** `app/config.py`, pydantic-settings reading `../.env` relative to `backend/`. Fields per design §3.4 and §8: `openai_api_key`, `openai_model` (default `gpt-5.6-terra`), `tutor_prompt_path`, `course_pack_path`, `max_tool_rounds` (6), `max_message_chars` (4000), `max_history_entries` (60), `history_token_budget` (30000), `cors_origins`, `log_level`, `debug_log_prompts` (false), `request_timeout_s`. Missing key raises at import of the settings singleton (NFR 4.3.2).
  *Unit tests:* defaults applied; missing key raises; env override wins; paths resolve to absolute.
- [x] **0.3 App factory.** `app/main.py` with `create_app()`, router mounting under `/api`, CORS middleware from settings, and a request-id middleware that puts `request_id` on every log line. JSON structured logging configured here (NFR §4.9).
  *Unit tests:* app builds; unknown route returns 404; request id appears in the response headers.
- [x] **0.4 Health controller.** `app/api/routes/health.py`, returns `{status, model, pack_loaded}`. `pack_loaded` is a placeholder `false` until Phase 1.
  *Unit test:* 200 and the expected keys.
- [x] **0.5 Test harness.** `pytest.ini`/`pyproject` config with `asyncio_mode = "auto"`, an `httpx.AsyncClient` + `ASGITransport` fixture, and a `tests/fixtures/` directory.
- [x] **0.6 Update `backend/CLAUDE.md`.** Replace the "no stack chosen" placeholder with the real commands and layout.

---

## Phase 1 — Prompt file and course pack injection

**Goal.** The system prompt exists as an external file, the chapter 1 pack is injected into it, and assembly is a pure, tested function.

**Verify.** `curl localhost:8000/api/courses/current` returns the chapter label and title. Health reports `pack_loaded: true`. Edit `backend/prompts/tutor.fr.md`, reload, and confirm the change is picked up with no restart.

- [x] **1.1 Write the prompt.** `backend/prompts/tutor.fr.md`, French, covering every clause of R1.5, R1.6, and R9.1–R9.3: tutoiement, warm and direct, questions preferred over statements when stuck, the pack's notation conventions, nothing taught that is absent from the pack, opens with a proposed agenda, never states the answer to an open exercise, redirects off-topic requests, and never teaches an item listed under the pack's "Points à faire valider" (R2.4). Declares an explicit insertion marker for the pack.
- [x] **1.2 CourseService.** `app/services/course_service.py`. Reads `courses/chapitre_1/pack.md`, caches by mtime so an edit is picked up without restart (R1.4, NFR 4.2.3). Raises `PackUnavailable` on failure. Single hardwired accessor (R2.2). Also exposes chapter metadata parsed from the pack header.
  *Unit tests:* reads and returns content; second call does not re-read an unchanged file; a touched file is re-read; missing file raises.
- [x] **1.3 PromptService.** `app/services/prompt_service.py`. `build(prompt_text, pack_text, history)` is pure (NFR 4.1.4). Emits the developer message first with the pack substituted at the marker and a `prompt_cache_breakpoint`, then the mapped transcript. Ordering is load-bearing for cost (design §7).
  *Unit tests:* marker substituted; developer message is item 0; breakpoint present; a prompt file missing the marker raises; identical inputs produce byte-identical prefixes across calls.
- [x] **1.4 Courses controller.** `app/api/routes/courses.py`, `GET /api/courses/current` returning `{id, chapter_label, title}` only. Pack content must not appear in the response (R2.5).
  *Unit tests:* 200 and expected keys; response body contains no pack body text.
- [x] **1.5 Wire health.** `pack_loaded` now reflects the real state.

---

## Phase 2 — Domain models and tool registry

**Goal.** Board cards, transcript entries, and the two tool declarations exist and reject malformed input. No network.

**Verify.** `uv run python -m app.tools.dump_schema` prints the JSON schema for both tools, matching design §4.3. Unit suite green.

- [x] **2.1 Board card models.** `app/domain/board.py` and `app/api/schemas/board.py` per design §4.2: the `Block` union (text, formula, quote, note) and the six card kinds, discriminated on `kind`.
  *Unit tests:* each kind parses from a valid payload; the §4.2 constraints reject — two-to-four options, `correct_option_id` present in `options`, one-to-eight steps, non-empty strings.
- [x] **2.2 Transcript models.** `app/api/schemas/chat.py`: `LearnerEntry`, `TutorEntry`, `ToolEntry`, discriminated `Entry`, and `ChatRequest` with the length caps from settings.
  *Unit tests:* discriminator routes to the right type; oversized message rejected; oversized history rejected.
- [x] **2.3 Tool registry.** `app/services/tools/registry.py` and `board.py`. Declarations for `display_board` (strict false) and `clear_board` (strict true), fixed order because they sit in the cached prefix. `validate(call)` returns parsed arguments or a `ToolValidationError` carrying a message intended for the model. Handlers return the card to emit; they hold no state (design §3.4).
  *Unit tests:* declaration order stable across calls; valid arguments dispatch; invalid arguments produce a message naming the offending field; an unknown tool name is handled, not raised.
- [x] **2.4 History mapping.** `app/services/history.py`. `to_provider_input(entries)` maps learner/tutor/tool onto provider items, synthesizing `call_{index}` ids (design §10.4), and applies the trimming policy from §7.
  *Unit tests:* role mapping; a `function_call` is never emitted without its `function_call_output`; trimming drops oldest first; trimming never separates a tool entry from its turn; the most recent learner message always survives.
- [x] **2.5 Schema dump utility.** Small module that prints the tool declarations, used for the phase verification and for eyeballing what the model actually receives.

---

## Phase 3 — Provider adapter and test double

**Goal.** OpenAI sits behind the protocol, and a scripted fake lets every later phase be tested offline.

**Verify.** `uv run python -m scripts.smoke` performs one real API call and prints the streamed text plus token usage including `cached_tokens`.

- [x] **3.1 Protocol and events.** `app/providers/base.py`: the `LLMClient` protocol and the `ProviderEvent` union (`TextDelta`, `ToolCallRequested`, `Completed`, `Failed`) per design §3.3. Nothing above this module may import `openai`.
  *Unit test:* an import guard asserting `openai` is absent from the import graph of `app/services/`.
- [x] **3.2 FakeLLM.** `tests/fixtures/fake_llm.py`. Constructed from a list of scripted event sequences, one per round. Records the input it received so tests can assert on prompt assembly.
  *Unit tests:* replays events in order; raises when a test asks for more rounds than scripted.
- [x] **3.3 OpenAI adapter.** `app/providers/openai_responses.py` using `AsyncOpenAI`. Calls `client.responses.create(..., stream=True)` and maps events per design §3.3. Sets `store=false` (design §10.6), the model from settings, and the request timeout. Buffers `function_call_arguments.delta` and emits `ToolCallRequested` only on `.done`. Maps provider exceptions onto the §4.4 error hierarchy.
  *Unit tests:* event mapping table driven by recorded fixtures; malformed argument JSON surfaces as a tool error rather than a crash; `store` is false on every call.
  *Check at implementation time:* whether the installed SDK exposes a `client.responses.stream()` context-manager helper. If it does, prefer it; the `create(stream=True)` form is the confirmed fallback.
- [x] **3.4 Live smoke script.** `backend/scripts/smoke.py`, opt-in, not part of the default test run. Also serves as the first real check that the prompt and pack fit and that caching engages on the second call.

---

## Phase 4 — Turn loop and SSE endpoint

**Goal.** `POST /api/chat` runs a full turn, including tool rounds, and streams it as SSE.

**Verify.** `curl -N -X POST localhost:8000/api/chat -H 'content-type: application/json' -d '{"history":[]}'` prints an opening turn: `turn.start`, `text.delta` frames in French, at least one `board.set`, then `turn.end`.

- [x] **4.1 Event models and serializer.** `app/api/schemas/events.py` for the six events in design §3.2, and a serializer producing `event: <name>\ndata: <json>\n\n`.
  *Unit tests:* frame format exact, including the blank-line terminator; JSON is single-line; unicode is not escaped away.
- [x] **4.2 TutorService.** `app/services/tutor_service.py`, the loop in design §3.4. Yields turn events; increments `block_id` per contiguous text run (R6.4); appends `function_call` and `function_call_output` between rounds; stops at `max_tool_rounds` with `reason: max_rounds` (R6.3).
  *Unit tests, all with FakeLLM:* text only; text → tool → text ordering and block ids; two tool calls in one round; invalid arguments then a corrected retry within the same turn; round limit exhausted; provider failure mid-stream ends the turn with an error event.
- [x] **4.3 Chat controller.** `app/api/routes/chat.py`. Validates the request, wraps `run_turn` in a `StreamingResponse` with `media_type="text/event-stream"` and the headers from design §3.2, emits a `: ping` comment every 15 seconds, and closes the provider stream in a `finally` on disconnect. Checks `await request.is_disconnected()` between rounds.
  *Unit tests:* headers present; heartbeat emitted on an idle stream; disconnect closes the underlying stream exactly once.
- [x] **4.4 Error translation.** Pre-stream failures become HTTP status codes per design §4.4; anything after the first byte becomes an `error` event followed by `turn.end` (design §5). Client-visible messages are French and carry no internals (NFR 4.3.6).
  *Unit tests:* a missing pack yields 500 before any frame; a provider failure after the first delta yields an in-stream error; no message contains a stack trace or a path.
- [x] **4.5 Golden transcripts.** Integration tests over `ASGITransport` with FakeLLM injected, asserting the complete SSE byte stream for three scripted turns. These are the contract the frontend codes against; changing them means changing design §3.2.

---

## Phase 5 — Chat column wired, text only

**Goal.** The learner talks to the real tutor in the browser. The board still shows the mock cards.

**Verify.** Run both servers, open the app. The tutor greets you in French with a proposed agenda without being prompted. Send a message and watch the reply stream in. Press the stop control mid-reply and confirm the partial text stays. Kill the backend and confirm a French error entry with a working retry.

- [x] **5.1 Test runner.** Add `vitest` 5 and a `test` script to `frontend/package.json`. Node environment is enough; no DOM tests are required by this phase.
- [x] **5.2 Vite proxy.** Add `vite: { server: { proxy: { "/api": "http://localhost:8000" } } }` to the `defineConfig` call in `frontend/vite.config.ts`. The wrapper documents this as the supported extension point; do not add plugins.
- [x] **5.3 SSE parser.** `src/lib/tutor/sse.ts`, a pure function from a chunk plus carry-over buffer to parsed frames.
  *Unit tests:* frames split across chunk boundaries; multi-line data; comment heartbeats ignored; a trailing partial frame retained in the buffer.
- [x] **5.4 Types.** `src/lib/tutor/types.ts` mirroring the design §3.2 events and §4.2 cards. Kept in sync with the golden transcripts from 4.5.
- [x] **5.5 Transport.** `src/lib/tutor/client.ts`. POSTs the transcript, reads `response.body` through a `TextDecoder`, yields typed events, accepts an `AbortSignal`.
  *Unit tests:* against a mocked `fetch` replaying a golden transcript; abort stops iteration; a non-200 response surfaces as an error event.
- [x] **5.6 Session hook.** `src/components/celestin/use-tutor-session.ts` with the shape in design §3.6. Deltas accumulate in a ref and flush on animation frames (NFR 4.2.2). Fires the opening turn on mount when empty (R3.8).
  *Unit tests:* entries assembled in order from a golden transcript; cancel marks the partial entry interrupted; retry re-sends without duplicating the learner message.
- [x] **5.7 Wire `tutor-column.tsx`.** Replace the mock `conversation` import with the hook. Composer: Enter sends, Shift+Enter newlines, disabled while streaming, cleared on submit, empty submissions rejected (R3.4–R3.6). Add stop and retry affordances. Keep the symbol palette working and non-focus-stealing (R3.7). Auto-scroll that stops when the learner scrolls up, and an `aria-live` region that does not re-read the transcript on each chunk (NFR 4.5.2, 4.5.4).
- [x] **5.8 Leave inert controls alone.** Plan card, camera, and mic unchanged (R-scope, question 4).

---

## Phase 6 — Board driven by tools

**Goal.** Tool calls render as real cards on the whiteboard, with markers in the transcript.

**Verify.** Ask `explique-moi la somme d'une suite géométrique`. An explanation card appears on the board with the course formula typeset, a marker appears in the chat, and the card joins the history strip. Ask the tutor to clear it and confirm the board empties while the strip survives.

- [x] **6.1 Block renderer.** `src/components/celestin/board-blocks.tsx`. Renders the four block types. Text blocks split on `$…$` and hand segments to the existing `Math` component. No `dangerouslySetInnerHTML` beyond KaTeX's own output, which stays on `trust: false` (NFR §4.8).
  *Unit tests:* inline maths split; an unmatched `$` renders literally rather than swallowing the rest; block types dispatch correctly.
- [x] **6.2 Card components take data.** Refactor the six board components in `whiteboard.tsx` to accept their card DTO as props instead of hardcoded content. Visual output must not change (R4.3).
- [x] **6.3 Whiteboard state.** Whiteboard takes the current tutor card and the tutor board history. Tutor cards append to the history strip and become current (R4.4). The six mock boards remain in the strip (R4.8).
- [x] **6.4 Hook handles board events.** `board.set` and `board.clear` update board state and insert marker entries using the backend-supplied French label (R5.1, R5.2). Selecting a marker brings its board back (R5.4).
  *Unit tests:* board state after a set/clear sequence; markers ordered correctly relative to text blocks.

---

## Phase 7 — Failure paths and observability

**Goal.** Every path in requirements R7 and NFR §4.4 and §4.9 behaves as specified.

**Verify.** Set `MAX_TOOL_ROUNDS=1` and confirm a turn that needs two rounds ends with a French notice rather than hanging. Post an oversized message and get a 413 with no provider call. Watch one turn's log line and read off latency to first token, round count, and `cached_tokens`.

- [x] **7.1 Input caps.** Enforce `max_message_chars`, `max_history_entries`, and a body size limit server-side, before any provider call (NFR 4.3.3).
  *Unit tests:* 422 and 413 cases; assert the provider was never called.
- [x] **7.2 Cancellation end to end.** Abort from the browser closes the provider stream, leaves no dangling task, and leaves the composer usable (R7.1, R7.4, NFR 4.4.2).
  *Integration test:* client disconnect mid-round; assert the fake provider's stream was closed.
- [x] **7.3 Round limit notice.** French copy for `reason: max_rounds` in the transcript.
- [x] **7.4 Tool self-correction.** Integration test proving a malformed tool call is returned to the model and a corrected call in the same turn renders a board (R4.6).
- [x] **7.5 Per-turn logging.** One structured line per turn: model, rounds, tool names with validation outcome, end reason, latency to first token, total latency, and the full usage block including `cached_tokens` (NFR §4.9). Prompt and pack content only behind `debug_log_prompts`.
  *Unit test:* the log record contains the required fields and no key material.
- [x] **7.6 Cache hit check.** Assert on the smoke script that a second consecutive turn reports non-zero `cached_tokens`. A zero means prefix drift and blocks the phase.
- [x] **7.7 CORS.** Denied by default, allowed origins from settings, exercised by a test.

---

## Phase 8 — Prompt quality pass

**Goal.** R9 is prompt-only and therefore has no code to test. This phase gives it a repeatable manual check.

**Verify.** Run the probe script and read the transcript against the checklist below.

- [x] **8.1 Probe script.** `backend/scripts/probe.py`, opt-in, runs a fixed list of learner messages against the real model and writes the transcript to a file for reading.
- [x] **8.2 Probe set.** At minimum: `dis-moi juste la réponse` while an exercise is open; a request for a method not in the pack; an off-topic request; a question about `|x² − 3| ≤ 3`, which is one of the pack's seven unvalidated items; a request to explain `Sₙ` for a geometric sequence; and a plain `salut` to check the opening agenda.
- [x] **8.3 Checklist.** The tutor stays in French and tutoiement; withholds the answer and offers a question or hint; uses only pack formulas and the pack's own notation, including decimal commas and `]a ; b[`; refuses to teach the unvalidated item and says why; redirects the off-topic request briefly; opens with an agenda.
- [x] **8.4 Iterate `tutor.fr.md`** until the checklist passes. Record in the spec folder which probes still fail and why, if any.

---

## Phase 9 — Documentation

**Goal.** The repository explains itself to the next session.

**Verify.** A fresh reader can start both servers from the docs alone.

- [x] **9.1 `backend/CLAUDE.md`.** Real commands, layout, and the layering rule that nothing above `providers/` imports `openai`.
- [x] **9.2 `frontend/CLAUDE.md`.** Add the test command, the proxy, and the tutor module map.
- [x] **9.3 Root `CLAUDE.md`.** Two-process dev workflow.
- [x] **9.4 `documentation/`.** Create `index.md` plus a page for the tutor turn pipeline, covering the SSE contract and the prompt-caching prefix rule, per the repository's documentation convention.

---

## Cross-cutting rules

- Nothing above `app/providers/` imports `openai` (design §3.3). Enforced by test 3.1.
- The SSE event set in design §3.2 is a two-sided contract. Changing it means changing the golden transcripts in 4.5, the frontend types in 5.4, and the design document together.
- Tool declaration order and the developer-message prefix are load-bearing for prompt caching. Any change to either invalidates the cache and must be justified against the §7 cost argument.
- The five limitations in requirements §4.6 stay open at the end of this feature. Do not implement grading, mastery, or a leak filter here.

---

## Phase 8 result — probe run

Model `gpt-5.6-terra`, prompt `backend/prompts/tutor.fr.md`. Full transcript regenerated with
`uv run python -m scripts.probe`; it is a generated artefact and is gitignored.

| Probe | Outcome |
|---|---|
| Ouverture de séance | Passes. Opens unprompted with a `title` card and a 25-minute agenda, ends on "Ça te va ?". |
| Refus de donner la réponse | Passes. Refuses, then shows a faded worked example that establishes the raison and stops at "quelle place correspond à 2018 ?". The result is never stated. |
| Insistance | Passes. Acknowledges the frustration, still refuses, reduces the exercise to one remaining step. |
| Méthode hors du cours | Passes. Declines sigma notation and infinite geometric series as absent from the chapter, redirects to the finite sum. |
| Hors sujet | Passes. One sentence, no lecture. |
| Point non validé du pack | Passes. Refuses `\|x² − 3\| ≤ 3` by name, citing the contradictory corrigé, and offers a validated exercise instead. |
| Enseignement normal | Passes. Explanation card with the course derivation, `CE : q ≠ 1` flagged, ends with a choice. |

Notation observed in output: `q ≠ 1`, `CE`, `]a ; b[`, decimal commas, `u_1` indexing. No probe failed;
no prompt iteration was needed beyond the first draft.

---

## Cleanup pass

Ran after phase 9, across four review angles. Applied:

| Fix | Why it mattered |
|---|---|
| `scripts/probe.py` and `scripts/smoke.py` now drive `TutorService` | Both carried a second copy of the turn loop. The probe never called the tool registry, so an invalid card was transcribed as valid — the phase 8 transcript was not what a learner would get. |
| Provider `Failed` events raise a mapped `TutorError` instead of framing their own SSE error | Rate-limit and timeout were flattened to `provider_unavailable` on the streamed path, leaving two of the four error types in design §4.4 dead there. Error translation now happens once, in the controller, as design §5 specifies. |
| Composition moved into `create_app`; `app.state` replaces `lru_cache` singletons | Object lifetime was tied to the process and to config values, the provider client was pinned to whichever event loop touched it first, and tests had to clear a private cache. `dependency_overrides` is no longer written by production code. |
| Card markers moved onto the card classes as `ClassVar` | The marker table re-enumerated the six kinds. A seventh would have type-checked, validated, then raised `KeyError` mid-stream. |
| `registry.declarations()` built once at import | ~2 ms per call, once per round, on the path to first token — and it sits in the cached prefix, so it is now byte-stable by construction. |
| One layout tree instead of two | Both branches were rendered and one hidden with CSS: two of every component, two KaTeX board trees, both re-rendering on every streamed token. |
| `React.memo` on `Entry` and `Whiteboard` | The whole transcript and the board re-rendered at frame rate during a stream. |
| A run only disowns its own `AbortController` | An aborted run cleared the newer run's controller and flipped status while it was still streaming. |
| Pending animation frame cancelled in `flush` | Each board event orphaned a scheduled frame. |
| `history.trim()` costs each turn once | Was O(n²) over the transcript; bounded by the entry cap, but wrong. |
| Mock strip entries derived from `MOCK_CARDS`; dead `Board`/`BoardKind`/`ChatEntry`/`conversation` deleted | The duplicate list had already drifted, and carried a second, incompatible spelling of the card kinds (`worked-example` vs `worked_example`). |
| Strip items carry their own `select` callback | The source was encoded into a key string and recovered with `startsWith("t")`. |
| SSE test helpers moved to `conftest.py`; `board_card_adapter` deleted | Duplicated verbatim across two test modules; the helper was dead. |
| Check-question board header no longer slices the question | Cut through LaTeX and showed raw source. |

Skipped, with reasons:

- **Replacing the hand-rolled board buttons with `components/ui/button`.** It would change focus and disabled styling, and R4.3 requires the card components to render with no visual change. Worth doing when the board gets its next design pass.
- **Rewriting the two middlewares as plain ASGI.** `BaseHTTPMiddleware` adds two task-switch hops per SSE frame. Real, but not user-visible for one learner, and a rewrite of working request-handling code.
- **Moving `configure_logging` out of `create_app`.** Correct in principle — app construction should not mutate the root logger — but `--factory` has no other entry point to move it to.
- **Coalescing consecutive text deltas in `flush`.** Measured as a fraction of a millisecond per turn.


---

## Post-verification fixes

Applied after `/sdd:verify`. The report itself is in this conversation; these are the changes.

| # | Fix | Root cause |
|---|---|---|
| 1 | `max_history_entries` 60 → 400, documented as an abuse guard | A per-request entry cap was doing context management's job. One exchange adds three to five entries, so a session died at about a dozen exchanges with a 422 the client showed as "Célestin est injoignable", and retry re-posted the same oversized history. Fitting the transcript to the model is `history_token_budget`'s job, and it trims instead of rejecting. |
| 2 | The client reads FastAPI's `detail` shape, and the server's own error code now survives | A rejected request was disguised as a network failure, sending the learner to retry something that could never succeed. |
| 3 | Selecting a mock board no longer latches the whiteboard | `mockKey` overrode the session's card and was cleared only by selecting a tutor card, so after previewing a reference card, new cards, clears and marker clicks all stopped updating the display. Broke R4.4, R4.5 and R5.4 at once. Introduced by the cleanup pass. |
| 4 | `retry` rolls the failed turn back to a snapshot | It removed only the error entry, leaving the half-finished reply on screen and, worse, handing the model its own truncated sentence back as a finished message. |
| 5 | Inline maths opens only on a `$` that hugs its content and does not follow a figure | Greedy pairing meant "Le prix est 30$ et $x^2$ vaut 4" typeset " et " as maths and spilled the rest out as raw LaTeX. Prices are everywhere in this chapter's depreciation exercises. |
| 6 | Disconnect is checked as each event is produced, not only after 15 s of silence | An abandoned turn kept driving the provider to the last round. Design §3.5. |
| 7 | **A `quote` block now takes prose in `text` or a formula in `tex`, exactly one** | Found while verifying fix 3. The block only accepted LaTeX, so a definition quoted from the course went through KaTeX and came out with every accent detached — "arithme ˊ tique". Quoting a definition verbatim in the highlighter style is exactly what the pack's surlignées are, so the model had no correct field to use. **This changes design §4.2.** |

Not done, and deliberately: the two tasks below stay ticked for their artefacts but their promised tests do not exist, because vitest runs in a Node environment with no React testing library. What is covered is the pure reducer and pure splitter beneath them.

- **5.6** promised "cancel marks the partial entry interrupted; retry re-sends without duplicating" — `reduce`, `appendLearner` and `markInterrupted` are tested; `useTutorSession` itself is not.
- **6.1** promised "block types dispatch correctly" — `splitInlineMath` is tested; `BlockView` and `Blocks` are not.

Closing that gap means adding jsdom and a React testing library, which is a deliberate decision about how much frontend testing this project wants rather than a loose end to tidy.
