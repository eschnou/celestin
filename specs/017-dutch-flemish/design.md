# 017 — Dutch (Flemish): design

## 1. Overview

`nl` becomes a third **interface language** (`Locale`) and a third **course language** (`CourseLanguage`). Spec 011 built the structure for this (`by_language` tables that refuse at import, `*.{lang}.md` prompt files, typed `Record<Locale, …>` tables on the frontend), so the addition is mostly **rows, files and fixtures**. The research found six places where a language is still a bare `if language == "en"` or an untyped dict, which a third language would silently get wrong: §4.3 fixes them first, so that the next language after this one needs no such pass.

The Flemish board notation is the **Belgian-French one**, held by reference: every `nl` notation row (backend rule patterns, frontend `Notation`) is the French row under a Dutch name, so a convention that turns out different is a one-line edit of a row and of the Dutch prompt's « Op het bord schrijven » section, nothing else.

Decisions on the open points of the requirements (§5):

| # | Question | Decision |
|---|---|---|
| 1 | Flemish notation | Assumptions kept (user, 8 Oct 2026): decimal comma; `12,5 %`; `]a ; b[`, `[a ; b[`, `]a ; b]`, `[a ; b]`, `]−∞ ; 2]`; points `(2 ; −1,5)`; thousands grouped by a space from five digits (fr-BE grouping, unchanged); sequences from `u₁`. Held in: `NOTATION.nl` (frontend), the `*_NL` aliases of the rule patterns (backend), `notation_cases.json` rows for `nl`, and the Dutch subject prompts. Hand-written `]a, b[` is *recognised* by the rules (§4.6) though the board never writes it. |
| 2 | `nl` or `nl-BE` | One code, `nl`. `Intl` tag for the interface is `nl-BE`; `nl-NL` browsers resolve to `nl`. A later `nl-NL` is a new language code (`nl-NL`) with its own rows; nothing in this design prevents it. |
| 3 | Subject vocabulary | The subject prompts impose no curriculum's vocabulary: they say « gebruik de woorden van de cursus » and list only structure words (`oefening`, `bewijs`, `vergelijking`). Belgian school words (`leerkracht`, `toets`, `graad`, `leerjaar`, `cursus`) are used when Célestin names the school. |
| 4 | Declarations / refusals | As for English (011 §4.7): `TOOL_TEXT["nl"] = {}`, declarations equal the French/English ones, refusals stay French; flipped by Dutch probe evidence only. |
| 5 | `CHARS_PER_TOKEN` | `3.4`, an estimate between French (3.2) and English (4.0), to be checked against `ai_usage` (input tokens ÷ prompt characters) after the first Dutch runs. |
| 6 | Who reviews | A Flemish speaker, before the spec status leaves « Dutch copy and prompts awaiting review ». Not a code concern; the status line carries it. |
| 7 | Sweep | Generalised: one `foreignTextOutside(root, locale)` with a detector per interface language (§5.5). The English detector (French accents) is unchanged. |

## 2. Architecture

```
POST /api/courses {language:"nl"}  ──▶ require_language + require_offered ──▶ courses.language = "nl"   (no migration: free strings)
     │
CourseRecord.language ─▶ LessonChapter.language ─▶ TurnContext.language          (011 plumbing: unchanged)
     │                          │                        │
     │                          │                        ├─ by_language tables           +nl row each  (§4.2)
     │                          │                        ├─ rule patterns / readers      +nl (= French) (§4.6)
     │                          │                        └─ registry.declarations(mode,"nl")  == fr == en bytes
     │                          ├─ PromptLibrary: prompts/*.nl.md   (20 files)                        (§6)
     │                          └─ VoiceService: transcription language hint "nl"
     ▼
AuthoringRunner ─▶ AuthoringAgent.run(…, language="nl")   MARKERS · numbering words · AGENT_WORDS · templates *.pack.nl.md

users.locale = "nl"  ─▶ messages/nl.py (server catalog) · frontend messages/nl.json (Paraglide) · Accept-Language nl*  (§4.1, §5.1)
Frontend: NOTATION.nl · LEARNER_SENTENCES.nl · MARKER_EXAMPLES.nl · AUTONYM/INTL_TAG/error-page.nl · create form (autonym select)
```

**Staged offering** (as 011 did): until the last implementation phase `SubjectInfo.languages` stays `("fr", "en")`; `nl` is built and tested underneath (tests build Dutch courses through the repository, or with the `dutch_offered` fixture that patches `SUBJECTS`), and switched on in one edit when every file and table exists (R3.7). Every phase therefore leaves the application releasable and unchanged for users.

## 3. Data models

No database change. `users.locale` is `String(8)` and `courses.language` a free string (specs 010, 011; verified in `db/models.py` and by `test_head_matches_the_models`). No DTO changes: `language`/`locale` are already fields; their `Literal` gains `"nl"`.

