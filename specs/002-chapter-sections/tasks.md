# 002 — Tasks

Phases are testable increments in dependency order. Each ends with a check the user can run. Requirement ids refer to `requirements.md`, section numbers to `design.md`. Tick tasks as they land; record design deviations under the phase they occurred in.

## Phase 0 — Content

**Goal:** the chapter is two reviewable files. **Done when** both parse and the parent has read them.

- [x] 0.1 Trim `courses/chapitre_1/pack.md` to sequences; keep §1–§8 numbering; state the exclusion in the header. (R1)
- [x] 0.2 Draft `courses/chapitre_1/curriculum.yaml`, 13 sections, quoted scalars where a colon appears. (R2.8)
- [ ] 0.3 Parent review of the curriculum: granularity, beats wording, counts, `done_when`. Edit in place.

**Verify:** `uv run python -c "import yaml; print(len(yaml.safe_load(open('../courses/chapitre_1/curriculum.yaml'))['sections']))"` prints 13.

## Phase 1 — Curriculum in the backend

**Goal:** the backend loads and validates the curriculum and serves the chapter overview. **Done when** `/api/chapters/current` returns 13 sections and a broken file fails startup with the section named.

- [x] 1.1 Add `pyyaml` to `backend/pyproject.toml`; `uv sync`. Add a `types-PyYAML` dev dependency if the type checker complains.
- [x] 1.2 `app/domain/curriculum.py`: `Section`, `Curriculum`, `Kind`, cross-field validators (§4.1). Tests `tests/unit/test_curriculum.py`: real file loads; fixtures `tests/fixtures/curricula/{duplicate_id,teach_no_beats,practise_no_count,unknown_key}.yaml` each fail naming the section.
- [x] 1.3 `app/domain/errors.py`: `CurriculumInvalid(path, detail)` and `CurriculumUnavailable` (500, French). Test in `test_curriculum.py`.
- [x] 1.4 `app/config.py`: `curriculum_path`, validated like the other paths. Test `test_config.py`.
- [x] 1.5 `CourseService`: third mtime-cached file, `get_curriculum()` parsing on change, `is_available()` over three files, `get_meta()` returning `ChapterMeta {id, title, sections}`. Tests `test_course_service.py`: reload on mtime change, unavailable when the file is missing.
- [x] 1.6 `create_app`: call `get_curriculum()` at startup; failure aborts with path and section. Test `test_app.py`.
- [x] 1.7 `app/api/schemas/chapter.py` and `app/api/routes/chapters.py`: `GET /api/chapters/current` (§3.1), `Cache-Control: no-store`. Remove `routes/courses.py` and `test_courses_route.py`. Test `tests/integration/test_chapters_endpoint.py`: shape, `index` 1-based, no `beats`/`exercises`/`done_when` keys, header.
- [x] 1.8 `routes/health.py`: `curriculum_loaded`, `sections`. Test in `test_app.py`.

**Verify:** run the backend; `curl -s localhost:8000/api/chapters/current | jq '.sections | length'` prints 13; `curl -s localhost:8000/api/health` shows `curriculum_loaded: true`. Break the YAML, restart, see the error name the file.

## Phase 2 — Path rules, section tools, prompt

**Goal:** the tutor works section by section and the path is enforced in the tools. **Done when** a scripted turn produces `section.start` / `section.done` events and a locked section is refused, with the cached prefix intact.

