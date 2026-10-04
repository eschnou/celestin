# Chapters: the pack, the curriculum and the path

Since spec 005 a chapter is a database row owned by a student's course. It holds three things:

| Column | Says | Read by |
|---|---|---|
| `source_text` | The chapter's material as text: the transcription of the document the student dropped (spec 006), or that text as the student corrected it. | The authoring agent ([authoring.md](./authoring.md)), the « Texte extrait du document » tab. |
| `pack` | **What** the teacher teaches, restructured into the subject's template: definitions, formulas, notation, vocabulary, sample exercises, points to check. Markdown. | The prompt, in full, inside the cached prefix. |
| `curriculum` | **In which order** Célestin teaches it: an ordered list of sections. JSON. | The prompt (a one-line-per-section overview), the section tools (the brief of one section), the interface (titles and goals). |

`pack`, `curriculum` and `title` are written together or not at all, with `content_version`
incremented in the same transaction and the chapter's progress deleted. A chapter is **ready** when
`content_version > 0`. Next to them sit `section_count` and `title` (denormalised for the course
page), `authoring_state` (`idle`, `generating`, `failed`) with `authoring_error` (the failure code, turned into a French message for the client), and since spec 006 `source_kind` (`document`; `text` for the seed), `authoring_stage` (`transcription`, `pack`, `curriculum`: where a run is, or stopped), `pages_done` and `page_count`.

## The transcription

A document is never stored; its transcription is. It is plain text with one marker per page and a
few marks the pack stage and the student can rely on:

| Mark | Means |
|---|---|
| `--- page N ---` | Start of page N, on its own line, every page in order. |
| `[manuscrit] …` | A handwritten passage (answers, corrections, notes in the margin). |
| `[incertain: a \| b]` | A handwritten figure or word readable two ways. Doubt is always marked: a wrong reading presented as sure is the worst error. |
| `[illisible]` | Nothing can be read there. |
| `[figure : …]` | A drawing or graph, described, so the pack can carry it as data. A statistical chart keeps its kind, axis titles, categories or classes and every readable value (spec 008). A graph in a repère keeps each axis's title and unit, the graduation, the shape and every readable point. A geometric figure keeps its points, the coordinates or measures one can read, and its codage. A number line keeps the numbers placed, each interval and the way its brackets face, or what is hatched. A diagram of sets keeps its sets, what each zone holds and the hatched zones. An organigramme keeps each box's text and shape (start or end, step, question, input or output) and where each arrow leads, with its label. Nothing unread is written. |
| `[barré: …]` | Crossed-out text. |
| `[page vide]` | A page with nothing on it. |

The marks above are the French set. An English course's transcription writes `[handwritten]`,
`[uncertain: a | b]`, `[illegible]`, `[figure: …]`, `[crossed out: …]` and `[empty page]`
(no space before the colon; `domain/transcription.py` `MARKERS`); `--- page N ---` is the same in both,
and nothing is ever translated. A stored French source keeps validating under `fr`.

Formulas are LaTeX; the typed course and the handwriting are copied, never corrected. The pack
prompt turns uncertain and illegible passages into « Points à vérifier » rather than guessing.

`chapter_uploads` records which pages of the source came from which upload (`first_page`,
`page_count`, `run_id`). Today a document replaces the source, so a chapter has one row; the row is
there for a later « ajouter des pages » that transcribes only new pages and appends them.

The chapter 1 files of specs 002–004 (`backend/tests/fixtures/chapters/suites/`, a sequences chapter written
for the tests: a student's own material is never in the repository) remain as seed input only: `scripts/seed.py` stores them for a local test student
([running-locally.md](./running-locally.md)).

## How a chapter is numbered

The authoring model writes a title and nothing else: « Nombres réels et suites ». The number
comes from the chapter's `position` in its course, so two courses never both show « Chapitre 1 :
… » for different material, and reordering chapters later renumbers them by itself.

- Stored: `chapters.title` and the curriculum's `title` hold the bare title. `chapter_title`
  (`domain/pack.py`) strips « Chapitre 3 : », « Chap. II - », « 4) » and the like from whatever
  the model or the material wrote; a title that is only a number, or a real one starting with a
  number (« 1000 façons de compter »), is kept as is.
