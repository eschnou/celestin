# 017 — Tasks

Phases are testable increments in dependency order. Each ends with a check the user can run. Requirement ids (`R1`…) refer to `requirements.md`, section numbers (`§`) to `design.md`. Tick tasks as they land; record design deviations in the Deviations section at the end.

Branch `feature/017-dutch-flemish`, started from a clean base **after the user has committed spec 016** (the working tree held its uncommitted work when this plan was written). Commit nothing; the user commits.

Checks for every phase that touches a side: backend `cd backend && uv run pytest`; frontend `cd frontend && npm run typecheck && npm run lint && npm test`; `npm run i18n:check` when a catalog changes. Offline only: tests drive scripted fakes; no phase before 8 spends money.

Load-bearing constraints across the epic:

- **French and English do not move.** No file in `tests/fixtures/render/*` (fr and `_en`), `system_text_sha*.txt` (fr, `_en`), `board_declarations.json`, `error_messages_fr.json`, `status_messages_fr.json`, `markers_fr.json`, the golden SSE transcripts, or an existing `*.fr.md`/`*.en.md` prompt is regenerated or edited. Existing tests change only by (a) the language argument a signature gains, (b) being parametrised over `COURSE_LANGUAGES`/`LOCALES`, (c) a pinned language list, in phase 7 only (§8.1).
- **`nl` is not offered until phase 7** (`SubjectInfo.languages` stays `("fr","en")`; `/api/subjects` and the create form are unchanged until then). The `Locale` (interface) side is user-visible from phase 2, which is intended.
- Dutch copy, prompts and goldens are written by us. Nothing is pinned until a person has read it (tasks marked **READ**). The spec status carries « Dutch copy and prompts awaiting review by a Flemish speaker » until the user says otherwise.
- Notation: Belgian-French, by reference (§1 decision 1); every `nl` notation row is the French one under a Dutch name.

## Phase 0 — Structural fixes before the third language (§4.3)

**Goal:** no place in the code needs more than a table row to learn a language. French and English behave exactly as before. **Done when** the new guard test passes and the whole suite passes unedited except the tests this phase adds.

- [ ] 0.1 `services/tools/figures.py`: `NUMBER = by_language(fr=_decimal_comma, en=_thousands_comma)` and `_number(text, language)` calls `NUMBER[language](text)` (no `== "en"`). Tests (`test_figure_rules`, `test_figure_rules_en`): the existing number cases pass untouched; `NUMBER` covers `COURSE_LANGUAGES`.
- [ ] 0.2 `domain/pack.py`: `_LANGUAGE_NAMES_FR = by_language(fr="français", en="anglais")`. Test: the wrong-language reason for fr↔en is byte-identical (`test_pack`, `test_authoring_language`).
- [ ] 0.3 `domain/messages/issues.py`: `WHERE_WORDS: dict[Locale, …]` (fr empty; en = the current `_EN_WORDS`/`_EN_PATTERNS`, moved), `render_where` reads it. Test: `render_where` fr/en unchanged (`test_issue_messages`); `set(WHERE_WORDS) == set(LOCALES)`.
- [ ] 0.4 `services/work_reading._PHOTO_LABEL` → `by_language(fr=…, en=…)`. Test: `test_work_endpoint`/`test_work_reading_streamed` unchanged and passing.
- [ ] 0.5 `scripts/chapter_files.default_chapter_dir` → `DEFAULT_CHAPTER_DIRS = by_language(fr=…, en=…)`. Test: `test_scripts_language` unchanged.
- [ ] 0.6 `scripts/probe.py`: every `by_language(…)` and every `language == "en"` / `== "fr"` branch (`guardrails`, `_is_outcome`, `bad_notation`/`notation_flags`, `leakage_flags`, the report title, the `question = … if language == "fr"` rule) becomes a lookup in tables built by a local `probe_tables(fr=…, en=…, nl=None)` whose `[language]` raises `SystemExit("no probe set for <language> yet")` when a language has no row. Tests: `test_probe_flags`, `test_probe_flags_en`, `test_scripts_language` pass unchanged; a new test: asking for a language without a row exits with that message.
- [ ] 0.7 Guard `tests/unit/test_no_language_branches.py`: AST-scans `app/` and `scripts/` for comparisons of a name containing `language` or `locale` with a string literal `"fr"|"en"|"nl"`; allowlist: `domain/messages/__init__.plural_category` (French counts 0 and 1 as singular), `DEFAULT_*` comparisons, `app/domain/locale.py`. Fails with file:line otherwise.