- [x] 2.1 `app/domain/progress.py`: `Progress` frozen dataclass, `normalise(dto, curriculum)` dropping unknown ids, raising `InvalidProgress` (422) on `active` unknown or in `done`. Test `tests/unit/test_progress.py`.
- [x] 2.2 `app/api/schemas/chat.py`: `ProgressDTO`, `ChatRequest.progress` with default. Test `test_chat_schema.py`.
- [x] 2.3 `app/services/path.py`: `section_states`, `can_start`, `can_complete`, `next_section`, `Refusal` (§3.4). Test `tests/unit/test_path.py`: the four-state table for empty, mid-chapter with active, mid-chapter without active, complete; `can_start` and `can_complete` on every state. Write the cases as `tests/fixtures/path_cases.json` (shared with the frontend in 3.2).
- [x] 2.4 `app/services/curriculum_render.py`: `overview`, `brief`, `state_message` (§3.5). Test `tests/unit/test_curriculum_render.py` against snapshot files in `tests/fixtures/render/`.
- [x] 2.5 `app/services/tools/registry.py`: `TurnContext(curriculum, progress)`; `execute(name, arguments_json, ctx)`; `ToolOutcome.output: str | None`; `replay_output(name, arguments, ctx)`. Board tools accept and ignore `ctx`. Test `test_registry.py`: declaration order is `display_board, clear_board, start_section, complete_section`; board declarations byte-identical to before (pin with a snapshot).
- [x] 2.6 `app/services/tools/section.py`: args models, `SectionStarted`, `SectionCompleted`, handlers using `path` and `curriculum_render`. Test `tests/unit/test_section_tools.py`: brief on success, review flag on a done section, refusal messages name the startable section, `complete_section` output names the next section or « Chapitre terminé. », summary length bounds.
- [x] 2.7 `app/api/schemas/events.py`: `SectionStartEvent`, `SectionDoneEvent`, markers (§3.2). Test `test_events.py`.
- [x] 2.8 `TutorService`: `build_input(entries, progress)` passes curriculum and progress to `prompt_service`; `run_turn(items, ctx)` emits the two events, applies successful section outcomes to `ctx.progress`, sends `{"ok": true, "result": output}` when an output exists; logs `section_active`, `section_started`, `section_completed`. Test `test_tutor_service.py`: complete-then-start in one turn sees the updated state; refused start emits no event; `max_rounds` leaves progress untouched.
- [x] 2.9 `history.to_provider_input(entries, budget, ctx)`: replayed section tool entries carry the recomputed brief. Test `test_history.py`.
- [x] 2.10 `prompt_service.build(prompt, pack, curriculum, progress, history_items)`: both markers required, state message last (§3.7). Test `test_prompt_service.py`: first item byte-identical across two builds with different progress and history; last item is the state message; missing marker raises.
- [x] 2.11 `routes/chat.py`: normalise progress, build the context, pass it through. Golden transcript in `tests/integration/test_chat_endpoint.py`: a turn with `start_section` then text, a turn with `complete_section`, a refused `start_section` with no event; `InvalidProgress` gives 422 with a French body (`test_hardening.py`).
- [x] 2.12 `prompts/tutor.fr.md`: `<!-- CURRICULUM -->` marker; « Le parcours » section (opening, per-kind behaviour, reviews, completion only via the tool, « l'outil te dira si une section n'est pas ouverte », the « Ma réponse à la question : … » message); rewrite « Le début d'une séance ». Test in `test_prompt_service.py` that the real prompt file contains both markers.
- [x] 2.13 `scripts/probe.py`: locked-section probe and premature-completion probe (§6). `scripts/smoke.py`: run, confirm cached tokens on turn two.
- [x] 2.14 `tests/unit/test_layering.py` still passes.

**Verify:** `uv run pytest` green. `uv run python -m scripts.smoke` reports cached tokens on turn two. `uv run python -m scripts.probe` shows the locked-section probe passing. `curl -N localhost:8000/api/chat -H 'content-type: application/json' -d '{"history":[],"progress":{"done":[],"active":null}}'` streams a `section.start` for `suites` in the opening turn.

## Phase 3 — Frontend transport and progress state

**Goal:** the browser carries progress across reloads and shows section markers. **Done when** completing a section, reloading, and sending a message resumes the next section.

