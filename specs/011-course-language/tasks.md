# 011 — Tasks

Phases are testable increments in dependency order. Each ends with a check the user can run. Requirement ids (`R1`…) refer to `requirements.md`, section numbers (`§`) to `design.md`. Tick tasks as they land; record design deviations in the Deviations section at the end.

Work on `feature/course-language`, merged in one go.

Checks for every phase that touches a side: backend `uv run pytest`; frontend `npm run typecheck`, `npm run lint`, `npm test`.

The load-bearing constraint across the whole epic: **French does not move.** The only edits to existing tests are the language argument a signature gains (§4.2) and the accessor changes named in 5.1. No file in `tests/fixtures/render/`, `system_text_sha*.txt`, `board_declarations.json`, `error_messages_fr.json`, the golden SSE transcripts or the French formatter tests is regenerated. Where a task moves French literals into a `by_language` table, the French row is the old literal verbatim and the existing goldens are the proof.

Until 7.8 no subject is offered in English (`SubjectInfo.languages == ("fr",)`): English is built and tested underneath (tests build English courses through the repository or by patching `offered()`), and switched on only when the whole path exists (R1.7).

## Phase 0 — A course has a language (backend)

**Goal:** `courses.language` exists, is set at creation, is immutable and reaches the lesson, the turn context and every course DTO. French behaviour is unchanged. **Done when** the endpoint and migration tests pass and `uv run pytest` is green untouched.

- [x] 0.1 `app/domain/language.py` (§3.2): `CourseLanguage`, `COURSE_LANGUAGES`, `DEFAULT_COURSE_LANGUAGE`, `is_course_language`, `require_language`, `by_language`, `InvalidLanguage` (code `invalid_language`, 422; keys in both catalogs; row in `tests/fixtures/error_messages_fr.json` via `make`). Tests `unit/test_language.py`: `by_language` raises on a missing and on an extra key; `require_language` accepts `fr`/`en`, refuses `de` and `""`; the error renders in both interface languages; catalog parity test passes.
- [x] 0.2 `domain/subject.py` (§3.2): `SubjectInfo.languages`, `offers`, `offered`, `offered_languages`; both launch subjects `("fr",)` for now. Tests: `offers("mathematics","fr")`, not `"en"`; `offered()` lists available subjects only.
- [x] 0.3 `db/models.py` `CourseRow.language` and migration `0007_course_language.py` (§3.1, style of `0006`, `batch_alter_table`, working `downgrade`). Tests `unit/test_migrations.py`: head matches the models; an existing course reads `fr` after upgrade from 0006; downgrade then upgrade.
- [x] 0.4 Records and repository (§3.2): `CourseRecord.language`, `CourseRepository.create(..., language="fr")` and its mapper, `LessonChapter.language` set in `services/chapters.py` from the owning course, `TurnContext.language` (default `fr`) set by `load_context`. Tests: create with `en` and read back through the course and the chapter loaders; `load_context` carries it; the default leaves every existing call site valid.
- [x] 0.5 Routes and DTOs (§3.3, §4.2): `CreateCourseRequest.language` (default `fr`, `require_language`), `offers` check, `course_created` log gains `language`; `language` on `CourseSummary`, `CourseDetail`, `ChapterView`, `ChapterContent`; `SubjectDTO.languages`. Tests `integration/test_courses_endpoint.py`: no language → `fr`; `en` refused while not offered (422, message in the `Accept-Language` language); with `offered()` patched, `en` is stored and every DTO returns it; `PATCH` with `language` is 422 and changes nothing; another student's course stays 404; `unit/test_route_guards.py` passes untouched.

**Verify:** `cd backend && uv run alembic upgrade head && uv run alembic downgrade 0006 && uv run alembic upgrade head`; `uv run pytest` green; `curl -s localhost:8000/api/subjects` (signed in) lists `"languages":["fr"]`; creating a course with `"language":"de"` answers 422.

**Verified** (2026-10-02): migration cycle 0007 up/down/up clean; 2355 backend tests (was 2333). `InvalidLanguage` has its row in `error_messages_fr.json` (an addition). Two existing assertions changed because `SubjectDTO` gained `languages` (`test_courses_endpoint`, `test_display_languages`). `tests/conftest.py` gained the `english_offered` fixture (scaffolding until 7.8).