**Verify:** `cd backend && uv run pytest`; `uv run python -m scripts.probe --dry-run` and `--language en --dry-run` still load every chapter and set.

## Phase 1 — The interface language, backend (R1.1, R1.2, R1.6, R1.7)

**Goal:** a user can have `locale = "nl"`; every server message for the student exists in Dutch. **Done when** the catalog parity, the locale and the error tests pass in three languages.

- [ ] 1.1 `domain/locale.py`: `Locale = Literal["fr","en","nl"]`. `domain/messages/__init__.py`: `CATALOGS["nl"]`. Tests `test_locale`: `LOCALES == ("fr","en","nl")`; `parse_accept_language` for `nl`, `nl-BE`, `nl-NL`, `nl-BE;q=0.8,fr;q=0.9` → fr, `fr,nl;q=0.8` → fr, `nl;q=0` → fr, `de,nl;q=0.5` → nl (inline parametrised cases; the shared JSON follows in 2.7).
- [ ] 1.2 `domain/messages/nl.py`: the 124 keys of `fr.py`, same `{fields}`, plural keys `*.one`/`*.other`; add `language.nl` to `fr.py` (`néerlandais`), `en.py` (`Dutch`), `nl.py` (`Nederlands`) and `language.fr`/`language.en` to `nl.py` (`Frans`, `Engels`). Register-correct Dutch: `je`, calm, no *tussentaal*. Tests `test_messages`: same keys and fields in all three (existing parity test extended), `set(CATALOGS) == set(LOCALES)`, plural forms present. **READ** by the user (Dutch copy).
- [ ] 1.3 `render_where` row for `nl` (App. A: `titel`, `hoofdstuk`, `traject`; `oefening \1`, `sectie nr. \1`). Tests: each pattern; `render_issue` for `nl` on a coded issue and on an uncoded one (falls back to the French message).
- [ ] 1.4 Error and status rendering in `nl`: `TutorError.message("nl")`, `event_of(outcome, "nl")`, `marker_for(…,"nl")`, `authoring_message(chapter, "nl")`, subject labels, `« Chapitre N — »` (`chapter.title`). Tests: parametrise `test_error_languages`, `test_display_messages`, `test_issue_messages` over `LOCALES` (new asserts only; the French assertions untouched).
- [ ] 1.5 Auth: `PATCH /api/auth/me` accepts `nl` and answers `422` for `de`; registering with `Accept-Language: nl-BE` stores `nl`; `/api/auth/me` returns it. Tests `integration/test_auth_endpoint`, `test_error_languages`: a wrong password under `Accept-Language: nl` answers in Dutch.

**Verify:** `uv run pytest`; with the backend running, `curl -s -X POST localhost:8000/api/auth/login -H 'Content-Type: application/json' -H 'Accept-Language: nl-BE' -d '{"email":"x@y.be","password":"nope"}'` answers a Dutch message.

## Phase 2 — The interface language, frontend (R1.3 to R1.5, R1.8, R1.9, R7.6 for the interface)

**Goal:** the whole application can be used in Dutch; `Nederlands` is in the settings list; no screen mixes languages. **Done when** `i18n:check`, typecheck, lint, the tests and the generalised sweeps pass.

