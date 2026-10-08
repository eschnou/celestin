# Course language

A course has a language, `fr`, `en` or `nl` (Dutch, as written in Flanders), chosen when it is created and never changed (spec 011; Dutch is spec 017).
It is the language of the student's material, the pack, the curriculum, Célestin's speech, the
voice session and the board's notation. It is **not** the interface language
([i18n.md](./i18n.md)): a student can read an English or a Dutch course under a French interface, and the
model is never told which interface language the student chose.

| | Interface language | Course language |
|---|---|---|
| Stored on | `users.locale` | `courses.language` |
| Chosen | in « Paramètres », at any time | in the create form, once |
| Types | `Locale` (`app/domain/locale.py`, `src/lib/locale.ts`) | `CourseLanguage` (`app/domain/language.py`, `src/lib/course-language.tsx`) |
| Read by | the catalogs (errors, statuses, markers, issues), the message functions | the prompts, the text built for the model, the tool rules, the board's notation, the learner sentences |
| In a request | `locale_of(request)` | `chapter.language`, `ctx.language` |

The two lists happen to hold the same codes today; they are two types so that a new interface
language does not become a course language by accident.

## French does not move

Every French course reads, byte for byte, what it read before the course language existed:
`tests/fixtures/render/system_text_sha*.txt`, the render goldens, `board_declarations.json`, the
voice session configuration, the golden SSE transcripts and the French rule tests are untouched.
English and Dutch are added beside French, never in place of it. A function that gained a `language`
parameter defaults it to French, which is also how a forgotten argument would pass unnoticed:
`tests/unit/test_language_is_passed.py` walks the call sites of the application and fails on
one that does not name the language.

## Where the language lives

```
POST /api/courses {name, subject, language}   require_language + require_offered → courses.language
   │
CourseRecord.language ─▶ LessonChapter.language ─▶ TurnContext.language   (locale: display only)
   │                            │                       │
   │                            │                       ├─ curriculum_render(…, language)   overview · brief · state · moment
   │                            │                       ├─ path / section / pace / registry / SAVE_FAILED words
   │                            │                       ├─ tool rules: PACK_WORDS · hole words · interval/pair/number patterns
   │                            │                       └─ registry.declarations(mode, language)
   │                            ├─ PromptLibrary.tutor/subject/mode/mode_opening(language)  ─▶ prompts/*.{lang}.md
   │                            └─ VoiceService: instructions · transcription language hint
   ▼
AuthoringRunner ─▶ AuthoringAgent.run(…, language)
        ├─ prompts: transcribe · verify · authoring_pack · authoring_curriculum (language)
        ├─ MARKERS[language]    count · handwritten_numbers · apply_uncertain · validate_batch
        ├─ PromptLibrary.template(subject, language) + other_templates → pack.wrong_language
        └─ chapter_title(…, language) · Curriculum (validation context) · issue_text · AGENT_WORDS[language]
```

Offering a subject in a language is its files and tables being present: `SubjectInfo.languages`
lists them (`("fr", "en", "nl")` for each of the four subjects), `GET /api/subjects` serves them, and
`offered()` is what the prompt library requires at startup. A language no available subject is
offered in has no required file.

## Per-language tables

Every table that depends on the language is declared with `by_language(fr=…, en=…, nl=…)`
(`app/domain/language.py`), which raises at import unless it covers `COURSE_LANGUAGES`. The table
sits in the module that uses it; there is no central lexicon.
`tests/unit/test_by_language_tables.py` adds a language in a fresh interpreter and imports every
module that declares a table: each must refuse.

| Table | Module | What it holds |
|---|---|---|
| `WORDS` | `services/curriculum_render.py` | the overview, brief, completion and state sentences, day and month names, time of day |
| `KIND_LABELS` | `domain/curriculum.py` | `cours / exercices / synthèse` — `lesson / practice / summary` |
| `WORDS` | `services/path.py` | the path refusals |
| `SAVE_FAILED`, `_UNKNOWN`, `_OUTPUT`, `_WORDS` | `tools/context.py`, `section.py`, `pace.py`, `registry.py` | the other sentences a tool hands the model |
| `CHARS_PER_TOKEN` | `services/history.py` | 3.2 / 4.0 / 3.4, so English or Dutch history is not trimmed as French |
| `MARKERS` | `domain/transcription.py` | `[manuscrit` … / `[handwritten` … / `[handgeschreven` …, the page-batch sentences |
| `_NUMBERING_BY_LANGUAGE` | `domain/pack.py` | the chapter-numbering words `chapter_title` strips |
| `AGENT_WORDS` | `services/authoring/words.py` | what the agent says around the material |
| `PACK_WORDS_BY_LANGUAGE`, `COMMA`, `GROUPS` | `tools/plots.py` | which function the pack must name; the comma a pair uses; half-open intervals |
| `HOLE_WORDS` | `tools/flowcharts.py` | the phrases that mark a box as a hole |
| `INTERVAL`, `COORDS`, `DEGREES`, `LENGTH` | `tools/figures.py` | hand-written notation, and how a measure is read |