- Displayed: `display_title(position, title)` in `api/routes/courses.py` composes
  « Chapitre 2 — Les suites » for the lesson view (`ChapterView.title`, which also carries
  `position`), and `chapterName()` in `components/celestin/chapter-row.tsx` does the same for the
  content page. The course page shows the number in its own column next to the bare title.

## The pack template

Every subject has a template, `backend/prompts/templates/<subject>.pack.fr.md` (and `.en.md`): a YAML header
(`subject`, `exercises_section`) and a skeleton whose numbered level-2 headings are the required ones. The four
subjects share the numbering (`tests/unit/test_subject_prompts.py` builds a pack from each template's own headings
and checks that none is accepted as another's):

| § | Mathematics | Sciences | Languages | General courses |
|---|---|---|---|---|
| 1 | Objectif du chapitre | Objectif du chapitre | Objectif du chapitre | Objectif du chapitre |
| 2 | Prérequis | Prérequis | Prérequis | Prérequis |
| 3 | Conventions de notation | Notations, grandeurs et unités | Langue étudiée et conventions | Repères et conventions |
| 4 | Notions, dans l'ordre d'enseignement | Notions, dans l'ordre d'enseignement | Notions, dans l'ordre d'enseignement | Notions, dans l'ordre d'enseignement |
| 5 | Vocabulaire | Vocabulaire | Vocabulaire | Vocabulaire |
| 6 | Exercices types | Exercices types | Exercices types | Exercices types |
| 7 | Points à vérifier | Points à vérifier | Points à vérifier | Points à vérifier |

What differs is what a notion (§ 4) holds. Sciences: definitions, laws and formulas, chemical equations, structures
and processes, experiments, diagrams and documents, graphs. Languages: the rule, the forms (one per line, accents
included), exceptions, the course's example sentences in the language they are written in, texts quoted word for
word; the vocabulary lists are copied exactly and nothing written in the language studied is translated. General
courses: definitions, facts and reference points, causes and consequences, and each **document** (what it is, its
source, what can be read on it, what the course takes from it). The templates and subject prompts were written
without sample material from real courses for the last three: they are first drafts to be tuned on real chapters
(`scripts.authoring_eval`, `scripts.probe`).

The mathematics template also asks, in comments only, for the course's drawings, the ones the
board's drawing blocks can show (see [tutor-turn-pipeline.md](./tutor-turn-pipeline.md)).

In § 3, for statistical charts (spec 008), a « Représentations graphiques » bullet names each kind the
course uses and its conventions: class brackets, reference amplitude, polygon closed or not, quartile
definition. When the material has other drawings, § 3 has one bullet for each, in the course's own
words and conventions:

- « Graphiques » for functions or sequences in a repère: graduation, orthonormal or not, isolated
  points for a sequence, filled or hollow endpoints, the curves' names;
- « Figures » for geometry and sets:
  - a point marked by a cross or a dot;
  - the codage of equal lengths and right angles;
  - an interval on a number line as brackets, as filled and hollow dots, or by hatching what does
    not fit;
  - diagrams of sets;
- « Organigrammes » for methods or algorithms: the shapes and words used (« Début », « Lire »,
  « Afficher », « Si … alors »…).

In § 4, a « **Représentation graphique** » line per notion carries the chart, figure or organigramme
the course draws for it, with its kind and its data as the material gives them:

- classes and their counts;
- a function's or a sequence's expression, window and notable points;
- a figure's points, measures and codage;
- intervals;
- sets and their elements;
- an organigramme's box texts, its questions and their answers.

The sciences template's « **Graphiques** » line per notion asks what each graph shows (axes and units,
shape, slope, phases), with its readable values (measurements, plateaus, instants).

No heading was added, so packs written before stay valid. Célestin draws only the representations and
methods the pack names. That is a prompt rule, which `scripts/probe.py` measures with `--charts`,
`--flowcharts`, `--figures` and `--plots`. The tool checks it in one place: a plot's expression may
not use a function the pack never names (`pack_function`). The pack must name the function itself
(« fonction exponentielle », `\ln`, « tangente d'un angle »), not a word sharing its root (« une
croissance exponentielle », « la tangente en A »). A function drawn from computed points or a broken
line is not checked; the plot probe measures it.