```python
# domain/locale.py        Locale = Literal["fr", "en", "nl"]      # LOCALES via get_args: order fr, en, nl
# domain/language.py      CourseLanguage = Literal["fr", "en", "nl"]
# domain/subject.py       SubjectInfo(..., ("fr", "en", "nl"))    # last phase only
```
```ts
// lib/locale.ts           LOCALES = ["fr", "en", "nl"] as const;  AUTONYM.nl = "Nederlands"
// lib/course-language.tsx COURSE_LANGUAGES = ["fr", "en", "nl"] as const
```

`/api/subjects` answers `languages: ["fr","en","nl"]`; `Accept-Language`: `nl`, `nl-BE`, `nl-NL` → `nl` (primary-subtag rule, unchanged code).

## 4. Backend

### 4.1 Types, catalog, locale

- `Locale`, `CourseLanguage`: add `"nl"`. `project.inlang/settings.json`: `"locales": ["fr","en","nl"]`.
- `app/domain/messages/nl.py` (`MESSAGES`, 124 keys, same keys and `{fields}` as `fr.py`; plural keys `*.one`/`*.other`) and `CATALOGS["nl"]`. `plural_category` already gives Dutch's rule (one iff 1) in its non-French branch. New keys in all three catalogs: `language.nl` (`néerlandais` / `Dutch` / `Nederlands`), and `language.fr`/`language.en` in `nl.py` (`Frans`, `Engels`). `test_messages.py` pins parity.
- `Marker` needs nothing (`render` takes the locale).
- `domain/messages/issues.py`: `render_where` is the structural defect of §4.3 (3); the `nl` rows are in Appendix A.

### 4.2 Per-language tables: the `nl` rows

Every `by_language` table gains `nl=`; each fails at import until it does (`test_by_language_tables.py`, which parametrises over the modules it scans).

| Table | Module | `nl` row |
|---|---|---|
| `MARKERS` | `domain/transcription.py` | `[handgeschreven`, `[onzeker`, `[onleesbaar]`, `[lege pagina]`, batch sentences (App. A) |
| `_NUMBERING_BY_LANGUAGE` | `domain/pack.py` | `_NUMBERING_NL`, built like the English one from `_KEYWORD_NL = hoofdstuk|hfdst\.?|hfst\.?|les|eenheid|module|thema|deel|sectie|paragraaf|onderwerp|sessie|week`, number on its own with a closing mark (`4)`, `IV.`) |
| `KIND_LABELS` | `domain/curriculum.py` | `teach: les`, `practise: oefeningen`, `synthesis: samenvatting` |
| `WORDS` | `services/curriculum_render.py` | App. A |
| `WORDS` | `services/path.py` | App. A |
| `_OUTPUT`, `_UNKNOWN`, `SAVE_FAILED`, `_WORDS` | `tools/pace.py`, `section.py`, `context.py`, `registry.py` | App. A |
| `CHARS_PER_TOKEN` | `services/history.py` | `3.4` |
| `TOOL_TEXT` | `tools/registry.py` | `{}` |
| `AGENT_WORDS` | `services/authoring/words.py` | field by field from the English row (App. A glossary) |
| `PACK_WORDS_BY_LANGUAGE`, `GROUPS`, `COMMA` | `tools/plots.py` | App. A / §4.6 |
| `HOLE_WORDS` | `tools/flowcharts.py` | App. A |
| `INTERVAL`, `COORDS`, `DEGREES`, `LENGTH` | `tools/figures.py` | §4.6 |

French rows and constants keep their names and bytes; English rows are not touched.

### 4.3 Structural fixes (the « files and tables » claim made true)

Found by grepping for `"en"`/`== "fr"` and plain dicts keyed by language. Each is a change *before* the `nl` rows, with the French and English behaviour pinned by their existing tests:

1. **`tools/figures._number`**: `float(text.replace(",", "") if language == "en" else text.replace(",", "."))` becomes `NUMBER = by_language(fr=_decimal_comma, en=_thousands_comma, nl=_decimal_comma)` and `_number(text, language)` calls `NUMBER[language](text)`.
2. **`domain/pack._LANGUAGE_NAMES_FR`** (`{"fr": "français", "en": "anglais"}`, a plain dict read by `_wrong_language`) becomes `by_language(fr="français", en="anglais", nl="néerlandais")`. The French reason text for `nl` is « le document suit le modèle en néerlandais, mais ce cours est en français ».
3. **`domain/messages/issues.render_where`**: `if locale == "fr": return where` else the English tables `_EN_WORDS`/`_EN_PATTERNS`. A Dutch interface would get English « title ». Becomes `WHERE_WORDS: dict[Locale, tuple[dict[str,str], list[tuple[Pattern, str]]]]` with `fr` empty and rows for `en` (moved verbatim) and `nl` (App. A); `render_where` reads the locale's entry. A test asserts it covers `LOCALES`.
4. **`services/work_reading._PHOTO_LABEL`**: plain `dict` → `by_language(fr=…, en=…, nl="Hier is de foto van het werk van de leerling.")`.
5. **`scripts/chapter_files.default_chapter_dir`**: `… if language == "en" else …` → `DEFAULT_CHAPTER_DIRS = by_language(...)`; `seed.COURSE_NAME_BY_LANGUAGE`, `smoke.SECOND_TURN`, `voice_probe` word/pattern tables, `authoring_eval.FIXTURES`: the same (`by_language`), each gaining its `nl` row. These live in `scripts/`, which `by_language` scanning (`test_by_language_tables`) already covers once converted.
6. **`scripts/probe.py`**: the `if language == "en"` branches (`guardrails`, `_is_outcome`, `bad_notation`/`notation_flags`, `leakage_flags`, the report title, the `question = … if language == "fr"` flowchart rule) become `by_language` tables or small per-language functions; Dutch rows in §4.8.