The French constants (`PACK_WORDS`, `_COMMA`, `_INTERVAL`, …) keep their names and shapes, so the
French tests that read them did not change.

## The prompt set

One file per language beside the others: `tutor.fr.md`, `tutor.en.md` and `tutor.nl.md`, `modes/<mode>.{lang}.md`
and `modes/<mode>.opening.{lang}.md`, `subjects/<subject>.{lang}.md`,
`templates/<subject>.pack.{lang}.md`, `authoring/{pack,curriculum}.{lang}.md`,
`transcription/{transcribe,verify,work}.{lang}.md`. `PromptLibrary` takes the language in every
accessor, caches by file name, and `/api/health` lists a broken file with its language in the name.

The English files keep the French skeleton (`tests/unit/test_prompt_files_languages.py` compares
headings, markers, tool and block names), carry no French, and say in their own terms what is
notation or culture:

- the board's notation: decimal point, `12,500` only from five digits, intervals `(a, b)`,
  `[a, b)`, `(−∞, 2]`, coordinates `(2, −1.5)`, sets in braces;
- the pack's headings: « Chapter objective … Points to check » (each subject names its §3 its own way: sciences « Notation, quantities and units », languages « Language
  studied and conventions », general courses « Reference points and conventions »), with the sentinels « None. », « Nothing in the material. », « not corrected in
  the material »;
- the transcription's marks: `[handwritten]`, `[uncertain: a | b]`, `[illegible]`,
  `[empty page]`, `[figure: …]`, `[crossed out: …]`, and « never translate »;
- the voice block's spoken forms: « x squared », « u sub n », « two point five ».