`app/domain/pack.py` `index_pack` checks a pack against its template and extracts identifiers:

- exactly one `# Titre`, first; it is the chapter title, without the numbering the material
  gives it (« Chapitre 1 : les suites » is stored as « Les suites »): chapters are numbered by
  their position in the course, so two courses' « Chapitre 1 » never read the same. The prompt
  asks for the title alone; `chapter_title` in `domain/pack.py` strips one anyway;
- the `## N. Titre` headings are the template's, same numbers, same titles (case and spacing
  ignored), same order;
- `### N.M Titre` sits under `## N.` and gives the id `§N.M` (`## N.` gives `§N`); unnumbered
  `###` are free;
- under the exercises section only, each exercise is a `#### N.M.K` heading under `### N.M`;
  at least one;
- fenced code is ignored; the document is at most `PACK_MAX_CHARS`.

Each failure is a `ContentIssue(where, message)` in French (`§ 5`, `exercice 6.1.3`, `titre`),
at most 20. The editors show them, the authoring agent sends them back to the model.

« Points à vérifier » lists what could not be established: unreadable passages, corrections that do
not check out, contradictions. The tutor prompt says Célestin does not teach, cite or set exercises on
those points, and tells the student to check them with the teacher.

## The curriculum

```jsonc
{
  "id": "5e5e…",                        // the chapter id, always set by the server
  "title": "Les suites numériques",
  "sections": [
    {
      "id": "sa-somme",                 // url-safe, unique
      "kind": "teach",                  // teach | practise | synthesis
      "title": "Suites arithmétiques — somme de n termes",
      "goal": "Connaître Sₙ = (u₁ + uₙ)·n/2 et savoir reproduire sa démonstration.",
      "pack": ["§4.2 propriété 4"],     // references into the pack
      "beats": ["La démonstration du cours…", "Question de contrôle…"],   // teach only
      "done_when": "Elle a reproduit la démonstration…"
    },
    {
      "id": "sa-applications",
      "kind": "practise",
      "title": "Suites arithmétiques — applications",
      "goal": "Résoudre les applications du cours sur les SA.",
      "exercises": ["6.1.1", "6.1.2", "6.1.3 (sans la somme)"],   // practise / synthesis only
      "count": 3,
      "done_when": "Trois exercices résolus, dont un avec la somme."
    }
  ]
}
```

Validation (`app/domain/curriculum.py`): a `teach` section has `beats` (at most 12) and no
exercises; the others have `exercises` (at most 12) and a `count` (1–10); ids unique; 1–40 sections;
texts up to 600 characters; unknown keys refused. `check_curriculum` returns the curriculum or
`ContentIssue`s naming the section. `app/domain/content.py` `validate_content` runs the pack index,
the curriculum rules and the references together; the editors, the authoring agent and the seed all
use it, and adoption only accepts its result (`ValidContent`).

**References** (`app/domain/references.py`): every `pack` entry starts with a `§` id that exists in
the pack; every `exercises` entry starts with an exercise id (`6.1.3`) or, for a pool drawn from a
whole part of the pack (a table of applications, the definitions to recite), a `§` id. The rest of
the entry is free text for the tutor.

The stored curriculum is parsed once per `(chapter id, content version)` (`CurriculumCache`). A
stored curriculum that no longer validates makes that chapter a `500 chapter_unavailable` and logs
`chapter_invalid`; other chapters are unaffected.

## Editing

From « Contenu du chapitre » (`/courses/{course}/chapters/{chapter}/content`):

- **Contenu**: a Markdown editor with a preview. Saving checks the template and re-checks the
  stored curriculum's references against the new pack.
- **Parcours**: a form per section (kind, title, goal, beats or exercises and count, pack references,
  done-when), add, move, remove. Saving checks the curriculum and its references against the stored
  pack.
- **Texte extrait du document**: correcting the transcription starts a new authoring run from the
  pack stage; « Remplacer par un document » reads a new document first. The current content stays in
  use until the run succeeds; on failure it stays and the failure is shown. « Redéposer le document »
  on a failed row opens this tab (`?tab=source`).