- [x] 3.1 `lib/tutor/types.ts`: `SectionKind`, `SectionOverview`, `Chapter`, `Progress`, `SectionState`, the two events in `TutorEvent` (§3.9). `client.ts`: post `{history, progress}`. Test `lib/tutor/__tests__/client.test.ts` asserts the body shape.
- [x] 3.2 `lib/tutor/path.ts`: `sectionStates(chapter, progress)`. Test `lib/tutor/__tests__/path.test.ts` driven by `path_cases.json` copied from the backend fixture (2.3).
- [x] 3.3 `lib/tutor/progress-store.ts`: `loadProgress`, `saveProgress`, `clearProgress`, key `celestin.progress.<chapterId>`, `v: 1`, try/catch, unknown ids dropped. Test `lib/tutor/__tests__/progress-store.test.ts`: round trip, malformed JSON, wrong version, ids not in chapter.
- [x] 3.4 `lib/tutor/chapter.ts`: `fetchChapter`, `useChapter` (`queryKey: ["chapter"]`, `staleTime: Infinity`).
- [x] 3.5 `use-tutor-session.ts`: `progress` in `SessionState`; reducer cases for `section.start` (review leaves `active`) and `section.done`, each adding a marker and a tool history entry; `useTutorSession(chapter)` restores progress before the opening turn, persists on change, exposes `progress` and `resetProgress()`; on a 422 from `/api/chat` clear the store and retry once. Tests in `__tests__/use-tutor-session.test.ts`.
- [x] 3.6 `routes/index.tsx`: load the chapter, pass it to the hook and the column; render a skeleton strip until loaded, error state on failure.

**Verify:** start the app; the opening turn starts section 1 and a « section commencée » marker appears; ask Célestin to finish the section (or drive it through); reload; the state message resumes section 2 and `localStorage` holds `celestin.progress.suites`.

## Phase 4 — Chapter strip and map

**Goal:** progress is visible at all times and the full path on demand. **Done when** the strip, the sheet, review, start and reset all work on desktop and phone widths.

- [x] 4.1 `components/celestin/chapter-strip.tsx`: title, segmented bar (13 segments, `success` / `primary` / `border`), active line, count, states for « à suivre » and « chapitre terminé »; the whole strip is a button opening the sheet (§3.11). Test `__tests__/chapter-strip.test.tsx`: segment classes per state, label per state.
- [x] 4.2 `components/celestin/chapter-map.tsx`: shadcn `Sheet` (left, 380 px / full width), rail, four row states, active row shows its goal, « Revoir » on done rows, start button on the available row when nothing is active, locked rows `aria-disabled`, buttons disabled while streaming, sheet closes after an action. Test `__tests__/chapter-map.test.tsx`: `send` called with the exact French sentences; no button on locked rows.
- [x] 4.3 Reset: `DropdownMenu` in the sheet header, `AlertDialog` confirm, calls `resetProgress()`. Test: confirm calls reset, cancel does not.
- [x] 4.4 `tutor-column.tsx`: replace `SessionPlan` with `ChapterStrip`; remove `plan` and `PlanItem` from `session.ts` (keep `BoardStatus`); marker entries with `boardIndex: null` render non-clickable.
- [x] 4.5 Phone width: strip above the chat panel, sheet full width. Check with `useIsDesktop` false in tests.
- [x] 4.6 `npx tsc --noEmit`, `npm run lint`, `npm test`.

**Verify:** on desktop the strip shows « 0 / 13 » then « ● 1 · Cours · Suites numériques » after the opening turn; open the sheet, see 13 rows with section 1 active and the rest locked; after section 1 is done, « Revoir » on row 1 sends the review sentence and Célestin starts a review without changing the strip; reset returns to 0 / 13 and restarts the conversation. Resize below 1024 px and repeat.

## Phase 5 — Check-question feedback

**Goal:** teaching sections can end on a check question the tutor sees. **Done when** picking an option produces a learner message and a tutor reaction.