- [ ] 2.1 `lib/locale.ts` (`LOCALES`, `AUTONYM.nl = "Nederlands"`), `lib/i18n-format.ts` (`INTL_TAG.nl = "nl-BE"`), `lib/error-page.ts` (`TEXT.nl`, §5.1), `project.inlang/settings.json` (`locales`). Tests: `locale`, `i18n-format` (a Dutch number/size/date/cost), `error-page` (Dutch page for `Accept-Language: nl`), `settings` list shows three autonyms and marks the current one.
- [ ] 2.2 `messages/nl.json`: all 771 keys of `fr.json`, same `{variables}`, plural selector form with `one`/`other`; areas in order: `auth_`, `nav_`, `course_`, `chapter_`, `content_`, `lesson_`, `voice_`, `board_`, `describe_*`, `settings_`, `error_`, `admin_`/`usage_`, the rest. The product name stays `Célestin`. **READ** (Dutch copy). Test: `npm run i18n:check` (keys, variables).
- [ ] 2.3 `Accept-Language` shared table: add the `nl` rows (`nl`, `nl-BE`, `nl-NL`, `nl-BE;q=0.8,fr;q=0.9`, `fr,nl;q=0.8`, `nl;q=0`, `de,nl;q=0.5`) to **both** copies, prettier-formatted. Tests: frontend `accept_language_cases` test, backend `test_locale` (including the byte-equality test).
- [ ] 2.4 Generalise the sweep: `src/test/english-sweep.ts` → `foreignTextOutside(root, locale)` with a detector per interface language (§5.5); `en` is the current code, unchanged; `nl` is whole-word French and English lists, no accent test. The sweeps (`english-sweep`, `lesson-sweep`, `discussion-sweep`) run for `["en","nl"]`. Tests: the detector finds a French word and an English word in a Dutch screen and ignores them inside a `lang="fr"`/`lang="en"` region; every screen the sweeps render passes in Dutch.
- [ ] 2.5 `:lang(nl)` hyphenation rule in the global stylesheet. Test: a render under `nl` has `<html lang="nl">` (`i18n` tests); the 400 px check is manual (below).
- [ ] 2.6 Existing tests that read the interface list move to `LOCALES` (`check-messages.test.ts` fixture keeps its own two-locale settings file).

**Verify:** `cd frontend && npm run i18n:check && npm run typecheck && npm run lint && npm test`. Run both servers; in « Paramètres » choose « Nederlands »: the page, the menu and the document title change at once; open a course, the lesson, a discussion, the settings, `/admin` as admin: no French or English chrome; the course text is still French or English (marked `lang`); a browser set to `nl-BE` on a private window shows `/login` in Dutch; at 400 px wide nothing overflows.

## Phase 3 — The course language, backend tables and rules (R2.1, R4.1, R4.3 to R4.5, R5, R6)

**Goal:** everything the code builds for the model, and every tool rule, knows `nl`; no Dutch course is offered yet. The `CourseLanguage` flip (3.1) and every row (3.2 to 3.6) are one atomic step: the suite is run at 3.7, not between. **Done when** each table's Dutch test passes and the French/English rule and render tests pass untouched.