Every adopted change deletes the chapter's progress. The editors send the `version` they loaded; a
chapter changed meanwhile answers `409 stale_version` and nothing is written. While a new version is
being prepared, pack and path edits answer `409 authoring_running` (the run would overwrite them
when it finishes) and the editors are disabled. A section tool saves progress against the content
version its turn loaded; a save racing an edit is refused, so stored progress never names sections
of an older path. A save that would
reset existing progress asks for confirmation first.

## Three kinds of section

| Kind | Label | Célestin does | Ends when |
| --- | --- | --- | --- |
| `teach` | « Leçon » | Follows the beats in order, one board card per beat, quoting the course verbatim, a short check between beats, a `check_question` card at the end. No exercise cards. | The check question is answered. |
| `practise` | « Exercices » | Sets `count` exercises one at a time, each a variant of the listed sample exercises, explaining only to unblock. | The `done_when` criterion is met, on the tutor's judgement. |
| `synthesis` | « Synthèse » | Like practise, mixing everything before it, without naming the notion. | Same. |

The per-kind behaviour is text in `backend/prompts/tutor.fr.md`, section « Le parcours ». The
structure (which section, which beats, which pool) is data; the prose is generated live.

## The locked path

Every section is in one state, computed by `app/services/path.py` from the curriculum order and the progress:

- `done`: in `progress.done`.
- `active`: `progress.active`. At most one.
- `available`: the first section that is neither, and only when nothing is active.
- `locked`: everything after the available one, or everything else while a section is active.

Rules, enforced in the tools and not in the prompt:

- `start_section(id)` works on the available, active or done section. A done one opens as a **review**, which changes nothing. A locked one is refused with a tool error naming the section that can be started; the model reads that and explains it to the learner.
- `complete_section(id, summary)` works on the active section only. The summary is logged (`section_completed`); it is the only record of why a practice section closed until a checker exists.

The frontend keeps a display-only mirror of the same rules in `lib/tutor/path.ts`, tested against the same case table (`backend/tests/fixtures/path_cases.json`, copied to `frontend/src/lib/tutor/__tests__/`). It colours rows and nothing else.

## Where progress lives, and what else a chapter carries

The record `{done, active}` is a row of the `progress` table, keyed by student and chapter (a foreign
key to `chapters`, deleted with it), written by the section tools in the same request that emits
`section.start` or `section.done`, and read by the chat and voice controllers. The browser receives
it with the chapter (`GET /api/courses/{courseId}/chapters/{chapterId}`), updates its copy from the
events, and resets it through `DELETE …/progress`. Every read of the lesson view repairs the record
against the current curriculum.

Since spec 007 a chapter also carries the student's stored **discussions** — a separate record, in
`conversations`, that no discussion turn can write progress into. The two are independent: resetting
progress leaves conversations alone, and a conversation never moves the path. Details in [accounts-and-courses.md](./accounts-and-courses.md).

## What the interface shows

- **Chapter strip** (`components/celestin/chapter-strip.tsx`), always visible under the tutor header: chapter title, one bar segment per section coloured by state, the active or next section on one line, done count. Tapping it opens the map.
- **Chapter map** (`components/celestin/chapter-map.tsx`), a sheet from the left: every section with its number, kind, state, the active one expanded with its goal; « Revoir » on done rows, « Commencer » on the next one when nothing is active, locked rows inert. Both actions are ordinary learner messages; the tutor does the rest. « Recommencer le chapitre » at the bottom.
- **Transcript markers** for « section commencée », « révision », « section terminée » and « étape suivante proposée ».
- **The page-turn button** under the board, greyed by default. It reads « Étape suivante » once the tutor calls `propose_next_step` (satisfied with the exchange on the current card), or as soon as a `title` card is shown, since a section's opening card has nothing to talk through and « Section suivante » once a section closes, surviving the recap card until the next section starts. Either click is a learner message; only then does the next card or section come. The student turns the page, not the tutor.

`GET /api/courses/{courseId}/chapters/{chapterId}` feeds both with `{id, title, course_id,
course_name, subject, sections: [{id, index, kind, title, goal}], progress}`. Beats, exercise pools
and `done_when` never cross the wire there, and a test scans the whole body for them. The content
view (`…/content`) is the student's own page and does return them.

Nothing in the code knows about sequences, or about any subject beyond its prompt and template files.
