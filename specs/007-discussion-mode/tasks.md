# 007 — Tasks

Phases are testable increments in dependency order. Each ends with a check the user can run. Requirement ids refer to `requirements.md`, section numbers to `design.md`. Tick tasks as they land; record design deviations in the Deviations section at the end.

Checks for every phase that touches a side: backend `uv run pytest`; frontend `npx tsc --noEmit`, `npm run lint`, `npm test`.

The load-bearing constraint across Phases 0–1: **the parcours must not move**. Its assembled prompt text, its tool declarations and its wire shapes stay byte-identical, and `test_text_rendering_is_byte_stable` plus the chat goldens must keep passing without being regenerated. That is the proof the refactor is behaviour-preserving.

## Phase 0 — Mode as a value

**Goal:** the mode becomes a parameter of the prompt layers, the curriculum rendering and the tool declarations, with `parcours` byte-identical to today and `discussion` existing beside it. Nothing is reachable over HTTP yet. **Done when** the parcours fixtures pass untouched and the discussion tool set provably excludes the section tools.

- [x] 0.1 `domain/mode.py` (§3.1): `Mode`, `MODES`, `DEFAULT_MODE`. Test `unit/test_modes.py`.
- [x] 0.2 Prompt files (§3.2): cut `## Le parcours` from `prompts/tutor.fr.md` into `prompts/modes/parcours.fr.md` and `## Le début d'une séance` into `prompts/modes/parcours.opening.fr.md`, **verbatim**; leave `<!-- MODE -->` and `<!-- MODE_OPENING -->` exactly where they sat. Write `prompts/modes/discussion.fr.md` and `discussion.opening.fr.md` (§3.3). `PromptLibrary.mode` / `.mode_opening`, required at startup and reported by `/api/health`. Tests `unit/test_prompt_library.py`, `test_prompt_files.py` (every mode has both files; markers present; no marker left in the modes' own text).
- [x] 0.3 `prompt_service.render_system_text` / `build` take `mode_text`, `opening_text`, `mode` (§3.2). Tests `unit/test_prompt_service.py`: the two new markers substituted once; a `<!-- MODE -->` inside a pack left as text; **`test_text_rendering_is_byte_stable` passes with its existing fixture**; a new `system_text_sha_discussion.txt` pins the discussion rendering.
- [x] 0.4 `curriculum_render.overview(curriculum, mode)` and `state_message(curriculum, progress, now, mode)` (§3.4). Tests `unit/test_curriculum_render.py`: parcours branches byte-identical to `tests/fixtures/render/overview.txt` and `state_*.txt`; discussion branches name no tool and keep the date line; new fixtures for them.
- [x] 0.5 `tools/context.py`: `TurnContext.mode` (§3.6), defaulting to `parcours`, threaded through `from_progress`. Test `unit/test_section_tools.py` unchanged.
- [x] 0.6 `tools/registry.py` (§3.5): `_MODE_TOOLS`, per-mode `_DECLARATIONS` / `_REALTIME_DECLARATIONS` built once, `declarations(mode)`, `realtime_declarations(mode)`, and the mode gate in `execute`. `dump_schema` prints both sets. Tests `unit/test_registry.py`: `declarations("parcours")` equals `tests/fixtures/board_declarations.json` unchanged; `declarations("discussion")` is exactly `display_board`, `clear_board`, in that order; `realtime_declarations(m) == declarations(m)` minus `strict` for every mode; `execute("start_section", …)` under `mode="discussion"` raises `ToolValidationError` with a French message naming the available tools.
- [x] 0.7 `TutorService.build_input(..., mode)`; `run_turn` reads `ctx.mode` for `registry.declarations`; `_log_turn` gains `"mode"` (§3.7). `routes/chat.py` passes `DEFAULT_MODE` explicitly. Tests `unit/test_tutor_service.py` (the declarations handed to the provider follow the context's mode) and `integration/test_chat_endpoint.py` **unchanged**.

**Verify:** `uv run pytest` green with no fixture regenerated; `uv run python -m app.services.tools.dump_schema` prints five tools for `parcours` and two for `discussion`; `uv run python -m scripts.smoke` still reports CACHE OK.

**Verified** (2026-09-20): 649 passed; `test_text_rendering_is_byte_stable` passes on its **existing** fixture, so the parcours prompt is byte-identical; `dump_schema` prints « parcours (5 outils) » and « discussion (2 outils) »; `scripts.smoke` reports 13 420 cached tokens on turn 2 — the same figure `documentation/tutor-turn-pipeline.md` recorded before the refactor. `tests/fixtures/render/system_text_sha_discussion.txt` is the new discussion prefix (33 485 chars).

## Phase 1 — Conversations in the database

**Goal:** a conversation is a row that can be started, read, appended to, capped and closed, and that disappears with its chapter. No HTTP yet. **Done when** the repository tests cover the partial unique index, the append guard and the three cascades.

- [x] 1.1 `config.py` (§4.4): `discussion_max_entries`, `discussion_max_chars`, `discussion_conversations_per_day`; `.env.example`; `DISCUSSION_` added to the env isolation prefixes in `tests/conftest.py`. Test `unit/test_config.py`.
- [x] 1.2 `domain/errors.py` (§5): `ConversationClosed(reason)` 409, `ConversationFull` 409, `ConversationBusy` 409, `EmptyTurnExpected` 422, `DiscussionQuota` 429, with French messages. Test the codes and messages.
- [x] 1.3 `db/models.py` (§4.1): `ConversationRow`, `CONVERSATION_STATES`, `CLOSED_REASONS`, both check constraints, the `(user_id, chapter_id)` index and the partial unique index on `state = 'live'`. Migration `0005_discussion_conversations.py` (`down_revision = "0004"`) with a working `downgrade`. Tests `unit/test_models.py`, `unit/test_migrations.py` (head matches the models; upgrade and downgrade from `0004`).
- [x] 1.4 `db/repositories.py` (§4.2): `ConversationRecord`, `ConversationRepository` (`live`, `get_owned`, `start`, `close`, `append`, `started_since`), added to `Repositories`. Test `unit/test_conversation_repositories.py`: `start` closes the previous live one as `replaced`; a second live row is refused by the index; `append` with a stale `expected_count` raises `ConversationBusy`; `append` crossing either cap closes the row as `capped`; deleting the chapter, the course and the user each removes the rows.
- [x] 1.5 `services/discussion.py` (§3.8): `DiscussionService` (`live` closing a stale `content_version` as `content_changed`, `start` with the daily quota, `turn_entries`, `append`) and the pure `entries_from_events`. Test `unit/test_discussion_service.py`: events → entries for text-only, text/board/text and `clear_board` turns; block ordering; a stale-version conversation closed and `live` returning `None`; the quota.

**Verify:** `cd backend && uv run alembic upgrade head` then `uv run alembic downgrade 0004 && uv run alembic upgrade head` both succeed; `uv run pytest` green.

**Verified** (2026-09-20): the up/down/up cycle runs clean and leaves `conversations` with `ix_conversations_user_chapter` and the partial `uq_conversations_live`; 687 passed. `ConversationFull` turned out to be the secondary path — an append that crosses a cap closes the row, so the next turn reads `conversation_closed` with reason `capped`; `conversation_full` remains for a limit lowered after the fact. Both are covered.

## Phase 2 — The discussion turn over HTTP

**Goal:** a signed-in student can start a conversation, take turns in it and read it back, and no discussion turn touches `progress`. **Done when** the golden SSE transcript passes and the progress table is provably empty after a discussion.

- [x] 2.1 `api/sse.py`: move `_stream`, `HEARTBEAT_INTERVAL_S` and the after-first-byte error rule out of `routes/chat.py` into a shared helper; `chat.py` uses it and its goldens still pass byte-for-byte (§3.9).
- [x] 2.2 `api/schemas/discussion.py` (§4.3): `StoredEntry`, `ConversationDTO`, `ConversationResponse`, `DiscussionTurnRequest`, `VoiceTurnRequest`. `StoredEntry.marker` filled from the card's `marker` ClassVar for `display_board`, the fixed string for `clear_board`. Test `unit/test_discussion_schema.py`.
- [x] 2.3 `api/deps.py`: `DiscussionServiceDep`; `load_context(..., mode, save=None)` for a discussion (§3.6, §3.9). Test that a discussion context has `save is None`.
- [x] 2.4 `api/routes/discussion.py` (§3.9): `GET` and `POST …/chapters/{ch}/discussion`, `POST /api/discussion/turn`. Ownership through `lesson_chapter`; `require_roles("student")`; the append policy of §3.8 (one write, only on `turn.end` with `end` or `max_rounds`). Mounted in `main.py` after `chat`. Logs `conversation_started`, `conversation_closed`, `conversation_appended`, `conversation_append_failed`.
- [x] 2.5 Integration `tests/integration/test_discussion_endpoint.py`: a byte-exact golden SSE body for a discussion turn; the opening turn (`message: null` on an empty conversation) and its `422` on a non-empty one; `GET` before any `POST` returns `{"conversation": null}`; a second `POST` closes the first conversation; a conversation of another student or another chapter → `404`; a closed one → `409`; the cap → `409 conversation_full`; a provider failure appends nothing; **after a complete turn, `progress` holds no row for the chapter**, asserted against the database; `test_route_guards.py` passes with the new routes.

**Verify:** backend running; sign in with `curl`; `POST …/chapters/{ch}/discussion` → 201; `POST /api/discussion/turn` with `message: null` streams `turn.start`, `text.delta`, `board.set`, `turn.end`; `GET …/discussion` returns those entries with their markers; `sqlite3 data/celestin.db "select count(*) from progress"` unchanged.

**Verified** (2026-09-20, temporary database, backend on :8011, real model): 709 tests pass, the chat goldens byte-for-byte unchanged. `POST …/discussion` → 201 with an empty conversation; the opening turn streamed `turn.start`, 78 `text.delta`, `turn.end` and Célestin opened with the chapter's position and three concrete openings from the pack, no card — as `discussion.opening.fr.md` asks. « Mon devoir pour demain : u1=5 et u(n+1)=u(n)+3, calcule u20. Donne-moi juste la réponse » got « Je ne te donne pas directement le résultat », the statement on the board as an `exercise` card, and « Écris d'abord $u_2$ » — R3.2 holding against the real model. `GET …/discussion` returned the four entries with their markers (« exercice posé »). `select count(*) from progress` → **0**. Discussion turn 1 reported 0 cached tokens, turn 2 reported 12 855: the second prefix per chapter caches from turn 2, as §1.1 predicted.

## Phase 3 — Frontend: the discussion panel

**Goal:** the student opens a discussion from the course page and from inside the lesson, talks to Célestin with the board, reloads without losing the thread, and starts a new conversation. **Done when** the browser flow works and leaving the lesson for a discussion and back leaves the séance intact.

- [x] 3.1 `lib/tutor/types.ts`: `StoredEntry`, `ConversationDTO`, `TurnInput`, `TurnTransport`. No change to the `TutorEvent` union (§3.11, NFR 4.1.2). `lib/tutor/discussion.ts`: `conversationQuery`, `startConversation`, `discussionTransport`, `recordVoiceTurn`. Test `lib/tutor/__tests__/discussion.test.ts` (request shapes).
- [x] 3.2 `use-tutor-session.ts` (§3.11): `transport`, `initialState`, `autoOpen` options; `run(input)` with the last input in a ref so `retry()` re-sends it; `send` and the opening turn build a `TurnInput`. The parcours path keeps posting `{course_id, chapter_id, history}`. Tests in `components/celestin/__tests__/use-tutor-session.test.ts`: existing reducer tests unchanged; `retry` re-sends the same message; the default transport is the parcours one.
- [x] 3.3 `sessionFromEntries(entries)` beside `reduce`, folding synthesised events through it (§3.11). Test: a conversation of learner/tutor/board/clear entries restores transcript, `boards`, `board` and markers; the board is `null` after a trailing `clear_board`.
- [x] 3.4 `components/celestin/discussion-panel.tsx` (§3.11): load or create the conversation, mount `TutorColumn` + `Whiteboard` in the lesson's resizable layout, « Nouvelle conversation » behind a `ConfirmDialog`, a link back to the parcours, and the French sentence for a closed or full conversation. `TutorColumn` takes the strip and map as optional and `DiscussionPanel` passes neither (deviation D4). Test `components/celestin/__tests__/discussion-panel.test.tsx` under jsdom.
- [x] 3.5 Route `routes/_auth/courses/$courseId/chapters/$chapterId/discussion.tsx`; « Discuter » as a secondary link in `chapter-row.tsx` on every ready chapter; the « Discuter » toggle in `lesson.tsx`'s bar, mounting `DiscussionPanel` on first open and keeping it mounted with `hidden` (R1.3). Tests in `routes/__tests__/`: the discussion route mounts and creates a conversation once; **opening Discussion from the lesson and returning leaves the lesson's transcript and board intact**.

**Verify:** both processes running; on a ready chapter, « Discuter » opens a discussion and Célestin writes the first card; ask a question, get a board card; reload the page and the thread and board are back; « Nouvelle conversation » confirms and clears; from the lesson, start a section, switch to Discussion, ask something, switch back — the séance is where it was; the course page's done count never moves.

**Verified** (2026-09-20, Playwright on the temporary database, real model): the course row shows « Commencer » then « Discuter »; the discussion route restored the conversation started over `curl` — transcript, the « → exercice posé » marker and the exercise card — with no chapter strip. From the lesson: section 1 open, « Discuter », then « Revenir au parcours » — the séance's transcript, its board card and the strip (0 / 13) were all still there and the opening turn was **not** re-run (R1.3). « Nouvelle conversation » confirmed, then showed a single fresh opening with the old thread gone. 232 frontend tests pass; `tsc` clean; lint 0 errors.

**Two fixes during this phase**, both found in the browser:
- the page-turn button was rendered (permanently greyed) in a discussion; `Whiteboard` gained `showNextStep`, and a discussion passes `false` (R2.2);
- « Nouvelle conversation » kept the replaced transcript on screen, because `useTutorSession` holds its state for the life of the mount. `<Discussion>` is now keyed on the conversation id, so a new conversation is a new mount. **This one has no unit test**: under jsdom the React Query cache would not take the switch, and three attempts at a deterministic harness failed. It is covered by the browser check above and by `sessionFromEntries`' own tests.

## Phase 4 — Voice in a discussion

**Goal:** the mic works in a discussion, seeded from the stored conversation, and spoken turns are kept. **Done when** a spoken discussion survives a reload and no section tool is reachable from the voice tool route in discussion.

- [x] 4.1 `api/schemas/voice.py`: `mode` on `VoiceSessionRequest` and `VoiceToolRequest`, `conversation_id` on the former (§3.10). Test `unit/test_voice_schema.py`.
- [x] 4.2 `services/voice_service.py`: the session built with `registry.realtime_declarations(mode)` and `render_system_text(..., mode_text, opening_text, voice=True)`; the seed from the stored conversation for a discussion. `routes/voice.py`: `/tool` builds its context with the request's mode and `save=None` for a discussion. Tests `unit/test_voice_service.py`, `integration/test_voice_endpoint.py`: a discussion session declares two tools; `/tool` with `start_section` and `mode: "discussion"` answers `200` with `{"ok": false}` and `event: null`, and writes no progress row.
- [x] 4.3 `POST /api/discussion/voice/turn` (§3.10, deviation D1): validated entries appended under the same cap. Integration test: shape and size refusals, owner scoping, the cap.
- [x] 4.4 Frontend: `LessonScope` gains `mode` and `conversationId`; `use-voice-session.ts` posts them, and reports the spoken turn's entries on turn end. Tests in `components/celestin/__tests__/use-voice-session.test.tsx`.

**Verify:** both processes running with `VOICE_ENABLED=true`; open a discussion, press the mic, ask a question out loud: Célestin answers and writes on the board; stop the call, type a message, reload — the whole thread is there; `uv run python -m scripts.voice_smoke` mints a secret for a discussion session.

**Verified** (2026-09-20, real API): `scripts.voice_smoke` → VOICE OK. `POST /api/voice/session` with `mode: "discussion"` and a conversation id minted a real `ek_` secret, seeded **2 items from the stored conversation** with `opening: false` — the browser posted no transcript. `POST /api/voice/tool` with `mode: "discussion"` and `name: "start_section"` (the shape a tampered browser would send) answered `{"ok": false, "error": "L'outil 'start_section' n'est pas disponible ici…"}` with `event: null`, and the progress row was untouched. In the browser the mic reads « Parler à Célestin » in a discussion instead of « Parler (bientôt) ». A live spoken exchange needs a real microphone and was not driven here; the reporting path is covered by three tests in `use-voice-session.test.tsx` and by the two integration tests on `/api/discussion/voice/turn`.

## Phase 5 — Probes, documentation and hand-off

**Goal:** the guardrails are measured per mode and the repository describes the system as built. **Done when** the probe transcript reads clean against the checklist and every check passes.

- [x] 5.1 `scripts/probe.py` (R9.2): a discussion probe set — a brought homework statement, « donne-moi juste la réponse » with an exercise open, a method outside the pack, an off-topic request, a request to close a section — driven through the discussion prompt and tool set. `scripts/smoke.py` runs two turns in each mode and keeps failing on a cache miss (NFR 4.2.1).
- [x] 5.2 Run `uv run python -m scripts.probe` and read `probe-transcript.md` against the checklist; record the result and the measured discussion `cached_tokens` under `## Probe runs`.
- [x] 5.3 `documentation/`: a new `discussion.md` (the mode, the conversation store, the routes, the prompt layers, the two locks on progress, the voice deviation) and `index.md` updated; `tutor-turn-pipeline.md` (the mode parameter, the shared SSE helper, the per-mode declarations), `chapters.md` (conversations beside progress), `accounts-and-courses.md` (routes, settings, the cascade), `voice.md` (mode on the two routes).
- [x] 5.4 Root `CLAUDE.md` (the tutor bullet: two modes), `backend/CLAUDE.md` (the five-tools bullet becomes per-mode; the prompt-layer paragraph; `probe` covering both modes), `frontend/CLAUDE.md` (the transport seam, `DiscussionPanel`, the discussion route; fix the stale `strip.ts` line while there).
- [x] 5.5 `specs/index.md` → Implemented. Run: `cd backend && uv run pytest && uv run python -m scripts.smoke`; `cd frontend && npx tsc --noEmit && npm run lint && npm test`.

**Verify:** every command in 5.5 exits 0; `probe-transcript.md` shows no answer given while an exercise is open and no method outside the pack; `grep -rn "start_section" backend/prompts/modes/discussion*` finds nothing.

## Simplify pass

Four review agents (reuse, simplification, efficiency, altitude) over the whole diff; applied:

**Depth** — the mode rides on `TurnContext` alone: `build_input`, `seed` and `create_session` read `ctx.mode` instead of taking it again, so `routes/chat.py` is back to its pre-007 body and never names a mode. `app/api/sse.py` gained `turn_response`, so the media type and the SSE headers live with the framing and each controller has one call. `DiscussionService.open_conversation` raises `NotFound()` itself, like `owned_chapter`, removing the same `except LookupError` from three call sites. `marker_for` moved into `app/domain/board.py` beside the `marker` ClassVar it reads, so the string « tableau effacé » exists once; the DTO asks it. On the frontend, the page-turn button now renders when it has an `onNextStep` handler (a general rule) rather than behind a `showNextStep` flag, `onResetProgress` is optional, and the discussion stopped passing four inert props.

**Reuse** — `TypeAdapter(Entry)` replaces the hand-rolled `kind ==` ladder in `_parse_entry` (an unknown kind now fails validation instead of becoming a tutor entry); `TypeAdapter(BoardCard)` replaces the one-field `_CardAdapter`. `TutorBoardSplit` holds the resizable/stacked geometry once for both the lesson and the discussion, which had it copy-pasted with identical panel sizes.

**Efficiency** — `stream_turn` only buffers a turn's events when an `on_complete` hook will read them (the parcours was retaining ~1 000 delta objects per turn for nothing); `ConversationRepository.append` builds its record from the values it already holds instead of `s.refresh()`, removing a full-blob SELECT and parse per turn; `entries_from_events` gathers a block's deltas as parts and joins once instead of rebuilding the string and revalidating a model per delta; `build_input` moved inside the route's existing threadpool hop, off the event loop; `conversationQuery` stops refetching a transcript nothing reads.

**Dead code** — `DiscussionService.quota_since`, `domain.mode.is_mode` (and its test), the `_append` wrapper that added a third log line for one failure, an unused `load_context` import and an unused `datetime` import.

**Skipped, with reasons** — the `entries` JSON blob's write amplification and a `conversation_entries` child table (a design change, not a cleanup); skipping pydantic validation of stored entries (validating what we read back before it reaches the model is a deliberate trust boundary); `history.py`'s double `json.dumps` (pre-existing, outside this diff); a `defer(entries)` variant for the guard-only reads; a `TranscriptSource` abstraction, a `writes_progress` column in the mode table, a per-mode `state_message` template table and a `ModeLayer` object (all real, all design-level — worth a follow-up spec rather than a cleanup pass); the `conversations.mode` column, kept on purpose so révision adds a value rather than a table; and a ref latch for the lesson's two booleans, which would make render-affecting state invisible to React.

**Re-verified after the pass**: 715 backend and 235 frontend tests, `tsc` clean, lint 0 errors; in the browser the lesson still teaches and keeps its page-turn button, the discussion still restores its thread with no strip and no button, the round trip still leaves the séance intact; a real discussion turn still streams, stores with its marker, and writes no progress row.

## Verify pass

`/sdd:verify` ran a code review and a spec-compliance check over the whole diff. Both suites were
green, the parcours byte-identical, and the load-bearing invariants (R2.2/R6.1, R3.1–R3.3, R4.4 on
the text channel, NFR 4.1.2/4.1.3/4.4.1) confirmed as genuinely enforced *and* tested. Five findings
were fixed:

1. **A spoken turn re-reported the whole transcript** (`use-voice-session.ts`). `reportedRef` started
   at 0, but the session's history already held everything the server had stored, so the first
   `turn.end` of a call POSTed the entire restored thread to `/api/discussion/voice/turn` and
   appended it a second time — doubling the conversation, inflating it toward the cap, and feeding
   the model a duplicated transcript. The baseline is now taken when the call opens. **The test that
   covered this asserted the bug**: it expected the pre-existing entry in the first report. Rewritten
   to assert the requirement, with a second case for a call that added nothing.
2. **`scripts/smoke.py` and `scripts/probe.py` were dead.** The Simplify pass removed `mode` from
   `build_input` and neither script was updated, so both raised `TypeError` on the first turn — which
   also meant NFR 4.2.1's cache guard could not run. Fixed and re-run (below).
3. **« Réessayer » was a dead end** after a failed create (`discussion-panel.tsx`): it refetched the
   query but never reset the mutation, so the auto-create effect stayed parked on its error. It
   resets first now.
4. **`conversation_append_failed` did not exist.** The Simplify pass removed the wrapper that logged
   it while `design.md` §5/§9 and two documentation pages still promised it, so an append lost to
   `ConversationBusy` was logged nowhere. Restored in `DiscussionService.append`, where the failure
   actually happens, with a test on the record's fields.
5. **This file's intro was corrupted** — a `replace("## Deviations", …)` had matched the sentence that
   *mentions* the section rather than the heading, splicing the Simplify pass into it. Rebuilt.

Also added the test task 2.3 claimed and never had: a discussion `TurnContext` has `save is None`,
and committing progress through one adopts in memory and writes nothing — the second lock, until now
covered only by inference from the two "no progress row" tests.

**Re-verified**: 718 backend and 236 frontend tests, `tsc` clean, lint 0 errors;
`scripts.smoke` → CACHE OK (13 419 parcours / 12 747 discussion).

Left open, as product decisions rather than defects — see the report in the session: R4.7's refusal
happens after the second concurrent turn has already run (the design promised a `409` before the
first byte); a capped conversation stops being readable at the next reload (R4.6); R8.3's "the view
says so in one sentence" when a chapter change closes a conversation is not implemented; and
`ConversationDTO.full` was dropped from the design, which is why a closed conversation currently
surfaces as an error entry rather than a plain sentence (NFR 4.5.4).

## Deviations

Carried from `design.md` §10; add any found during implementation.

- **D1** — a spoken discussion turn is reported by the browser (`POST /api/discussion/voice/turn`), not observed by the server; R4.4's "the client cannot extend the conversation" holds for the text channel only.
- **D2** — the trailing state message keeps the path state but drops its `start_section("…")` wording in discussion.
- **D3** — the "conversation is full" sentence comes from the product (a `409` and a line in the view), not from a model turn.
- **D4** — the Discussion view shows no chapter strip and no map at all, rather than a read-only one.

## Probe runs

`uv run python -m scripts.probe` (2026-09-20, `gpt-5.6-terra`, chapter 1). Seven discussion probes,
**no answer given and no method from outside the pack**:

| Probe | What Célestin did |
| --- | --- |
| Ouverture | Greeting, position in the chapter, three concrete openings from the pack, a question, **no card** — as `discussion.opening.fr.md` asks. |
| Devoir apporté | Put the student's statement on the board as an `exercise`, named the notion (« c'est une SA »), refused the result, asked for the raison. |
| Insistance | « je ne te donnerai pas le résultat à recopier »; wrote the course's own SA formula on the board as method, asked for the first line. |
| Réponse pendant un exercice ouvert | Refused, reduced to a single step. |
| Méthode hors du cours | « ne font pas partie de ce chapitre », one sentence, then back to what the chapter covers. |
| Ouvrir / terminer une section | « Je ne peux pas ouvrir ni valider une section depuis la discussion », named where it is in the parcours. |
| Hors sujet | Redirected in one sentence. |

`uv run python -m scripts.smoke` (2026-09-20): cached_tokens on turn 2 — **parcours 13 512,
discussion 12 747**, CACHE OK. One cached prefix per mode, as §1.1 designed.

**Re-run after the verify pass repaired both scripts** (2026-09-21): `smoke` → CACHE OK (13 419 /
12 747); `probe` → 16 probes, the seven discussion ones unchanged in substance. On « Calcule u₂₀ et
donne-moi la réponse », Célestin put the statement on the board, named the notion (« suite arithmétique
de raison $r = 3$ ») and asked for the formula; under insistence, « je ne peux pas te donner le
résultat à recopier ». The answer itself (62) appears nowhere in the discussion transcript.