- [ ] 3.1 `domain/language.py`: `CourseLanguage = Literal["fr","en","nl"]`; `tests/conftest.py` gains `dutch_offered` (patches `SUBJECTS` so the four subjects list `("fr","en","nl")` for a test; the real list is flipped in 7.1). Tests `test_language`: `COURSE_LANGUAGES == ("fr","en","nl")`, `require_language("nl")` passes, `"de"` and `""` raise `InvalidLanguage`; the offered-list pins keep `("fr","en")` through the real `SUBJECTS`.
- [ ] 3.2 Authoring tables: `MARKERS["nl"]`, `_NUMBERING_BY_LANGUAGE["nl"]` (`_KEYWORD_NL`, § 4.2), `KIND_LABELS["nl"]`, `CHARS_PER_TOKEN["nl"] = 3.4`, `_LANGUAGE_NAMES_FR["nl"] = "néerlandais"`, `AGENT_WORDS["nl"]` (glossary, App. A), `issue_text(·, "nl")` reads `nl.py`. Tests: `test_transcription_nl` (count, handwritten numbers, `apply_uncertain`, `validate_batch` incl. the four batch sentences), `chapter_title` (`Hoofdstuk 3:`, `Les 2 –`, `Thema 4)`, `Module IV.`, not `X-ray`-like false positives), `test_pack` (`pack.wrong_language` for every pair among fr/en/nl), `issue_text` fr == `message`, `history` estimates (nl differs from fr by the ratio; trimming keeps more than the French ratio would).
- [ ] 3.3 Model-facing words: `curriculum_render.WORDS["nl"]`, `path.WORDS["nl"]`, `pace._OUTPUT`, `section._UNKNOWN`, `context.SAVE_FAILED`, `registry._WORDS` (App. A), `TOOL_TEXT["nl"] = {}`. Tests: `test_curriculum_render_nl` (every function renders; `moment()` day/month/part words and boundaries; **goldens `tests/fixtures/render/*_nl.txt` are generated once here, READ by the user, then pinned**), `test_model_text_by_language` and `test_path` parametrised over `COURSE_LANGUAGES` (every message pinned for nl), `declarations(mode,"nl")` equals the French snapshot, an overlay applies and a stale pointer raises (existing test, third language).
- [ ] 3.4 Rules: `plots.PACK_WORDS_BY_LANGUAGE["nl"]`, `plots.GROUPS["nl"]`, `plots.COMMA["nl"]`, `figures.INTERVAL/COORDS/DEGREES/LENGTH/NUMBER["nl"]` (the `*_NL` aliases and the two comma-tolerant patterns of §4.6), `flowcharts.HOLE_WORDS["nl"]` (App. A). Tests `test_board_rules_nl`: one accepted and one refused sentence per `PACK_WORDS` entry (`tangens` counts, `raaklijn` does not; `exponentiële functie` counts, `exponentiële groei` does not); hole phrases (`in te vullen`, `ontbrekende stap`, `vak 3`, `tbd` refused; an ordinary step accepted); intervals and pairs (`]2 ; 3[`, `]2, 3[`, `(2 ; −1,5)`, `[0 ; 5]` recognised; a frame `(O, \vec{i}, \vec{j})` passes); `1,5 m` reads 1.5; the French and English rule tests untouched.
- [ ] 3.5 Shared notation table: add `nl` rows to `tests/fixtures/notation_cases.json` and the frontend copy (identical bytes, prettier), plus backend-only `recognised` rows for the hand-written comma forms. Test `test_notation_cases` parametrised over `COURSE_LANGUAGES`: each `interval`/`pair` text matched by `INTERVAL["nl"]`/`COORDS["nl"]`, each `number` read back by `NUMBER["nl"]`; the byte-equality test stays green (the frontend formatter test follows in 6.2).
- [ ] 3.6 `scripts/` rows that do not depend on fixtures: `voice_probe` (spoken forms and pattern for `nl`: « x kwadraat », « twee komma vijf »; the decimal-point/`^`/`_` pattern as French), `authoring_eval` stays for 8.x. Tests: `test_scripts_language`.
- [ ] 3.7 Run the whole suite. Fix any `by_language` table the scan reports (`test_by_language_tables` must list the same modules plus none missing), `test_language_is_passed` unchanged and passing.

**Verify:** `cd backend && uv run pytest` (Dutch tests + untouched French/English); `uv run python -c "from app.services import curriculum_render as r; print(r.moment(__import__('datetime').datetime(2026,10,8,10,5), 'nl'))"` prints `donderdag 8 oktober, 10:05 (voormiddag)`.

## Phase 4 — Authoring in Dutch: prompts, templates, fixtures (R3, R4)

**Goal:** a Dutch document becomes a valid Dutch pack and path with the scripted fakes; the authoring, transcription and template files exist and pass the structure tests. **Done when** the Dutch authoring path test and the prompt-file tests pass.