The Dutch files keep the same skeleton and are written in the Flemish register (« je » for the learner, `u` never, the glossary of the spec's Appendix A). Their notation is the one Belgian French uses — decimal comma, `]a ; b[`, `(2 ; −1,5)`, `12,5 %`, sequences from `u₁` — **held by reference**: `DUTCH` in `charts/format.ts` is `{...FRENCH, …}`, the `nl` rows of `notation_cases.json` repeat the French ones, and the Dutch prompt files say it in words. Changing the Flemish board's notation later is changing those three places (and the golden renders). The Dutch pack headings are « Doel van het hoofdstuk … Na te kijken punten » with the sentinels « Geen. » and « Niets in de cursus ». The copy and the prompts were written by us and await review by a Flemish speaker.

The English system text has its own pins (`system_text_sha_en.txt`,
`system_text_sha_en_discussion.txt`, and `_nl` twins) and its own cached prefix per chapter and mode. A chapter has
one language, so nothing about caching changes inside a chapter.

## Authoring in the course's language

The transcription reads the pages in the course's language and writes what it sees, in the page's
own language, with that language's marks; it never translates. The pack and curriculum stages
write in the course's language from the template of that language. A pack whose headings are those
of the subject's template in another language is reported as `pack.wrong_language` before any other
reason (`index_pack(…, alternatives)`); nothing detects the language of the material itself, so an
English document uploaded to a French course is the student's to notice.

A `ContentIssue` has two audiences: the authoring model repairs its output from the reason in
the **course** language (`issue_text(issue, language)`: French is the `message` the code always
wrote), the student's editor shows it in the **interface** language (`render_issue(issue, locale)`).
The `*_language` params of an issue hold codes and are named in the reader's language.

## The tool declarations

`registry.declarations(mode, language)` and `realtime_declarations(mode, language)` are built once
per pair. `TOOL_TEXT[language]` is an overlay of `{tool: {JSON pointer: text}}` applied on top of the
declaration built from the code; it is empty for all languages, so the English and Dutch declarations equal
the French ones until the English probes show French leaking from the descriptions into an English
course's speech or cards. Then only the texts that leak are written there, with one more snapshot.
The refusals the rules return stay French in the other two languages (they are an exchange between the tool
and the model; the model answers in the course's language).

## The board

`frontend/src/components/celestin/charts/format.ts` holds the notations: `FRENCH` (the original
functions, by reference), `ENGLISH` and `DUTCH` (the French notation plus the Dutch measure and box-plot words), chosen by `notationFor(language)` and read in the views with
`useNotation()`. The pure layout helpers take a `notation` parameter that defaults to French.
`backend/tests/fixtures/notation_cases.json` ↔
`frontend/src/components/celestin/charts/__tests__/notation_cases.json` is the shared table: the
formatter must write each `text`, and the rule patterns (`INTERVAL`, `COORDS`, `_number`) must
recognise and read it back.

`CourseLanguageProvider` (`src/lib/course-language.tsx`) is mounted by the course, chapter,
content and discussion routes from what the server sent; `useCourseLanguage()` is French outside
a provider. It sets `lang` on course text and chooses the learner sentences
(`lib/tutor/prompts.ts`: what the interface says to the model on the student's behalf), the
transcription marks the source editor names, and the notation.

## Adding things

- **A language** (say `de`). Dutch was the first one added after the table machinery existed, and this is what it
  needed, in the order that kept every step green:
  1. The types: `CourseLanguage` and `COURSE_LANGUAGES` (`domain/language.py`), the frontend type
     (`lib/course-language.tsx`). Every `by_language` table now fails at import until it has a row; add the rows
     module by module (the table above lists them). Two places are not tables and were found late: the
     work route's « nothing » phrases and `work_reading`'s doubt phrases, which now read `MARKERS`.
  2. The prompt set: one `*.de.md` beside every `*.fr.md` (the tutor, two mode files and their openings, four
     subject prompts and templates, the two authoring prompts, the three transcription prompts), kept on the
     French skeleton (`test_prompt_files_languages.py` compares headings, markers and block names, and the
     neutral-pronoun and no-other-language checks), plus fixtures: a valid curriculum and pack per subject
     used, a chapter directory, the render goldens (`*_de.txt`, read by a person before they are pinned) and the
     two system-text hashes.
  3. The rules: the `INTERVAL` / `COORDS` / `NUMBER` patterns (a language whose board writes a decimal comma
     inside a pair needs the union of the French and the English shapes), `PACK_WORDS_BY_LANGUAGE`,
     `HOLE_WORDS`, the notation rows in the shared table and the frontend `notationFor`.
  4. The scripts: `probe_tables` (the probe vocabulary is allowed to be missing until its fixtures exist),
     `chapter_files`, `seed`, `smoke`, `voice_probe` and `--language` choices; `evals/`'s `LANGUAGES`.
  5. Only then `SubjectInfo.languages` gains the code, and the pinned lists (`test_language`,
     `test_subjects`, `test_courses_endpoint`, the frontend create-form fixtures) move together. Until
     then a test that needs the language asks for it by patching `SUBJECTS`.
  The interface side is separate ([i18n.md](./i18n.md), « Another language »): a course language does not need an
  interface language, nor the other way round. No component names a language.
- **A subject in a language**: its `subjects/<subject>.{lang}.md` and `templates/<subject>.pack.{lang}.md`,
  then the language in `SubjectInfo.languages`.
- **A text the model reads**: a field of the module's `by_language` table, never a literal; the
  catalog (`app/domain/messages`) is for text the student reads.

## Probes and checks

`scripts.seed`, `smoke`, `voice_smoke`, `voice_probe`, `authoring_eval`, `document_eval` and
`probe` take `--language en` or `--language nl`. They call the real API and cost money: run them deliberately, read the
transcripts, and record what they show in `specs/011-course-language/tasks.md`. The English and Dutch probe
sets report three numbers per run: the answer-leak rate (target below 1 % of tutor messages), the
formulas or methods outside the pack (target zero), and the count of French (or English) in a Dutch or English course's
speech or cards (target zero; one is a failure to read, not to ignore).

## Known limits

- The English notation is the common international one; a course whose material writes otherwise
  is followed by Célestin's text, not by the board's formatter.
- Material in another language than the course's is not detected, only a pack with the wrong
  template.
- The refusals the rules return, about 150 messages, are French in an English or a Dutch course.
- Only Flemish conventions are offered: there is no `nl-NL` (Netherlands) variant, and `nl-NL` browsers read Dutch with the Flemish board.
- The Flemish board writes the Belgian-French notation (a choice of spec 017, easy to change: see « The prompt set »); a Flemish school that writes `(2, −1,5)` or `[a, b[` is followed by Célestin's text, not by the formatter.
- The English and Dutch prompts, render goldens and pins were written by us and have been read, not
  measured, until the probe runs are made and their transcripts read. The Dutch ones are awaiting review by a Flemish speaker.