- [x] 5.1 `whiteboard.tsx`: `onAnswer` on `CheckQuestionBoard`, forwarded by `Whiteboard`; `routes/index.tsx` wires it to `session.send` with « Ma réponse à la question : « {text} ». ». Test `__tests__/whiteboard.test.tsx`: clicking an option calls `onAnswer` with the option and correctness; the card still shows local feedback.
- [x] 5.2 Prompt already expects the message (2.12); confirm with one real turn.

**Verify:** in section 1, reach the check question, pick an answer, see the learner message in the transcript and Célestin react to it before moving on.

## Phase 6 — Documentation and hand-off

**Goal:** the next reader finds the system as built.

- [x] 6.1 `documentation/tutor-turn-pipeline.md`: request body with `progress`, state message placement, the two events, `TurnContext`, replay of section outputs, the `/api/chapters/current` route.
- [x] 6.2 New `documentation/chapters.md`: pack + curriculum, section kinds, path rules, where progress lives, how to edit the curriculum and what invalidates the cache. Add to `documentation/index.md`.
- [x] 6.3 `backend/CLAUDE.md` and `frontend/CLAUDE.md`: the new files and the rule that section events are part of the SSE contract.
- [x] 6.4 `specs/index.md`: status of 002.
- [x] 6.5 Full run: `uv run pytest`, `npm test`, `npx tsc --noEmit`, `npm run lint`, `uv run python -m scripts.smoke`.

**Verify:** the manual scenario end to end: fresh browser → section 1 → complete → reload → section 2 resumes → ask for section 7 → refused in the conversation → review section 1 → no state change → reset → section 1.

## Addenda after hand-off

- **Empty board.** The six mock boards kept by spec 001 R4.8 and the preview detour are removed; the history strip shows only this session's cards.
- **No card-level actions.** The inert or duplicated buttons on the cards are gone (« Explique autrement », « Un exemple de plus », the worked example's own step reveal and « Pourquoi cette étape ? », the exercise answer field, hint toggle, camera and « Valider », « Fermer la séance »). Acting on the board means talking to Célestin. Worked examples show every step; the faded mode is run by Célestin in the conversation (prompt updated). The exercise answer widget returns with the checker.
- **« Étape suivante ».** A `propose_next_step` tool and a `step.ready` event: the tutor lights a button under the board when satisfied with the exchange, ends its turn, and the next card comes only after her click (a learner message « Étape suivante. ») or explicit agreement. Prompt rule « C'est elle qui tourne la page ». Pace stays a prompt habit; nothing in code forbids a card after a card. After `section.done` the same button reads « Section suivante » (surviving the recap card) and its click asks Célestin to open the next section; the prompt tells Célestin to wait for it.

## Deviations

- **Phase 2.** Progress normalisation lives in `TutorService.build_input`, not in the chat controller as design §3.2 said. The controller stays free of business logic (001 layering rule) and the service already owns the curriculum. The 422 path is unchanged.
- **Phase 3.** Progress is restored synchronously in the hook's initial state, and the route mounts the lesson only once the chapter query has settled (design §3.10 had the hook wait on a `ready` flag). A first version restored in an effect and the persist effect overwrote storage with the empty default; the state shape now makes that race impossible.
- **Simplify pass.** An inconsistent `progress` (an `active` that is unknown or already done) is repaired server-side like unknown ids, not rejected with a 422 (design §4.2, §5). The client already repaired both cases on load, so the 422 and its retry loop were reachable only from corrupted in-memory state; both are gone.
- **Simplify pass.** Section tools apply their own progress transition to the turn context (design §3.6 had the service do it after the fact), and `Section` carries its `index` and `label` instead of `Curriculum.index_of`.
- **Phase 4.** Reset is a plain footer link in the map sheet opening the confirm dialog, not a dropdown menu: one fewer Radix layer, easier for the learner to find, and testable in jsdom.
- **Phase 4.** The tutor header does not repeat the active section (R7.6): the strip sits directly under it and always names the section, so the header line would have been a duplicate.
- **Phase 2.** The curriculum ships with a `pack` field per section and an `index_of` helper on the domain model; both are informative and used by rendering only.