`plural_category` and `Locale`-keyed `CATALOGS` stay (correct for `nl`); `test_messages.py` gains `set(CATALOGS) == set(LOCALES)`.

### 4.4 Prompt library and subjects

`file_name(base, language)` already builds `base.{language}.md`; `PromptLibrary` iterates `offered_languages()`. Nothing changes in `services/prompts.py` except that `nl` appears in `COURSE_LANGUAGES`. `SubjectInfo.languages` for the four subjects gains `"nl"` in the last phase. `/api/health` lists a broken Dutch file by name.

### 4.5 Authoring

- `MARKERS["nl"]`, `_NUMBERING_BY_LANGUAGE["nl"]`, `AGENT_WORDS["nl"]` (§4.2). The transcription prompt names `[handgeschreven]`, `[onzeker: a | b]`, `[onleesbaar]`, `[lege pagina]`, `[figuur: …]`, `[doorgestreept: …]` and « vertaal nooit ».
- Templates `templates/<subject>.pack.nl.md` (four): same `exercises_section: 6`, same seven headings in the same positions; titles in App. A; `index_pack` compares headings to the course language's template, and `alternatives` (`other_templates`) now has two entries for any language, so a pack in the wrong language of three is still reported as `pack.wrong_language` (the first alternative whose headings match).
- `issue_text(issue, "nl")` reads the interface catalog entry in `nl` for the issue's code (the course codes are the interface codes); every `issue.*` key therefore exists in `nl.py`.

### 4.6 Tool rules

Rule functions read `ctx.language`; the tables are keyed by it.

- **Belgian conventions by reference.** In `plots.py` and `figures.py`, next to each French constant:
  ```python
  _COMMA_NL = _COMMA            # a comma between digits is a decimal; `(1, 4)` (comma + space) separates
  _DEGREES_NL, _LENGTH_NL = _DEGREES, _LENGTH
  ```
  and rows `nl=_COMMA_NL`, … A convention that differs later is edited on its own line.
- **Hand-written intervals and pairs** (`figures.INTERVAL`, `COORDS`; `plots.GROUPS`): `nl` accepts the board's `;` **and** a comma as the member separator, bracket shapes of both kinds (`]a ; b[`, `[a ; b]`, `]a ; b]`, `[a ; b[`, `(a ; b)`), because Flemish teachers write `]2, 3[`:
  ```python
  _INTERVAL_NL = re.compile(rf"[\[\](]{_BOUND}[^,;\[\]()]*[,;]{_BOUND}[^,;\[\]()]*[\[\])]")   # = _INTERVAL_EN's shape
  _COORDS_NL   = re.compile(rf"\({_BOUND}[^,;()]*[,;]{_BOUND}[^,;()]*\)")
  ```
  A decimal alone in brackets (`]0,5[`) is read as an interval: the refusal lands on an *open exercise's* label, in the safe direction (costs the model one rewrite; the board writes intervals itself); the English rows accepted the same trade (`_COMMA_EN`, 011). `_bare()` strips whitespace before matching, so `, ` and `,` cannot be told apart: not attempted.
- `DEGREES`, `LENGTH`, `NUMBER`, `COMMA` are the French rows (decimal comma; `1.500 m` reads as 1.5, a known limit of the French row too).
- `PACK_WORDS_BY_LANGUAGE["nl"]`, `HOLE_WORDS["nl"]`: App. A. `tan` is simpler than in French and English: *tangens* is always the function (the line is *raaklijn*), so `\btan\b|\btg\b|\btangens\b`.
- Shared case tables: `tests/fixtures/notation_cases.json` ↔ `frontend/.../notation_cases.json` gain `nl` rows (the formatter writes `text`; backend `INTERVAL["nl"]`/`COORDS["nl"]`/`NUMBER["nl"]` recognise/read it back; plus rows for the hand-written comma forms, backend side only: `kind: "recognised"`). `expression_cases.json`, `layer_cases.json`, `capacity.json` are language-free: untouched.