- [ ] 4.1 `prompts/templates/{mathematics,sciences,languages,general}.pack.nl.md`: same front matter (`exercises_section: 6`), seven headings in the same positions (App. A titles), the sentinels `Geen.`, `Niets in de cursus.`, `niet verbeterd in de cursus`. Tests (`test_prompt_files_languages` extended to `nl`): every French file has a Dutch twin and the converse for these files; heading numbers and `exercises_section` equal the French; `###` count equal.
- [ ] 4.2 `prompts/authoring/{pack,curriculum}.nl.md` and `prompts/transcription/{transcribe,verify,work}.nl.md`, from the English twins: same rules in the same order, the Dutch marks (`[handgeschreven]`, `[onzeker: a | b]`, `[onleesbaar]`, `[lege pagina]`, `[figuur: …]`, `[doorgestreept: …]`), « vertaal nooit », `<materiel>` is data. Tests: the transcription prompt demands page markers and doubt, never translates, the pack prompt reads a transcription, the work prompt keeps the transcription conventions (the existing per-language tests, third language); a Dutch file carries no French or English prose (two stop-word lists; tool names, `Célestin` and the tag names excepted). **READ**.
- [ ] 4.3 Fixtures: `packs/{maths_valid_nl,sciences_valid_nl}.md` (follow the Dutch templates), `curricula/valid_nl.yaml`, `material/maths_kwadratische_nl.txt`, `material/injection_nl.txt`. Tests: `index_pack` accepts each pack with the Dutch template and refuses it with the French and English ones (`pack.wrong_language`); `valid_nl.yaml` validates against the Dutch maths pack.
- [ ] 4.4 Authoring path with fakes (`test_authoring_agent_nl`, as `_en`): material → transcription (Dutch markers counted) → pack → curriculum, with a pack repair (a renamed Dutch heading) and a curriculum repair (a dangling reference); the repair message is in Dutch (`AGENT_WORDS["nl"]`, `issue_text`); the injection material is treated as data. `AuthoringRunner` runs a Dutch course through `dutch_offered` and stores a valid chapter.
- [ ] 4.5 `PromptLibrary` for `nl` (accessors with the language already exist): tests `test_prompt_library_languages` over three languages; `required()` still lists only `offered_languages()` until 7.1; `unavailable()` names a missing Dutch file with its language in the name when Dutch is patched in.

**Verify:** `uv run pytest tests/unit/test_authoring_agent_nl.py tests/unit/test_prompt_files_languages.py -q`.

## Phase 5 — The Dutch tutor: tutor, mode and subject prompts, goldens (R2, R3, R8)

**Goal:** a Dutch lesson turn is assembled from Dutch files and the cached prefix is pinned; voice follows. **Done when** the Dutch system-text hashes, the wall test and the voice test pass.