## Phase 1 — The course language in the frontend

**Goal:** the page knows its course's language; `COURSE_LANG` is gone; the create form asks for the language. **Done when** the context, form, card and `lang` tests pass and the existing suite passes untouched.

- [x] 1.1 `lib/course-language.ts` → `.tsx` (§5.1): `CourseLanguage`, `CourseLanguageProvider`, `useCourseLanguage()` (default `fr` outside a provider). Types: `language` on `CourseSummary`, `ChapterView`, `ChapterContent`, `SubjectInfo.languages`; `createCourse(name, subject, language)`. Tests: the default, a provider value, a nested provider.
- [x] 1.2 Providers on the chapter, content, discussion and course routes and on each card of the courses list; replace every `lang={COURSE_LANG}` with the hook (about 20 sites, §5.1); delete `COURSE_LANG`. Tests: a chapter whose view says `en` renders its course text with `lang="en"`; French unchanged; a grep test asserts `COURSE_LANG` no longer exists.
- [x] 1.3 Create form and cards (§5.4): language select (autonym, offered per the chosen subject's `languages`, default the interface language when offered else `fr`, the immutability note), the badge on `course-card.tsx`, the course page header and the chapter bar; messages in `fr.json` and `en.json`. Tests: the select lists what the server lists, is hidden or single when only `fr` is offered, defaults per interface language, the body of `createCourse` carries the choice, the badge has its own `lang`.

**Verify:** `npm test && npm run typecheck && npm run lint`; with both servers running the create form shows the language (French only for now) with its note.

**Verified** (2026-10-02): 1242 frontend tests (was 1229 plus 13 new), `tsc` clean, lint 0 errors. `COURSE_LANG` is gone (a test greps for it); `lib/course-language.ts` became `.tsx`. Existing fixtures gained `language: "fr"` / `languages: ["fr"]` and the `createCourse` wire test gained `language` (the call now carries it). The language select is hidden while only one language is offered; the badge (`Matières · Français`) is always shown on the card and the course header.

## Phase 2 — Model-facing text by language (R5)

**Goal:** everything the code builds for the model is looked up by language; French rows are the old literals. **Done when** the French goldens pass untouched and the English goldens exist and are reviewed.

- [x] 2.1 `curriculum_render.py` (§4.1, §4.5, Appendix A): `RENDER_WORDS = by_language(...)`, `language` parameter (default `fr`) on `overview`, `brief`, `completion`, `state_message`, the discussion state and `moment`; section kind labels as `KIND_LABELS` (`KIND_LABEL_FR` kept as the fr row). Tests: the existing render goldens pass untouched; new English goldens `tests/fixtures/render/*_en.txt` (overview and state in both modes, brief of each kind, completion, review, finished chapter), generated once, read by a person, pinned; `moment()` in both languages, including the part of day boundaries.
- [x] 2.2 `services/path.py`, `section.py`, `pace.py`, `context.py` (`SAVE_FAILED` at the raise site), the registry's four parse errors: `WORDS = by_language(...)` read through `ctx.language`. Tests: each message pinned in both languages; the French strings equal what the code said before (existing substring tests untouched).
- [x] 2.3 `history.py` (§4.9): `CHARS_PER_TOKEN`, `estimate_tokens(…, language)`, `trim`, `to_provider_input` reads `ctx.language`. Tests: French estimates unchanged; English estimates differ by the ratio; trimming a long English history keeps more entries than the French ratio would.
- [x] 2.4 Table coverage test (§9.1): collect every `by_language(` in `app/` by import scan and assert each covers `COURSE_LANGUAGES`; an unlisted language added in a test monkeypatch fails at import of a fresh module.

**Verify:** `uv run pytest` green; read `tests/fixtures/render/overview_en.txt` and `state_*_en.txt` by eye.

**Verified** (2026-10-02): 2400 backend tests (was 2355); no French golden changed (`git status` shows only new `*_en.txt`). `KIND_LABELS` lives in `domain/curriculum.py`; the callers of `curriculum_render` in `prompt_service` and `voice_service` still use the French default until 5.5 / 6.2. `format_validation_errors` gained a `root` parameter so the registry's English refusal says `(root)`. English render goldens were generated from `tests/fixtures/curricula/valid_en.yaml` and read; they await the user's review with the rest of the English copy.

## Phase 3 — Tool rules by language (R6)

**Goal:** the answer-withholding and no-invention rules work in English as in French. **Done when** the per-language rule tests pass and the French rule tests pass untouched.

- [x] 3.1 `plots.py` (§4.6): `PACK_WORDS[language]` (French moved verbatim; English table), `_COMMA[language]`; the rules read `ctx.language`. Tests: per entry one accepted and one refused sentence per language (« sine » counts, « tangent to the curve » does not, « tangent of an angle » does); `(1,4)` is two values in English, `(0,5)` one decimal in French; the French tests untouched.
- [x] 3.2 `flowcharts.py`: `_HOLE_HEAD/_HOLE_GAP/_HOLE_WORDS[language]`, `_plain_words` unchanged. Tests: a placeholder box (« to complete », « fill in », « TBD », « box 3 ») is refused in English; an ordinary English step is not; French unchanged.
- [x] 3.3 `figures.py`: `_INTERVAL`, `_COORDS`, `_DEGREES`, `_LENGTH` by language, `_number(text, language)`. Tests: `(2, 3)`, `[2, 5)`, `(−∞, 2]`, `(2, −1.5)` recognised in English and `1,500 m` is 1500; French `]a ; b[`, `(2 ; 3)` and `1,5` unchanged; a frame `(O, \vec{i}, \vec{j})` passes in English.
- [x] 3.4 Every rule call that needs the language receives it from `ctx` (R6.6). Test: a rule called without a language fails type-checking (`uv run pyright` or the repo's checker if present) and the card tests of an English `ctx` pass end to end for each of the four drawing blocks.

**Verify:** `uv run pytest -k "plots or flowcharts or figures"` green; the French cases in those files are unchanged in the diff.

**Verified** (2026-10-02): 2547 backend tests (was 2400); the French rule tests pass untouched (`git diff` shows no edit to `test_plot_rules.py`, `test_flowchart_rules.py`, `test_figure_rules.py`). New: `test_plot_rules_en.py`, `test_flowchart_rules_en.py`, `test_figure_rules_en.py`, `test_board_rules_by_language.py`.

## Phase 4 — The board draws in the course's notation (R7)

**Goal:** an English course shows `12.5%`, `(a, b)` and « Relative frequency »; the learner sentences follow the course. **Done when** the formatter, sentence and sweep tests pass and the French tests pass untouched.

- [x] 4.1 `charts/format.ts` (§5.2): `Notation`, `NOTATION`, `notationFor`, `useNotation`; the French row is the existing exports by reference. English: `en-GB` numbers with `useGrouping: "min2"`, `12.5%`, `(a, b)`/`[a, b)`/`(a, b]`/`[a, b]`, infinite ends round, `(2, −1.5)`, class labels, `Frequency / Relative frequency / Percentage`, `Minimum / Q1 / Median / Q3 / Maximum`. Tests: tables per language (the French cases untouched).
- [x] 4.2 Thread the notation through the 52 call sites (§5.2): `ChartView`, `FigureView`, `PlotView`, `FlowchartView` call `useNotation()` once; `describe.ts` and `layout.ts` helpers take `notation` with the French default. Tests: an English chart, figure and plot render English numbers and words and their sr-only description keeps interface sentences with English numbers inside (R7.3); the existing French component tests pass untouched.
- [x] 4.3 Shared notation table (§4.6): `backend/tests/fixtures/notation_cases.json` ↔ `frontend/src/components/celestin/charts/__tests__/notation_cases.json` (prettier-formatted, byte equality asserted backend side). Tests: frontend formatter output equals each `text`; backend `_INTERVAL`/`_COORDS`/`_number` read each text back, per language.
- [x] 4.4 `lib/tutor/prompts.ts` (§5.3): `LEARNER_SENTENCES[language]`, `learnerSentences(language)`; callers (`lesson.tsx`, `chapter-map.tsx`, `discussion-panel.tsx`, `use-voice-session.ts`) read the hook. Tests: French constants unchanged; English sentences pinned; the module still never imports `@/paraglide/messages`.
- [x] 4.5 Source editor hint (§5.4): `lib/tutor/transcription-markers.ts`, `content_source_hint` takes the markers. Tests: French text byte-identical; English names the English markers.
- [x] 4.6 Sweep (§5.5): an English course under a French interface and a French course under an English interface added to `english-sweep` scenarios; course text carries its `lang`. Tests: both pass; a French word in English course text fails the sweep.

**Verify:** `npm test && npm run typecheck && npm run lint`; Storybook-free check: open the test harness page for a chart with an English course in `npm run dev` (the course is created through `scripts/seed.py --language en` once 8.3 lands; until then the unit tests are the verification).

**Verified** (2026-10-02): 1311 frontend tests (was 1242), `tsc` clean, lint 0 errors; 2586 backend tests. The pure helpers take `notation` as a trailing optional parameter (default `FRENCH`), so no French test changed; the four views and the chart components call `useNotation()` once. Backend and frontend read the same `notation_cases.json` (byte-equality asserted backend side).

## Phase 5 — The prompt library and the English prompt set (R3)

**Goal:** `PromptLibrary` is language-aware; the English files exist, are pinned and read by a person. **Done when** the per-language prompt tests pass, French hashes are unchanged and `/api/health` lists the English files when English is offered.

- [x] 5.1 `services/prompts.py` (§4.3): `file_name(base, language)`; accessors `tutor/subject/mode/mode_opening/template/authoring_pack/authoring_curriculum/transcribe/verify(language)`; caches keyed by (name, language); `required()`, `_broken()`, `check()`, `unavailable()` over `offered()`; `PackTemplate.language`; `other_templates(subject, language)`. Callers (`TutorService`, `VoiceService`, `AuthoringAgent`, `routes/courses.py`, scripts, `StubPrompts`) pass the language beside the subject. Tests `unit/test_prompt_library.py` parametrised by language: reads, cache per language, a missing file named in the startup error, `/api/health`; French assertions unchanged.
- [x] 5.2 Write `tutor.en.md`, `modes/{parcours,discussion}.en.md`, `modes/{parcours,discussion}.opening.en.md` (§6) from their French twins. Tests `test_prompt_files` parametrised: markers once and in order, same `##` sections as the French file (parity), voice blocks present, tool names identical, the cited button labels equal the English interface labels.
- [x] 5.3 Write `subjects/{mathematics,physics}.en.md` and `templates/{mathematics,physics}.pack.en.md` (§4.8, §6): English notation sections, spoken forms, headings and sentinels. Tests: templates parse, `exercises_section` and last-section positions equal the French, the cited `Points to check` heading equals the template's last heading, the subject prompts are subject-neutral where the French ones are.
- [x] 5.4 Write `authoring/{pack,curriculum}.en.md` and `transcription/{transcribe,verify}.en.md` (§6, R4.1–4.2): never translates; markers named per §4.8. Tests: the markers each prompt names are exactly the language's `MARKERS` (after 7.1) — until then, parity of sections and placeholders.
- [x] 5.5 `prompt_service.build(…, language)` and `render_system_text` callers; pins `system_text_sha_en.txt` and `system_text_sha_en_discussion.txt` created once, read by a person, then pinned. Tests: French hashes unchanged; English hashes pinned; nothing per-turn precedes the cache breakpoint in English.
- [ ] 5.6 **Human review gate.** The English prompt files are read by the user before 6 starts; wording changes are made here and the pins regenerated.

**Verify:** `uv run pytest -k prompt` green; `uv run python -c "from app.services.prompts import PromptLibrary; ..."` startup check names no file (done in the test); read the English tutor prompt next to the French one.

**Verified** (2026-10-02): 2688 backend tests. The English files were written by sub-agents from the French twins and checked here: `test_prompt_files_languages.py` pins the same skeleton (headings, markers, tool and block names), no French accent or guillemet, the cited `Points to check` heading, the markers, the learner sentences; `test_prompt_library_languages.py` pins the library; `test_prompt_service_en.py` pins `system_text_sha_en*.txt`. **5.6 (a person reads the English prompts) is open and is the user's.** The pins and the English render goldens were generated by me and are not yet reviewed by a person.

## Phase 6 — The tutor and the voice in the course's language (R2, R8)

**Goal:** a turn and a voice session for an English chapter use the English prompts, declarations and state text, with the wall intact. **Done when** the wall, tutor and voice tests pass and the French transcripts and configs are byte-identical.

- [x] 6.1 `TutorService.build_input` and `run_turn` pass `chapter.language` / `ctx.language`; `registry.declarations(mode, language)` and `realtime_declarations(mode, language)` over `_DECLARATIONS[(mode, language)]` with `TOOL_TEXT = by_language(fr={}, en={})` and `_localise` (§4.7). Tests: `declarations(mode,"fr")` equals `board_declarations.json`; `"en"` equals it while the overlay is empty; a temporary overlay applies; a stale pointer raises at build.
- [x] 6.2 `VoiceService` (§4.4): instructions, declarations, `"transcription": {…, "language": chapter.language}`, state text from `ctx.language`. Tests `test_voice_service`: French config byte-identical (`"fr"`); English config from the English files with `"en"`; the path-move state text in English.
- [x] 6.3 The wall (§4.10): `test_model_input_wall.py` reworded: the import check stays, the tutor path may not read `locale`; two accounts with different `locale` on the same course give identical input; a French and an English course give different inputs each equal to its pinned rendering. Replace `test_the_tool_declarations_take_no_language`. Tests: those themselves, plus an English golden SSE transcript with the scripted fake provider.
- [x] 6.4 `turn_complete` and `voice_session_created` logs gain `language` (§11). Test: the log extras.

**Verify:** `uv run pytest` green; with a patched `offered()` and a seeded English chapter (8.3), one English turn through `curl` reads English and the cache prefix is stable on the second turn.

**Verified** (2026-10-02): `test_course_language_turn.py` (declarations, voice, text turn, logs) and the reworded `test_model_input_wall.py` (an English account and a French account on an English course hand the provider identical input; a French and an English course hand different input, each equal to its pinned rendering).

## Phase 7 — Authoring in the course's language (R4)

**Goal:** an English document becomes an English pack and curriculum, offline-tested with fakes; then English is switched on. **Done when** the English authoring path passes end to end and the create form offers English.

- [x] 7.1 `domain/transcription.py` (§4.8): `MARKERS = by_language(Markers(...))`, `language` on `count_markers`, `handwritten_numbers`, `apply_uncertain`, `validate_batch`; `Words` table for the issue texts (French verbatim). Tests: French cases untouched; English markers counted and rewritten; an English marker in a French source is not counted.
- [x] 7.2 `domain/pack.py`: `_NUMBERING[language]`, `chapter_title(heading, language="fr")`, `parse_template(text, path, language)`; `index_pack(…, alternatives)` and the `pack.wrong_language` issue with both catalog keys. Tests: English titles (`Chapter 3:`, `Lesson 2 –`, `Unit 4)`, Roman numerals); a French pack against the English template and the reverse fail with `pack.wrong_language` first; French unchanged.
- [x] 7.3 Curriculum language (§4.8): `Curriculum` reads the language from the validation context; `curriculum_from_json`, `check_curriculum`, `parse_curriculum` take it; callers `services/chapters.py`, `domain/content.validate_curriculum`, `scripts/chapter_files.py` pass the chapter's. Tests: English section titles cleaned; French untouched.
- [x] 7.4 `domain/messages/issues.py` `issue_text(issue, language)` (§4.8): French = `issue.message` exactly; English from the catalog else `message`. Tests: for every issue code, fr equals `message`; the editor still renders by interface locale; the repair message bytes for French unchanged.
- [x] 7.5 `services/authoring/words.py` `AGENT_WORDS[language]`, `agent.py` literals replaced, `_repair_message(what, issues, language)`, `AuthoringAgent.run(…, language)`, `AuthoringRunner._execute` reads `course.language`. Tests with `fake_completion.py`: the English wrapper, page labels and repair message; French pinned as before.
- [x] 7.6 Content-save validation in `routes/courses.py` passes the course's language. Tests: an English pack saved to an English course validates; a French pack to it is refused with the mismatch issue shown in the interface language.
- [x] 7.7 English fixtures (§9.2, R9.1): material, valid pack, curriculum and chapter directory per subject under `tests/fixtures/{material,packs,curricula,chapters}`; `StubPrompts` takes a language. Tests: the English path from material through transcription, pack and curriculum to a valid chapter with scripted fakes, for each subject.
- [x] 7.8 Switch English on: `SubjectInfo.languages == ("fr","en")` for mathematics and physics. Tests: startup check passes with English files; the offered list and `/api/subjects` include `en`; the create form offers it; remove the `offered()` patches from earlier tests where they were only scaffolding.

**Verify:** `uv run pytest` and `npm test` green; in the browser create an English mathematics course (the form shows « English »), the course card and chapter bar carry the badge.

**Verified** (2026-10-02): 2835 backend tests; both launch subjects are offered in English (`SubjectInfo.languages == ("fr", "en")`) and the startup check requires, and finds, the whole English set. The English fixtures (material, packs, five chapter directories, an English curriculum) were written by a sub-agent from the French twins' topics and validated with `load_chapter_dir(..., language="en")`. New tests: `test_authoring_language.py`, `test_authoring_agent_en.py`, `test_transcription_en.py`, `integration/test_english_course.py`, `test_language_is_passed.py` (an AST walk that fails on a call that does not name the language).

## Phase 8 — Scripts, probes and review (R9)

**Goal:** English is held to the standard French is, and the evidence is read. **Done when** the scripts run with `--language en` and the findings are recorded.

- [x] 8.1 `scripts/probe.py --language`: per-language flags (French unchanged; English flags a decimal comma, a `;` interval and a French leakage list), the report per language with the answer-leak rate, out-of-pack count and leakage count. Tests: the flag functions per language, the report shape.
- [x] 8.2 `smoke`, `voice_smoke`, `voice_probe`, `authoring_eval`, `document_eval` take `--language` (R4.8, R8.4, R9.4). Tests: argument parsing and the language reaching the service in each.
- [x] 8.3 `scripts/seed.py --language` and an English seed chapter from the 7.7 fixtures. Test: the seed creates an English course and chapter for a local student.
- [ ] 8.4 **Runs (the user approves the cost first).** `probe --language en` (guardrail and the four drawing probes), `smoke --language en` (CACHE OK), `authoring_eval` and `document_eval` on an English document per subject, `voice_probe --language en`. Read the transcripts; record answer leaks, out-of-pack content and French leakage under Deviations / Findings.
- [ ] 8.5 Decide the declaration overlay (§4.7) on the evidence: if French leaks from the descriptions, fill `TOOL_TEXT["en"]`, add the English declarations snapshot, re-run the leakage probe; else record that it stays empty and why.

**Verified offline** (2026-10-02): 3008 backend tests. `probe.py --language en` (guardrail, discussion, charts, flowcharts, figures, plots) and `--dry-run` were written by a sub-agent and checked offline only (`test_probe_flags_en.py`, a `main()` run with a scripted reply, `--dry-run` for both languages); `smoke`, `voice_smoke`, `voice_probe`, `authoring_eval`, `document_eval` and `seed` take `--language`. **8.4 (the paid runs and reading their transcripts) and 8.5 (the declaration overlay decision) are open and are the user's: nothing was sent to the model.**

## Phase 9 — Documentation and close

- [x] 9.1 Documentation (§13): `documentation/i18n.md` (course language against interface language, tables, file layout, the rewritten wall), `authoring.md`, `chapters.md`, `tutor-turn-pipeline.md`, `accounts-and-courses.md`, `voice.md`; `documentation/index.md` if a file is added; `backend/CLAUDE.md`, `frontend/CLAUDE.md`, root `CLAUDE.md` (the invariants now say the course language, not "French for now"); `specs/product.md` §1, §3.1, §6.7, §12.4; `specs/index.md`.
- [x] 9.2 Full checks: backend `uv run pytest`, frontend `npm test && npm run typecheck && npm run lint && npm run build`; the French golden files show no diff in `git status`.

**Verify (manual checklist):** (1) create a French and an English course; the badges differ. (2) English chapter from an English PDF: the pack and the path are English, no translation. (3) An English lesson with a chart, a figure and a plot: English words and notation, no French. (4) The same under a French interface and under an English interface: identical tutor speech. (5) A voice session in English: English instructions, the probe reads `x squared`. (6) A French course behaves as before.

**Verified** (2026-10-02): backend 3008 passed / 7 skipped; frontend 1311 passed, `tsc` clean, lint 0 errors, `npm run build` passes, prettier clean; no French golden changed. The manual checklist above is the user's. `simplify` ran with four reviewers: applied the shared-language script choices, `create_course(language=…)`, the `issue_text` and `pack.wrong_language` reuse of the catalog, declarations shared between languages while an overlay is empty, the unused `Notation.language`, and `_language_of`; left (with the design's reasons) the French defaults and the AST test, the overlay, the `_placeholder` special case, and the probe script's internals.

## Deviations

- **3.1** `PACK_WORDS` stays the French table (name → pattern) because `test_plot_rules.py`, `test_probe_flags.py` and `scripts/probe.py` read it as such and must not change; the per-language table is the new `PACK_WORDS_BY_LANGUAGE`, `_COMMA` likewise `COMMA`, and `_GROUPS` `GROUPS`. Same for `DEGREES`, `LENGTH`, `INTERVAL`, `COORDS` (figures) and `HOLE_WORDS` (flowcharts).
- **3.1** English `COMMA` is a plain `,` (the verify review found that exempting a comma before three digits let `(3,100)` through the open-exercise give-away check): a thousands comma in a label such as `(1,500 m)` is refused too, which costs the model one rewrite. English `GROUPS` also reads the half-open `(2, 3]` and `[2, 5)`.
- **3.2** English hole phrases put the adjective first (`Missing step`, `Hidden node`) and leave out « blank »: `Blank box ?` is a question, as « Case vide ? » is in French. The placeholder rule is the only graph rule given the language; `flowchart_refusal` special-cases it.
- **3.3** English interval/coordinate patterns accept `,` or `;` as separator and any mix of `(`/`[`/`]` around: a French `]2 ; 5[` written by hand in an English course is still refused.
- **4.1** `Notation` also carries `separator` (the member separator of a list, `" ; "` / `", "`), and `bound` keeps the French `−∞`/`+∞` argument: English writes the right infinity as `∞`, so `(2, ∞)`, `(−∞, 2]`.
- **4.3** The shared table has no hand-grouped English pair (`(12,500, 0.25)`): the backend coordinates pattern does not see it, as it does not see `(12\u202f500 ; 0,25)` with its grouping removed; rare enough to leave.
- **4.4** The old French constants (`REVIEW_MESSAGE`, …) stay exported (the French row, and the existing test); components read `useLearnerSentences()`.
- **4.6** No change to `english-sweep.ts` itself: it already exempts only `lang="fr"`, so a French word inside an English course's `lang="en"` region fails; the new test pins that and the `lang` of an English course under each interface.
- **7.5** `AuthoringAgent.run` takes `language` as a keyword (default `fr`) and the runner reads it from `course.language`; `_repair_message(what, issues, language)` takes the already-worded `what` (`AGENT_WORDS[language].the_document` / `the_path`). The wrapper tags `<materiel>`, `<chapitre>`, `<lignes>`, `<couche_texte>` stay as they are in both languages (the English prompts name them).
- **7.4** `pack.wrong_language` carries language *codes* in `found_language` / `expected_language`; `render_issue` and `issue_text` name them in the reader's language (`language.fr`, `language.en` in both catalogs).
- **7.8** The `english_offered` test fixture of phases 0–7 is replaced by `french_only` (the opposite scaffolding, for tests of the French-only state).
- **9.2** The Deviations of phases 3–4 and 7 above are the whole list; the design is otherwise followed. Not done and left to the user: 5.6, 8.4, 8.5 and the manual checklist.
- **Verify fixes** (2026-10-02, after `/sdd:verify`): English `chapter_title` no longer eats `Chi-squared`, `X-ray`, `V-shaped` (a keyword needs a space or its own dot; a bare number needs a digit or a Roman numeral with a closing mark); the plot's screen-reader words « indice »/« exposant » are interface messages (`describe_plot_word_*`), and the English-sweep word list knows them; `pack.wrong_language` builds its French message without the catalog; the create form says what the language is for; the chapter bar shows the language; the AST guard also covers the history, rule and `issue_text` functions and the scripts. Left as they are, deliberately: the bare head words in the English hole list (the French list refuses `Réponse`, `Texte`, `Bloc` the same way), the `_placeholder` special case, the `_repair_message` word mapping, and `Markers.empty_page`.