### 4.7 Voice, tool declarations, history

`VoiceService` passes `chapter.language` as the Realtime input-transcription hint: `"nl"` (ISO-639-1, accepted). `registry.declarations(mode, "nl")` is built from the shared construction plus the empty overlay: byte-equal to the French declarations (`board_declarations.json` untouched). `history.estimate_tokens(…, "nl")` uses the 3.4 ratio.

### 4.8 Scripts and evals

`--language nl` for `seed`, `smoke`, `probe`, `voice_smoke`, `voice_probe`, `authoring_eval`, `document_eval` (their `language_of` already validates against `COURSE_LANGUAGES`). Probe tables (after §4.3 6):

- **Flags (Dutch)**: `bad_notation` flags a decimal **point** between digits outside a pack quote (`0.45`), a thousands comma, and English-style `(a, b)` / `[a, b)` intervals (a `)` or `(` closing a half-open interval is not Belgian); `leakage_flags` flags French and English function words and accents-with-French-stopwords outside quoted material (two lists: `FRENCH_STOPWORDS`, `ENGLISH_STOPWORDS`; the English list is new, since a Dutch course is checked against both).
- **Probe sets**: guardrail probes for both modes in Dutch (`GUARDRAIL_PROBES_NL`, `DISCUSSION_PROBES_NL`, the English set translated: leak requests, formula outside the pack, section skipping, off-topic, prompt injection in Dutch); the drawing probes run on Dutch chapters (§8.2) with their `STEPS`, `CLOSING`, `FLOWCHART_WORD`, `FIGURE_NAMES`, `CONVENTION`, `RIGHT_ANGLE`, `WRITTEN_INTERVAL`, `SAMPLE_WORD` rows.
- **Report**: « Rapport — cours en néerlandais … » (the report is in French for the operator, per `Report`); the leakage count is « mots français ou anglais ».
- **`evals/`**: `harness/config.LANGUAGES`, the `--language` `choices` in `worker.py` and `__main__.py` gain `"nl"` (the orchestrator does not import the backend); `metrics.gate_tutor` applies the `french_rate` gate when `language != "fr"` (the metric is the probe's leakage rate; the key name is kept, the README says « leakage »). Fixtures for `authoring_eval` (`FIXTURES["nl"]`) are the Dutch material of §8.2.

## 5. Frontend

### 5.1 Interface language

`lib/locale.ts` (`LOCALES`, `AUTONYM.nl = "Nederlands"`), `i18n-format.ts` (`INTL_TAG.nl = "nl-BE"`), `lib/error-page.ts` (`TEXT.nl`: title « Deze pagina is niet geladen », body « Er is iets misgegaan aan onze kant. Je kunt de pagina vernieuwen of terug naar de startpagina gaan. », retry « Opnieuw proberen », home « Terug naar de startpagina »). `messages/nl.json` (771 keys, same variables and plural forms as `fr.json`; Dutch uses `one`/`other`; `npm run i18n:check` and Paraglide's compiler enforce parity). `src/lib/__tests__/accept_language_cases.json` and its backend twin gain the `nl` rows (§8.1).

### 5.2 Notation

```ts
// charts/format.ts
export const DUTCH: Notation = {
  ...FRENCH,                                  // number, value, pair, bound, interval, classLabel, separator: by reference
  measureName: { effectif: "Frequentie", frequence: "Relatieve frequentie", pourcentage: "Percentage" },
  boxStats: ["Minimum", "Q1", "Mediaan", "Q3", "Maximum"],
};
export const NOTATION: Record<CourseLanguage, Notation> = { fr: FRENCH, en: ENGLISH, nl: DUTCH };
```
Wire identifiers (`measure: "effectif" | …`) do not change. `describe.ts` sentences are interface text (paraglide) and take numbers from `useNotation()`: unchanged.

### 5.3 Learner sentences, markers, source hint

`LEARNER_SENTENCES.nl`: `review: Ik wil graag de sectie “{title}” herhalen.`, `start: Beginnen we met de sectie “{title}”?`, `nextStep: Volgende stap.`, `nextSection: Volgende sectie.`, `answer: Mijn antwoord op de vraag: “{text}”.`, `work: Hier is mijn werk, ingelezen van mijn foto:\n{text}`, `voiceToolFailed: Hulpmiddel niet beschikbaar. Zeg het aan de leerling en ga verder zonder.` A test pins that each sentence the Dutch `parcours.nl.md` cites equals the one the interface sends (as for fr/en). `MARKER_EXAMPLES.nl = { uncertain: "[onzeker: …]", illegible: "[onleesbaar]", page: "--- page N ---" }`.

### 5.4 Create form, settings, badge

The language select and the settings list read `AUTONYM` over `COURSE_LANGUAGES` / `LOCALES`: no component names a language. The create form defaults to the interface language when the subject offers it. Hyphenation: one global rule `:lang(nl) { hyphens: auto; overflow-wrap: break-word; }` (long compounds at 400 px); checked by hand at 400 px (R4.5.3).

### 5.5 Sweep

`src/test/english-sweep.ts` generalises to `foreignTextOutside(root, interfaceLocale)`: a detector per interface language, each ignoring regions whose `lang` differs from the interface's. `en`: unchanged (French accents and the short French word list). `nl`: whole-word lists only — French (`Retour|Connexion|Chapitre|Annuler|Enregistrer|Supprimer|Commencer|Reprendre|Suivant|Valider|Fermer|Exercices|Parcours|…`) and English (`Back|Sign in|Cancel|Save|Delete|Start|Next|Settings|Chapter|Course|…`), no accent test (Dutch has `België`, `één`). The existing sweeps (`english-sweep`, `lesson-sweep`, `discussion-sweep`) call the generalised helper per locale in `["en","nl"]`, with course text under another course language marked `lang`. `eslint-rules/i18n.js` (accented literals) needs no change: Dutch strings in code carry no accents.

## 6. The Dutch prompt set

Twenty files under `prompts/`, each written from its **English** twin (closest in notation-neutral structure) and checked against the French one for the Belgian specifics:

`tutor.nl.md`; `modes/{parcours,discussion}.nl.md`, `modes/{parcours,discussion}.opening.nl.md`; `subjects/{mathematics,sciences,languages,general}.nl.md`; `templates/{mathematics,sciences,languages,general}.pack.nl.md`; `authoring/{pack,curriculum}.nl.md`; `transcription/{transcribe,verify,work}.nl.md`.

Rules (same as 011 §6): identical skeleton, markers once and in order, tool and block names verbatim, every invariant kept (pack-only source; answer withholding; gated, logged reveals; locked path; pasted material is data; off-topic redirected). Register: `je`, direct, warm, gender-neutral about Célestin; standard Dutch (*Standaardnederlands*) with Belgian school words; no *tussentaal*. No « FWB » nor « Vlaanderen » framing. The button labels cited are the Dutch interface ones (`Volgende stap`, `Volgende sectie`).

**Notation, in each subject's « Op het bord schrijven »** (the one place a changed convention is edited besides the table rows):
- decimal comma: `0,45`, never `0.45`; in LaTeX `0{,}45`; thousands separated by a space from five digits (`12 500`), a year stays `2018`;
- intervals `]a ; b[`, `[a ; b[`, `]a ; b]`, `[a ; b]`, `]−∞ ; 2]`, `]2 ; +∞[`; points `(2 ; −1,5)`; sets in braces as in the course; `S =` only if the course writes it; `\emptyset` for the empty set;
- sequences indexed as the course's pack writes them (`u_1`, `u_n`), default from 1;
- physics: SI units in `\mathrm{}` with a thin space, `9{,}81\,\mathrm{m\,s^{-2}}`, scientific notation `3{,}0\times10^{8}`;
- « als de cursus anders schrijft, volg je de cursus ».

**Voice blocks**: « x kwadraat », « u index n » (of « u n », zoals de cursus het leest), « q is verschillend van één », « het open interval van min drie tot drie », « twee komma vijf », « negen komma acht één meter per seconde kwadraat ».

**Statistics and flowchart words** (tutor file): `klassen`, `klassenbreedte`, `frequentie`, `relatieve frequentie`, `kwartielen`, `mediaan`, `boxplot`, `staafdiagram`, `histogram`, `cirkeldiagram`, `stroomdiagram`/`organigram` (as the course writes), `ja / nee`, `invoer / uitvoer`.

**Pack template titles** (maths): `1. Doel van het hoofdstuk`, `2. Voorkennis`, `3. Notatieafspraken`, `4. Begrippen, in didactische volgorde`, `5. Woordenschat`, `6. Typische oefeningen`, `7. Na te kijken punten`. Sciences § 3 `Notaties, grootheden en eenheden`; languages § 3 `Bestudeerde taal en afspraken`; general § 3 `Oriëntatiepunten en afspraken`. Sentinels: `Geen.`, `Niets in de cursus.`, `niet verbeterd in de cursus`. The tutor file cites `Na te kijken punten` (test: equals each template's last heading).

`languages` subject: « De leerling studeert een vreemde taal (vaak Frans of Engels) in het Nederlands » — Célestin speaks the course language (Dutch) and works in the studied language, as the French/English files say for theirs.

## 7. Error handling

| Case | Behaviour |
|---|---|
| `language: "nl"` before the last phase | `422 invalid_language` (not offered), message in the interface language |
| A `by_language` table without `nl` | fails at import, never at runtime |
| A Dutch prompt/template file missing or broken | startup stops naming it; `/api/health` lists it |
| A catalog key missing in `nl` | `i18n:check` / `test_messages` fail; at runtime the French text with a logged `i18n_fallback` (010 behaviour) |
| Pack in the wrong language of the three | `pack.wrong_language` first (any pair involving `nl`); the student reads it in the interface language, the repair loop in the course's |
| Material in another language than the course's | not detected; the student's to correct (probe records the model's behaviour) |

## 8. Testing strategy

### 8.1 Offline

- **Existing pins untouched**: `system_text_sha*.txt`, every `tests/fixtures/render/*` (fr and `_en`), `board_declarations.json`, `error_messages_fr.json`, golden SSE transcripts, French and English rule tests.
- **Tests that list the languages** (≈20 sites, found by grep) change by one of two rules: a test *about every language* is parametrised over `COURSE_LANGUAGES`/`LOCALES` (e.g. `test_board_rules_by_language`, `test_subject_prompts`, `test_course_language_turn`, `test_notation_cases`, `test_model_text_by_language`, `notation-views`); a test that *pins the language list* is updated to `("fr","en","nl")` only in the last phase together with `SUBJECTS` (`test_language`, `test_locale`, `test_subjects`, `test_courses_endpoint` lists, `create-course-form`, `course-language`).
- **New or extended**: `by_language` coverage (scan), catalog parity (`fr`/`en`/`nl`), `CATALOGS` keys == `LOCALES`; `Accept-Language` cases (`nl`, `nl-BE`, `nl-NL`, `nl-BE;q=0.8,fr;q=0.9` → fr, `fr,nl;q=0.8` → fr, `nl;q=0` → fr, `de,nl;q=0.5` → nl), both copies; prompt-file tests per language (markers, skeleton parity with the French and English twins, cited heading, no French/English prose in a Dutch file: two stop-word lists, tool names and `Célestin` excepted); `PromptLibrary`/`required()` over three languages; `system_text_sha_nl.txt`, `system_text_sha_nl_discussion.txt`; Dutch render goldens (`*_nl.txt`, the `check` helper already takes a language); `moment()` (weekday/month/part words, boundaries); `MARKERS`/`validate_batch`/`handwritten_numbers`/`apply_uncertain` for `nl`; `chapter_title` (`Hoofdstuk 3:`, `Les 2 –`, `Thema 4)`, `Module IV.`); `index_pack` against right/wrong templates (all six pairs); `issue_text(·,"nl")` and `render_where` for `nl`; the `_number`/`NUMBER` table; rule tables (one accepted and one refused sentence per `PACK_WORDS` entry, hole phrases, intervals/pairs including `]2, 3[`, `1,5 m`); `notation_cases.json` both sides; the wall test over three languages (same course + any interface → identical input; three courses → three inputs, each equal to its pinned rendering); the voice config (`"language": "nl"`); `test_language_is_passed` unchanged and passing (no new function).
- **Frontend**: `nl` formatter rows; learner sentences + cited-sentence parity; `AUTONYM`/`INTL_TAG`/error page; context default; `lang="nl"` on course text; create form lists three autonyms; the generalised sweeps over `["en","nl"]` with a Dutch interface on French and English courses and French/English interfaces on a Dutch course.

### 8.2 Fixtures (Dutch twins of the English ones)

`tests/fixtures/`: `packs/{maths_valid_nl,sciences_valid_nl}.md`, `curricula/valid_nl.yaml`, `material/{maths_kwadratische_nl,maths_statistiek_nl,fysica_eenparige_beweging_nl,injection_nl}.txt`, `chapters/{rijen_nl,statistiek_nl,analytische_meetkunde_nl,ongelijkheden_nl,eenparige_beweging_nl}/{pack.md,curriculum.yaml}` (≈1 100 lines in all), written to the Dutch templates; they are test fixtures, never course content offered to students. Offline phases need only `maths_valid_nl`, `valid_nl`, `rijen_nl` and one material text; the other chapter directories and materials are written with the probes phase.

### 8.3 Real-model checks (run by a person, recorded in the spec)

`smoke --language nl` (CACHE OK per mode), `probe --language nl` (guardrails, then `--charts --flowcharts --figures --plots`), `voice_smoke`/`voice_probe --language nl`, `authoring_eval`/`document_eval --language nl`. Reported per course language: answer-leak rate (< 1 %), formulas outside the pack (0), leakage count (0). The first Dutch run also decides `TOOL_TEXT["nl"]` and checks `CHARS_PER_TOKEN`. Transcripts are read by a Flemish speaker.

## 9. Performance considerations

Tables and regexes at import (a few dozen more); prompt files cached by mtime like the others; one more cached prefix per (subject, mode) for Dutch courses only. Paraglide compiles three catalogs into the one bundle: the added weight is the `nl` message functions (about the size of `en`), measured by the build output and reported in the tasks.

## 10. Security considerations

`language` from a body goes through `require_language`; file names come from `file_name(base, language)` with `language` a `Literal`. Pasted material is data in Dutch (the Dutch prompts carry the rule; a Dutch injection probe runs). Nothing new is logged about a student. `nl` in `Accept-Language` selects a catalog, never a path.

## 11. Monitoring and observability

Existing lines already carry `language` (`course_created`, `authoring_started`) and the interface locale resolution is unlogged by design. `i18n_fallback`/`i18n_missing` (010) are the signal for an untranslated key; `/api/health` lists a broken Dutch file. No new log line.

## 12. Documentation to update with the implementation

`documentation/i18n.md` (three interface languages, `Accept-Language` for `nl`, the `render_where` table, the sweep), `course-language.md` (three languages, the `nl` rows, « Adding things → A language » rewritten from what this epic actually needed, the structural fixes), `README.md`, root `CLAUDE.md` (spec 010/011 bullets and the notation invariant), `backend/CLAUDE.md` (language lists), `specs/product.md` line 17, `specs/index.md`. `documentation/index.md` only if a file is added.

## 13. Differences from the requirements

| Requirement | Design |
|---|---|
| R6.3 « `]a ; b[`, `]a, b[` recognised » | Both separators recognised by `nl` `INTERVAL`/`COORDS`/`GROUPS`; the board and the prompts write `;`. A decimal alone in brackets is read as an interval (safe direction, §4.6). |
| R7.1 notation held in a table | By reference to the French row (`DUTCH = {...FRENCH, …}`; `*_NL` aliases): same bytes by construction, divergence is a local edit. |
| R3.1 file list | 20 files (the requirement lists the families; `transcription/work.nl.md` and the four subjects are explicit here). |
| R5.3 | `CHARS_PER_TOKEN["nl"] = 3.4`, an estimate to verify. |
| R7.6 « language sweep » | `foreignTextOutside(root, locale)` with per-interface detectors; the Dutch detector uses word lists, not accents. |
| R9.5 evals | `evals/` takes `nl` in `LANGUAGES` and the `choices`; the gate key `french_rate` is applied for any non-French course and means leakage. |
| R4.1 `[figuur: …]`, `[doorgestreept: …]` | Named in the prompts only; `MARKERS` holds the four marks the code reads (handwritten, uncertain, illegible, empty page), as for fr/en. |

## 14. Open points for the user

1. A Flemish speaker for the review of the interface copy (`nl.json`, `nl.py`) and the 20 prompt files; the status line stays « Dutch copy and prompts awaiting review » until then.
2. The drawing-probe chapters (§8.2) are a large body of Dutch course text; if the review of the first guardrail probes is satisfactory, the other four chapter directories could be derived from existing Dutch school material the user owns instead of being written by us.

## Appendix A — Dutch words

**`curriculum_render.WORDS["nl"]`**

| field | text |
|---|---|
| `overview_heading` | `## Traject van het hoofdstuk “{title}”` |
| `lead_parcours` | `Secties in volgorde, vergrendeld: een sectie opent pas wanneer de vorige afgerond is. `start_section(id)` geeft je het plan van een sectie, `complete_section(id, samenvatting)` rondt ze af.` |
| `lead_discussion` | `Secties in volgorde. Dit is het traject van het hoofdstuk: het wordt gevolgd in de trajectmodus, niet hier. Je kunt je leerling zeggen waar een begrip behandeld wordt en voorstellen er naartoe te gaan; je kunt geen sectie openen of afronden.` |
| `overview_line` | `{index}. `{id}` ({kind}) — {title}. {goal}` |
| `brief_head` | `Sectie “{label}” ({kind}), {index}/{total}.` |
| `review` | `Herhaling: deze sectie is al afgerond. Rond ze niet opnieuw af.` |
| `goal`, `beats_head`, `beat` | `Doel: {goal}`, `Verloop:`, `{index}. {beat}` |
| `exercises`, `exercises_separator` | `Typische oefeningen: {exercises}.`, `; ` |
| `to_do` | `Te doen: {count} oefening(en), één per keer.` |
| `done_when` | `Afgerond wanneer: {done_when}` |
| `completion_last`, `completion_next` | `Sectie afgerond. Hoofdstuk afgerond.`, `Sectie afgerond. Volgende sectie: “{label}” ({kind}), id: {id}.` |
| `now` | `Het is {moment}.` |
| `status` | `Stand van het traject: {done} sectie(s) afgerond op {total}.` |
| `active`, `active_hint` | `Huidige sectie: “{label}” ({kind}).`, `Als je het plan nog niet in dit gesprek hebt, roep dan start_section("{id}") aan.` |
| `finished` | `Hoofdstuk afgerond. Stel een herhaling van een sectie naar keuze voor.` |
| `none_active`, `start_hint` | `Geen sectie bezig. Volgende: “{label}” ({kind}).`, `Begin eraan met start_section("{id}").` |
| `discussion_active` | `Huidige sectie in het traject: “{label}” ({kind}), daar verder te zetten.` |
| `discussion_finished`, `discussion_none_active` | `Hoofdstuk afgerond: het hele traject is gedaan.`, `Geen sectie bezig. De volgende zou “{label}” ({kind}) zijn, te doen in het traject.` |
| `moment` | `{weekday} {day} {month}, {hour}:{minute:02d} ({part})` |
| `days` | maandag, dinsdag, woensdag, donderdag, vrijdag, zaterdag, zondag |
| `months` | januari, februari, maart, april, mei, juni, juli, augustus, september, oktober, november, december |
| `parts` | voormiddag, namiddag, avond |

**`path.WORDS["nl"]`**: `unknown` `Sectie “{section_id}” bestaat niet. Secties van het hoofdstuk: {ids}.`; `locked` `Sectie “{label}” is nog niet open.{hint}`; `hint` ` Je kunt “{label}” beginnen (id: {id}).`; `none_active` `Geen sectie is bezig. Begin er een met start_section.`; `only_active` `Alleen de huidige sectie kan worden afgerond: “{label}” (id: {id}).`

**Other model-facing rows**: `pace._OUTPUT` `Knop “Volgende stap” geactiveerd. Beëindig je beurt en wacht tot de leerling klikt of antwoordt.`; `section._UNKNOWN` `Onbekende sectie in het huidige traject.`; `context.SAVE_FAILED` `Ik kon je voortgang niet opslaan. Probeer opnieuw.`; `registry._WORDS` `bad_json` `Ongeldige JSON-argumenten: {reason}.`, `not_object` `De argumenten moeten een JSON-object zijn.`, `invalid` `Ongeldige argumenten. {details}`, `unavailable` `De tool '{name}' is hier niet beschikbaar. Beschikbare tools: {offered}.`, `root` `(basis)`.

**`MARKERS["nl"]`** batch sentences: `missing` `ontbrekende markering voor pagina `; `unexpected` `onverwachte pagina `; `disordered` `paginamarkeringen dubbel of in de verkeerde volgorde`; `empty_without_marker` `lege pagina zonder “[lege pagina]”`.

**`PACK_WORDS["nl"]`** (case-insensitive; one accepted and one refused sentence per entry fix the final patterns): `exp` `\\exp(?![A-Za-z])|\bexp\s*\(|\bexponenti[eë]le\s+functies?\b|(?-i:\be\}?\s*\^)(?!\s*\{?\s*[-+−](?!\s*[\w\\({]))`; `ln` `\bln\b|\bnatuurlijke\s+logaritmes?\b|\bneperiaanse\s+logaritmes?\b|\blogaritmes?\s+met\s+grondtal\s+\$?\s*(?:\\mathrm\{e\}|\{e\}|e)(?!\w)`; `log` `\blog(?![A-Za-z])|\b(?:tientallige|decimale|briggse)\s+logaritmes?\b|\b10-logaritmes?\b|\blogaritmes?\s+met\s+grondtal\s+\$?\s*10\b`; `cbrt` `\b(?:derdemachts|kubieke)\s*wortels?\b|\\sqrt\s*\[\s*3\s*\]|∛`; `sin` `\bsin\b|\bsinus`; `cos` `\bcos\b|\bcosinus`; `tan` `\btan\b|\btg\b|\btangens\b`.

**`HOLE_WORDS["nl"]`** (on `_plain_words` text): head `(?:vak|stap|knoop|tekst|blok|vraag|antwoord)(?: nr)?(?: \d+)?`; gap `(?:(?:in|aan) te vullen|te (?:vinden|bepalen|raden|schrijven|plaatsen|preciseren)|nog te (?:bepalen|vinden)|vul (?:hier )?(?:in|aan)|ontbrekende?(?: hier)?|verborgen|onbekende?|mysterie|tbd)(?: door (?:de )?leerling| door jou)?`; word list `head(?: gap)?|gap(?: head)?|[lc]?dots`.

**`render_where` rows**: `nl` words `{"titre": "titel", "chapitre": "hoofdstuk", "parcours": "traject"}`; patterns `^exercice (\S+)$` → `oefening \1`, `^section n°(\d+)$` → `sectie nr. \1`.

**Glossary for `AGENT_WORDS["nl"]` and the other tables** (translate the English row field by field with these): document = *document*; material = *cursusmateriaal*; page = *pagina*; text layer = *tekstlaag*; chapter = *hoofdstuk*; path = *traject*; section = *sectie*; exercise = *oefening*; to repair = *herstellen*; points to check = *na te kijken punten*; student = *leerling*; teacher = *leerkracht*. The French tag names (`<materiel>`, `<chapitre>`, `<lignes>`, `<couche_texte>`) are not language and stay.