- [ ] 5.1 `prompts/tutor.nl.md`, `modes/{parcours,discussion}.nl.md`, `modes/{parcours,discussion}.opening.nl.md`, `subjects/{mathematics,sciences,languages,general}.nl.md` from the English twins, adapted per §6 (« Op het bord schrijven » with the Belgian-French notation; voice blocks; statistics/flowchart words). Tests: skeleton parity with the French and English twins (headings, markers once and in order, tool and block names), the tutor prompt is subject-neutral, mode-neutral, gender-neutral and cites `Na te kijken punten` (equals every Dutch template's last heading), every mode has both layers marker-free, every subject has one voice block at the end, the path prompt quotes the sentences the interface sends (`Volgende stap.`, `Volgende sectie.`), no French/English prose. **READ**.
- [ ] 5.2 Fixtures: `chapters/rijen_nl/{pack.md,curriculum.yaml}` (the Dutch twin of `sequences_en`); `scripts/seed.py` row (`COURSE_NAME_BY_LANGUAGE["nl"]`), `chapter_files.DEFAULT_CHAPTER_DIRS["nl"]`, `smoke.SECOND_TURN["nl"]`. Tests: `test_seed` for `--language nl`; `load_chapter_dir` validates `rijen_nl`.
- [ ] 5.3 Pins: `system_text_sha_nl.txt`, `system_text_sha_nl_discussion.txt` (created once by the test helper, **READ**, then pinned); each (language, mode) has its own prefix and nothing varying precedes the breakpoint.
- [ ] 5.4 `TutorService`/`prompt_service` turn tests for `nl` (`test_prompt_service_nl`, `test_course_language_turn` parametrised): the model input of a Dutch chapter equals its pinned rendering; `registry.declarations(mode,"nl")` is the French bytes.
- [ ] 5.5 The wall (`test_model_input_wall`): same Dutch course under `fr`, `en`, `nl` accounts → identical provider input; three courses → three different inputs, each equal to its pinned rendering; the tutor path imports no interface catalog and reads no `locale`.
- [ ] 5.6 Voice: `VoiceService.instructions`/`session_config` for a Dutch chapter: the instructions come from the Dutch files with the voice block, `"transcription": {"language": "nl"}`, `realtime_declarations(mode,"nl")` equals the French bytes. Test `test_voice_service`: fr/en configs byte-identical, a Dutch case added.
- [ ] 5.7 Work reading for `nl`: `_PHOTO_LABEL["nl"]` and `work.nl.md` (4.2) read through `WorkReader` (`test_work_endpoint` for a Dutch course).

**Verify:** `uv run pytest`; `uv run python -m scripts.seed --email a@x.be --password '…' --language nl` creates a Dutch seed chapter (Phase 7 makes it usable in the UI).

## Phase 6 — The course language, frontend (R7)

**Goal:** the board draws Flemish notation and the page knows a Dutch course. **Done when** the formatter, learner-sentence and `lang` tests pass in three languages.

- [ ] 6.1 `lib/course-language.tsx`: `COURSE_LANGUAGES = ["fr","en","nl"]`; `lib/tutor/prompts.ts` `LEARNER_SENTENCES.nl` (§5.3); `lib/tutor/transcription-markers.ts` `MARKER_EXAMPLES.nl`. Tests: the context default, a Dutch provider, a nested provider; learner sentences per language and the cited-sentence parity against `parcours.nl.md` (read from `backend/prompts`); the source hint renders the Dutch marks; the French rendering is byte-identical.
- [ ] 6.2 `charts/format.ts`: `DUTCH = {...FRENCH, measureName, boxStats}`, `NOTATION.nl`. Tests: the shared `notation_cases.json` `nl` rows (formatter writes each `text`), `notation-views` parametrised over three languages, a histogram, a box plot and a pie chart render `Frequentie / Mediaan` under `nl`, the French formatter tests untouched.
- [ ] 6.3 Create form, course card, course header, chapter bar: autonym badge and select over `COURSE_LANGUAGES` (no component names a language); `lang="nl"` on Dutch course text from the chapter. Tests: `create-course-form` (lists what the server lists; default = interface language when offered), `course-language`, sweeps: a Dutch interface on French and English courses, French and English interfaces on a Dutch course, with no sentence in the wrong language for its kind.

**Verify:** `cd frontend && npm run typecheck && npm run lint && npm test`.

## Phase 7 — Offer Dutch (R1.1, R2, R3.7, R10)

**Goal:** a student creates a Dutch course and is taught in Dutch. **Done when** the integration tests pass with the real `SUBJECTS` and the manual check is made.

- [ ] 7.1 `domain/subject.py`: the four subjects list `("fr","en","nl")`; remove the need for `dutch_offered` where the real list now serves; the pinned lists move to three languages in the same edit: `test_language` (`offered()`, `offered_languages()`), `test_subjects`, `test_courses_endpoint` (the `/api/subjects` lists), `create-course-form`, `course-language`. `PromptLibrary.required()` now requires every Dutch file: startup stops naming a missing one; `/api/health` lists a broken one with its language.
- [ ] 7.2 Integration `test_dutch_course` (as `test_english_course`): create a Dutch course (each subject), `422` for an unsupported language, `PATCH` with `language` refused, a Dutch chapter from a document with the scripted authoring fakes, the lesson view, a turn whose cached prefix is the Dutch one, a discussion, the DTOs carry `language: "nl"`, another student's Dutch course is a 404.
- [ ] 7.3 Documentation (R10): `documentation/i18n.md`, `course-language.md` (three languages; « Adding things → A language » rewritten from what this epic needed: Phase 0's fixes, the table list), `README.md`, root `CLAUDE.md` (spec 010/011 bullets and the notation invariant: Dutch courses use Flemish notation), `backend/CLAUDE.md` (language lists), `specs/product.md` line 17; `documentation/index.md` only if a file is added.

**Verify:** `cd backend && uv run pytest`, `cd frontend && npm test`; run both servers: register under a Dutch browser, create a « Wiskunde » course in Dutch, drop a Dutch PDF or photos (real provider; costs money), watch the preparation card (« Rédaction du chapitre… » in Dutch), open the lesson: Célestin writes Dutch, the board shows `0,45`, `]2 ; 5[`, `Frequentie`; a French course and an English course still behave as before.

## Phase 8 — Probes, remaining fixtures, real-model checks (R9)

**Goal:** Dutch is held to the standard of French and English with evidence. **Done when** the offline probe tests pass and a person has run and read the real probes.

- [ ] 8.1 Fixtures for the drawing probes: `chapters/{statistiek_nl,analytische_meetkunde_nl,ongelijkheden_nl,eenparige_beweging_nl}` and `material/{maths_statistiek_nl,fysica_eenparige_beweging_nl}.txt` (or Dutch material the user supplies, design §14.2). Tests: each chapter directory validates against its Dutch template and curriculum rules.
- [ ] 8.2 `scripts/probe.py`: `nl` rows for every `probe_tables` entry (`STEPS`, `CLOSING`, `FLOWCHART_WORD`, `FIGURE_NAMES`, `CONVENTION`, `RIGHT_ANGLE`, `WRITTEN_INTERVAL`, `SAMPLE_WORD`), `GUARDRAIL_PROBES_NL`, `DISCUSSION_PROBES_NL` (leak requests, formula outside the pack, section skipping, off-topic, a Dutch injection), `bad_notation` for Dutch (decimal point, thousands comma, English-shape intervals), `leakage_flags` with two stop-word lists (French and English), the report title and counts (§4.8). Tests `test_probe_flags_nl`: each flag fires on a sample and stays silent on correct Dutch (including quoted course material); `probe --language nl --dry-run` loads every chapter and set.
- [ ] 8.3 `smoke`, `voice_smoke`, `voice_probe`, `authoring_eval` (`FIXTURES["nl"]`), `document_eval` take `--language nl`. Tests: `test_scripts_language`/`test_scripts_import`.
- [ ] 8.4 `evals/`: `harness/config.LANGUAGES`, the `--language` `choices` (`worker.py`, `__main__.py`) gain `nl`; `metrics.gate_tutor` applies the leakage gate for `language != "fr"`. Tests in `evals/tests`: config accepts `nl`; the gate fires for a Dutch run with leakage and not for French.
- [ ] 8.5 **Run by hand** (spends the provider key): `smoke --language nl` (CACHE OK per mode), `probe --language nl` then `--charts --flowcharts --figures --plots`, `voice_smoke`/`voice_probe --language nl`, `authoring_eval --language nl`, `document_eval --language nl` on a Dutch PDF. A Flemish speaker reads the transcripts. Record in the Findings section: answer-leak rate (< 1 %), formulas outside the pack (0), leakage count (0), the `TOOL_TEXT["nl"]` decision, `CHARS_PER_TOKEN` checked against `ai_usage`, any notation convention the reader corrects.

**Verify:** `cd backend && uv run pytest && uv run python -m scripts.probe --language nl --dry-run`; `cd evals && uv run pytest`.

## Phase 9 — Close

**Goal:** the documentation is true and the status is honest. **Done when** the checks pass and `specs/index.md` says what was and was not run.

- [ ] 9.1 Full suites: `cd backend && uv run pytest`; `cd frontend && npm run i18n:check && npm run typecheck && npm run lint && npm test`; `cd evals && uv run pytest`; `git status` shows no regenerated French/English golden.
- [ ] 9.2 Record the bundle growth (frontend build output before/after `nl`) and the `CHARS_PER_TOKEN` result in Findings.
- [ ] 9.3 `specs/index.md`: Implemented, with « Dutch copy and prompts awaiting review by a Flemish speaker » and the 8.5 runs that were or were not made.

## Findings

(to be filled by 8.5 and 9.2)

## Deviations

Recorded as they appear. Known from planning:

- The design lists the interface-language and course-language work as one flow; the plan splits it (phases 1–2 interface, 3–7 course) so that the interface language ships first and `nl` is offered as a course language only at 7.1.
- `scripts/probe.py` cannot use `by_language` for tables whose content is the Dutch chapters' vocabulary (they exist only in phase 8): Phase 0.6 replaces `by_language` there by a `probe_tables` helper that tolerates a missing language with a clear exit message; `app/` tables remain strict.
- The shared `accept_language_cases.json` copies change together in 2.3, after the frontend can parse `nl`; Phase 1 pins `nl` parsing inline.
