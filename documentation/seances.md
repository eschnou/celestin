# Stored séances and the cahier

Spec 018 gives the parcours what the discussion already had (`discussion.md`): the server owns its
transcript. A lesson resumes where it stopped after a reload, and the student can reread what was
shown, above all the boards, in a « cahier » that costs no model call. The decisions are archived in
`specs/018-stored-seances/README.md` (D1–D11); this page says how the built system works.

Nothing here is a second tutor. The same turn loop, the same SSE events, the same board and the
same reducer; what changed is who holds the record and what a turn posts.

| What | Before spec 018 | Since |
|---|---|---|
| Who owns the parcours transcript | the browser, posted back whole on every turn | the server: `conversations` rows with `mode = 'parcours'` |
| What `POST /api/chat` carries | `{course_id, chapter_id, history}` | `{course_id, chapter_id, message}` |
| What the model reads on a turn | the page-load transcript within the token budget | the live séance's entries, then the message |
| A reload | a fresh opening turn | the séance restored as it was |
| « Revoir » | Célestin teaches the section again | still there; the cahier sits beside it |

## The rows

A séance is a `conversations` row, the table a discussion uses (migration `0012`):

```jsonc
// conversations, mode = 'parcours'
{
  "id": "…", "user_id": "…", "chapter_id": "…",   // both ON DELETE CASCADE
  "mode": "parcours",           // 'discussion' | 'parcours' (ck_conversations_mode)
  "section_id": "sa-somme",     // null until its first start_section; always null for a discussion
  "content_version": 3,         // the chapter version it was held against
  "entries": [ … ],             // the transcript, in the DTO shapes a turn already uses
  "entry_count": 12, "char_count": 4210,
  "card_count": 4,              // display_board entries, kept on every append
  "state": "live",              // live | closed
  "closed_reason": null         // done | left | capped | content_changed (a discussion: replaced | capped | content_changed)
}
```

- **One live row per student, chapter and mode**: the partial unique index `uq_conversations_live`
  is on `(user_id, chapter_id, mode) where state = 'live'`, so a live discussion and a live séance
  coexist on the same chapter.
- **One row per section séance** (D2): a row holds one stretch of work on one section, from its
  `start_section` to the next `start_section` of another section. Closed rows are final: never
  reopened, never appended to.
- **Every repository read names its mode** (`live`, `get_owned`, `started_since` take `mode=`), so a
  discussion never sees a séance and a séance never sees a discussion. The discussion's daily quota
  counts discussions only.
- `ToolEntry` has an optional `review` (on `start_section` entries only, refused elsewhere): what
  the call was at the time, like `ok`. `history.to_provider_input` reads the name and the arguments
  only, so it never reaches the model. A stored row leaves `review` out when it is not set, so a
  discussion's rows keep the bytes they always had (`chat.stored_form`).
- `card_count` is kept on every write, so the lesson can say which sections have notes with one SQL
  aggregate (`card_counts`), without parsing a transcript. The service counts the cards of what it
  writes (`conversations.card_count`, the one predicate of « a card shown », `card_of`) and hands the
  number to the repository with each `SeanceSegment`: the repository adds numbers and knows no tool.

The code: `app/services/seance.py` (`SeanceService`, `split`, `earlier_cards`), sharing
`app/services/conversations.py` with `discussion.py` (`entries_from_events`, `stored_entries` — the
one place a stored row is parsed —, `card_of`/`card_count`, `is_full`, `opening`, `payload`,
`live_row`); every séance write is `ConversationRepository.store_seance`, which returns ids and
counts (`StoredSeance`), not records.

## A turn

```
POST /api/chat {course_id, chapter_id, message}
  open_lesson                      ownership, content, progress, the context (save, earlier_cards)
  SeanceService.open_turn          the live séance (rolled over first if full), then the message
  TutorService.build_input         the four prompt layers, the séance's entries + message, the state message
  stream the turn                  the same SSE events
  on turn.end:   store             [learner?, *produced], cut by the split rule, one transaction
  ended early:   nothing           a failure, a dropped connection, a stop: the server stores nothing

on stop, in the browser:
POST /api/seance/report {course_id, chapter_id, entries}   what she kept of the turn, same split rule
  …and only then the next POST /api/chat
```

**What the model reads** (D4): the live row's entries, then the learner's message. Nothing of
earlier séances: the pack and the trailing state message carry what it needs. `history.trim` still
applies, with `HISTORY_TOKEN_BUDGET`, and in the parcours it never drops the section's brief (see
« Caps »).

**The opening turn** is `message: null`, accepted only while there is no live séance or it is empty;
otherwise `422 empty_conversation_expected` (worded « Cette séance a déjà commencé. », key
`seance_started`): the lesson restores a séance that holds something instead of greeting again. The
rule is the discussion's, written once (`conversations.opening`), each mode raising its own error.

`open_turn` returns the turn and what the model reads separately: once the input is built, the
streamed turn keeps only the live row's id, entry count and section, whether that row already holds
its section's completion (decided from the entries parsed for the input), and the learner's entry.

### The split rule

The route stores a turn once (D3), walking its entries `[learner?, *produced]` in order
(`seance.split`):

- an ok `start_section(Y)` while the live row has no `section_id` yet (only a greeting so far)
  **adopts** it: `section_id = Y`, and the entry goes to that row;
- an ok `start_section(Y)` while the live row is already Y's: appended, nothing else;
- an ok `start_section(Y)` while the live row is another section's: the entries before it go to the
  live row, which is closed `done` if it holds an ok `complete_section` of its own section, else
  `left`; a new live row for Y starts with that entry;
- everything else goes to the current live row, created on the first stored turn if there is none.

So the learner's message and the text said before a `start_section` stay with the section they
were said in, and a section's recap card (shown after `complete_section`, before the next
`start_section`) stays with its section. A refused call produces no entry and never splits.

A `skip_section` (spec 019) never splits either: skipping the live row's section leaves the row live
(the skip is one of its entries) until the next `start_section` of another section, which closes it
`left` (a skip is not a completion). Starting a section that was skipped un-skips it, and if it had
closed, non-review séances its brief ends with the reprise note like any section taken up again.
Leaving a section for another (spec 019 D4) is the same `left` close.

The whole cut lands in one transaction. The live row is guarded by the optimistic `expected_count`
(as a discussion's append is), and a second live row inserted by another tab trips the unique index:
both are `409 conversation_busy` (key `seance_busy`, D11), an in-stream `error` event once the stream
is open.

### Stopped, cancelled and failed turns

- **A turn that reached `turn.end`** (`end` or `max_rounds`) is stored by `on_complete`, before
  `turn.end` reaches the browser, so a failure to store is still an `error` event she sees. It is
  the only store hook `app/api/sse.py` has, in either mode.
- **A stream that ends early stores nothing** on the server, whatever ended it: a provider failure,
  a dropped connection, a closed tab, a stop. That is what the browser's `retry()` assumes when it
  rolls a failed turn back and sends the same message again, and an opening turn that failed can
  be sent again as an opening turn (`message: null`, not `422 seance_started`).
- **A turn the learner stops is reported by the browser** (D7, amended after review). The browser
  keeps an interrupted reply on screen, so dropping it would lose boards from the cahier. When she
  presses stop, `useTutorSession.cancel()` posts what the session's `history` gained since the turn
  began (her message, the text blocks and the tool entries received so far, after
  `markInterrupted`) to `POST /api/seance/report`, the route a spoken turn uses, and the next turn,
  a retry or « Recommencer le chapitre » waits for that report before it is sent: the server stores
  the two in the order she did them. A failed report is swallowed (the partial turn is then not
  stored); an error, a network drop or leaving the page report nothing. Frames already parsed when
  she pressed stop are not applied, so the report holds exactly what she saw.
- **The discussion's policy is unchanged**: a complete turn or nothing, and it does not report a
  stopped turn (its session has its own transport and no reporter).

Why not store from the server when the stream ends: a first version did (an `on_abandon` hook
running in a detached task). The review found it raced everything after it: the same student's
next request could be refused `seance_busy` after its reply was shown, a reset or a reload during
the opening turn could bring old content back, and `retry()` re-sent a message the séance already
held. A report the browser sends, and waits for, has none of these.

What is still possible: a tool that ran on the server after the browser stopped listening (the
section tools commit progress as they run) is not in the report, since its event never arrived; the
progress then says more than the séance, and the next turn's state message carries it. And a stop
pressed in the instant between the server storing a complete turn and `turn.end` reaching the
browser reports part of that turn a second time.

## Restore

`GET /api/courses/{c}/chapters/{ch}/seance` returns the live séance or `null`, with what the lesson
starts from, read in the same handler:

```jsonc
{ "seance": null | { "id": "…", "section_id": "sa-somme" | null, "entries": [ StoredEntry, … ] },
  "progress": { "done": ["…"], "active": "…" | null },   // repaired, as a turn sees it
  "seances": { "<section_id>": { "cards": 7 } } }          // SeanceService.card_counts
```

A pure read apart from the lazy `content_changed` close: a full séance is returned as it is and
rolls over on the next turn. The lesson folds the entries back through the reducer that built them
live (D6); non-empty means no opening turn. `seances` has one key per section with at least one
séance at the current content version, with its stored card count (zero is a key): what the map
needs to offer « Relire ». The chapter view does not carry it.

Each entry is the discussion's `StoredEntry` (`app/api/schemas/discussion.py`), one DTO for both
modes:

```jsonc
{ "kind": "learner" | "tutor", "text": "…", "name": null, "arguments": null, "marker": null }
{ "kind": "tool", "name": "display_board", "arguments": { "card": {…} }, "marker": "explication affichée", "text": null }
{ "kind": "tool", "name": "clear_board", "arguments": {}, "marker": "tableau effacé", "text": null }
{ "kind": "tool", "name": "start_section", "arguments": { "section_id": "…" }, "review": false,
  "marker": "section commencée · 1. Suites numériques", "text": null }
{ "kind": "tool", "name": "complete_section", "arguments": { "section_id": "…" },
  "next_section_id": "…" | null, "marker": "section terminée · 1. Suites numériques", "text": null }
{ "kind": "tool", "name": "propose_next_step", "arguments": {}, "marker": "étape suivante proposée", "text": null }
{ "kind": "tool", "name": "skip_section", "arguments": { "section_id": "…" },
  "next_section_id": "…" | null, "active_section_id": "…" | null,
  "marker": "section passée · 1. Suites numériques", "text": null }
```

- **What a stored call shows is the tool's to say.** Each row of the registry (`_TOOLS` in
  `services/tools/registry.py`) has, beside `replay`, a `shown` hook owned by the tool's module
  (`shown_display`, `shown_clear`, `shown_start`, `shown_complete`, `shown_propose`, `shown_skip`): it returns a
  `Shown`, the `Marker` the live call carried — built by the same function the live handler uses
  (the card's own `marker`, `CLEAR_MARKER`, `_start_marker`, `_done_marker`, `STEP_READY`) — and the
  extra wire fields of that entry. `app/api/stored.py`'s `stored_entry(entry, locale, mode, view)`
  asks `registry.shown` and hands the marker and the fields to `StoredEntry.of`, which renders the
  marker in the account's interface language (the wire schemas import no service:
  `test_layering.py`); a tool the mode does not offer shows nothing more than its call, so a
  discussion's entries keep their shape. Adding a tool is its row and its module: no DTO edit.
- Whether a `start_section` was a review is decided by one rule, `section.recorded_review`: the
  stored `review` when it is set, else the progress now. The restored transcript and the replayed
  brief both read it, so they cannot disagree. A reported start without `review` gets it at report
  time, from the progress then.
- `review` is on a `start_section` entry only, `next_section_id` on a `complete_section` or
  `skip_section` entry only, `active_section_id` on a `skip_section` entry only (extra keys,
  `extra="allow"`). Shown, they say where the page turns **now**, from the current progress
  (`StoredView`), by the one rule the live events use, `path.page_turn`: `next_section_id` is `null`
  while a section is active, else the next section of the path, `null` too once the chapter is
  finished; a skip's `active_section_id` is the section active now. Every restored entry reads the
  same progress, so the button they leave lit proposes something valid today (spec 019: a completion
  read back while another section is active no longer names that section; it proposes nothing, as
  the live event would).
- **What the model is told again is what the call answered** (spec 019). A stored `complete_section`
  or `skip_section` *records* what its event said (`ToolEntry.next_section_id`, and for a skip
  `active_section_id`; written by `entries_from_events`, or reported by the browser from the event, as
  `review` is; never sent to the model as arguments). Recorded means present: `stored_form` keeps an
  explicit `null` (« the chapter was finished »), and leaves the keys out when nothing was recorded, so
  every other entry keeps its bytes. The `replay` hooks rebuild the live text from those ids
  (`curriculum_render.completion` / `skipped` take sections, not a progress), whatever the progress
  became since: a skip that said « Prochaine section : Exercices » says it again after the student
  took the skipped section up in the same séance, and the cached history does not move. An entry
  that recorded nothing, or names a section the curriculum no longer has, is answered from the
  progress now, as before.
- The section's label comes from the current curriculum (its id when it is gone).
- Entries with `ok: false` are not returned (the browser never recorded them either). The séance
  carries no `entry_count`: the stored count includes them.

## The reprise note

Coming back to a section left unfinished gets a note, not a reopened row (D5). When
`start_section(X)` runs, or is replayed on a later turn, and X is not done, the brief ends with a
note built from the **closed, non-review** séances of X at the current content version: the cards
already shown, in order, and an instruction to say in one sentence where they were and continue
after the last card rather than start over.

```
Section « 1. Suites numériques » (leçon), 1/7.
…
Terminée quand : …

Reprise : cette section a déjà été travaillée lors d'une séance précédente. Cartes déjà montrées, dans l'ordre :
- explication : Somme d'une SG
- question de compréhension : Quel est le premier terme ?
Dis en une phrase à ton élève où vous en étiez, puis continue après la dernière carte, sans reprendre la section depuis le début.
```

- One line per card: the kind as the note names it, then the card's title (the question for a check
  question; a recap has neither). The last 20 cards (`REPRISE_MAX_CARDS`), with a line counting the
  older ones.
- Model-facing text, so it takes the course language and never the interface's:
  `curriculum_render.REPRISE`, a `by_language` table (French, English, Dutch as written in Flanders).
- The handler reads the cards through `TurnContext.earlier_cards`, which `deps.load_context` binds
  for the parcours (like `save`) to `seance.card_loader`: one lookup per section per turn. `None` in
  unit tests and scripts means no note.
- The lookup is cheap: a query of ids first (the section's closed rows at this content version that
  hold a card: `ConversationRepository.closed_seance_ids`), then a small process-wide LRU keyed by
  that tuple of ids (`_CardCache`, 256 sets). Closed rows are final, so a set of ids always lists the
  same cards: the transcripts are read and parsed once (`seances_by_id`), not on every turn that
  replays the brief. A voice session's seed, which replays the brief too, is built off the event
  loop (`VoiceService.create_session`, `asyncio.to_thread`).
- A séance counts as a review when its first ok `start_section` of its own section says
  `review: true`.
- Deterministic: closed rows are final, and the replay reads what the call was at the time — its
  stored `review` (today's progress only for an entry recorded without one), which also decides the
  note — so the replayed output on later turns is the same, byte for byte, even once the section has
  been completed inside the live séance. No note for a review, none without such a séance: the
  brief is then what it always was. The reload case needs none: the live row is restored exactly.
- It lives in a tool output, after the cache breakpoint: the cached prefix does not move.

## Caps

The discussion's caps apply per row: `DISCUSSION_MAX_ENTRIES` (400) and `DISCUSSION_MAX_CHARS`
(200 000). A séance is never closed by the write that fills it (the answer she is reading stays on
screen and in the restore). When the next turn opens — a text turn, a voice session, a reported
spoken turn — a full live séance is closed `capped` and the next row of the same section starts
with a synthetic ok `start_section` entry, so the brief and the reprise note are in front of the
model again (D10; `SeanceService.current`). The synthetic entry is written only when it tells the
truth (`_carried_on`): the row's section is the active one (`review: false`), or the row was opened as
a review of a done section (`review: true`). A section skipped, completed or otherwise no longer
worked in the full row gets none: the next row starts unsectioned and empty, and adopts the section
of the next `start_section`, as a fresh row does (the restored transcript never shows a « section
commencée » that did not happen). The rollover is one `store_seance` with two segments: the full row,
no entries, closed `capped`, then the new row with its synthetic entry, or none; the same guard, one
transaction, `409 conversation_busy` on a race.
`conversations.is_full` is the one test of « full », for both modes.

**The brief survives the trim.** Long before a row is full, `history.trim` starts dropping its
oldest turns from what the model reads (about `HISTORY_TOKEN_BUDGET` × 3.2 characters in French,
some 96 000), and the oldest turn holds the `start_section` call whose replayed output is the brief.
Since a séance outlives a reload, a long section would lose its beats, its end criterion and its
reprise note. So in the parcours (`trim(…, keep_brief=True)`, from `to_provider_input` when
`ctx.mode == "parcours"`) the latest ok `start_section` among the dropped turns is carried at the
head of what is kept, replayed as usual (its `function_call` and `function_call_output`), unless what
is kept already holds one. The total stays within the budget plus that one call; a discussion's
input and the byte-stable fixtures do not change.

**Reported turns are bounded** (D10). `POST /api/seance/report` is the one write without a model
call, so:

- every entry is validated (`ReportedTurn`, shared with the discussion's `/api/discussion/voice/turn`,
  whose wire does not change): a text at most `REPORTED_TEXT_MAX` (20 000) characters, a tool call's
  arguments at most `REPORTED_ARGUMENTS_MAX` (40 000) characters of JSON, and a `display_board` card
  must be a valid board card (the cahier draws it); `422` otherwise. The limits and why they are
  generous for a real turn are in `api/schemas/chat.py`;
- every `start_section`, `complete_section` and `skip_section` must name a section of the chapter, and
  so must the sections a completion or a skip recorded (`next_section_id`, `active_section_id`, when not
  null); only the tools the parcours offers are accepted: `422 seance_report_invalid` otherwise (nothing
  of the report is stored). Each tool says what it checks with the `check` hook of its registry row
  (`check_start`, `check_section`), beside `replay` and `shown`; a reported start without `review`
  gets it there;
- per student, `SEANCE_REPORTS_PER_HOUR` (600) reports an hour: `429 seance_report_rate`;
- a chapter that already holds `SEANCE_MAX_ROWS` (200) parcours rows for the student, every content
  version counted, refuses the report: `409 seance_full`. Model turns are not subject to it (they
  cost a model call, and a refusal there would stop the lesson); « Recommencer le chapitre » deletes
  the rows.

## The cahier

`GET /api/courses/{c}/chapters/{ch}/notebook` (D8): per section in path order, everything shown and
said in that section's séances — all rows of the current content version, live one included, oldest
first. No model call.

```jsonc
{ "sections": [
    { "section_id": "sa-somme",
      "items": [ { "kind": "card", "card": {…} } | { "kind": "tutor" | "learner", "text": "…" } ] } ] }
```

Only sections with at least one item; a row with no section (a greeting before any section) belongs
to none; refused calls are left out. Every card is returned, `title` cards included (the page does
not repeat them). Beats, exercise pools and `done_when` never cross this wire. The service returns
its own shape (`NotebookSection` and `NotebookItem` dataclasses in `services/seance.py`), which the
route reads into the response DTO in one step (`from_attributes`).

## Lifetime

- **« Recommencer le chapitre »** (`DELETE …/progress`) deletes the progress and the student's
  parcours rows of that chapter in one transaction (`ProgressRepository.reset`); her discussions
  stay. The cahier goes with it.
- **A content change** bumps the chapter version: the live séance is closed `content_changed`
  lazily (on the next read), and the cahier and the card counts read rows of the current version
  only. Older rows stay until the chapter or the account is deleted — known, accepted (D9).
- Rows cascade with the chapter and with the user.

## Voice

- `POST /api/voice/session` takes no `history` in either mode any more: a parcours session is seeded
  from the séance its next turn continues (`SeanceService.seed`, which rolls a full one over), a
  discussion from its conversation. `opening` is true when that séance is empty or absent.
- A spoken turn reaches the browser over WebRTC and never the server, so the browser reports it:
  `POST /api/seance/report {course_id, chapter_id, entries}` (1 to 32 entries) → `204`, stored with
  the split rule, the route a stopped text turn uses too. `start_section` entries may carry `review`.
  Same deviation as 007 D1: a student can write entries into her own séance only, and the entries
  are checked and bounded (« Caps »).
- `/api/voice/tool` runs `start_section` with the context `open_lesson` binds, so a spoken
  `start_section` ends with the reprise note too.

## Routes

| Route | Body | Answer |
|---|---|---|
| `POST /api/chat` | `{course_id, chapter_id, message}` (`message: null` opens) | SSE, the same events; `422 empty_conversation_expected` |
| `GET /api/courses/{c}/chapters/{ch}/seance` | — | `{seance, progress, seances}` (`seance` may be `null`) |
| `GET /api/courses/{c}/chapters/{ch}/notebook` | — | `{sections}` |
| `POST /api/seance/report` | `{course_id, chapter_id, entries}` (1 to 32) | `204`; `422`, `422 seance_report_invalid`, `429 seance_report_rate`, `409 seance_full` |
| `DELETE /api/courses/{c}/chapters/{ch}/progress` | — | `204`, the séances gone too |

All of them: the student who owns the course (`404` otherwise, never `403`), `409 chapter_not_ready`
without content (the routes go through `lesson_chapter`). A request that still posts `history` is
`422`.

## Log lines

Ids and counts only, never content (`test_seance_logs_carry_ids_and_counts_never_content` sweeps
them with a marker string in the message and on a card):

| Line | Carries |
|---|---|
| `seance_stored` | user, chapter, live row id and section, entries added, rows written, the reasons of those closed, entry and card counts |
| `seance_store_failed` | row id, chapter, entries added, the error's class |
| `seance_capped` | old and new row ids, chapter, section, entry and character counts |
| `seance_closed` | row id, chapter, reason `content_changed` |
| `seance_reported` | user, chapter, entries reported, rows written |
| `seance_report_refused` | chapter, the entry's index, the reason (`section` or `tool`) |
| `seance_full` | user, chapter, rows held |
| `seance_notebook` | user, chapter, rows read, sections and items returned |
| `history_brief_kept` | entries kept beside the carried brief |
| `progress_reset` | user, chapter, and now `seances`: how many rows went |

## The interface

- **Resuming a lesson.** The lesson screen (`lesson.tsx`) does not mount the session until it has
  read `lessonStartQuery`: one `GET …/seance`, which carries the live séance, the progress and the
  stored card count per section (`seances`), read by the server in one handler; once per mount
  (`staleTime: Infinity`, `gcTime: 0`), started by the chapter route's loader beside the chapter
  view rather than behind it. The route's own chapter view is cached for a
  few seconds, so starting from its progress could pair a fresh séance with a stale progress; the
  progress the session starts from is always the one read with the séance. While the read runs the
  screen says « Chargement du parcours… »; a failure shows the server's message and « Réessayer ».
- A non-empty séance is folded back through `sessionFromEntries` and gets a « séance reprise »
  marker at the end of the transcript; the board, its history strip and the page-turn button are as
  they were, and no opening turn is sent. An empty or missing séance opens with the opening turn
  (`message: null`). The progress the replay computes is discarded: the hook starts from the
  server's.
- **A turn posts the message.** `streamTurn` posts `{course_id, chapter_id, message}` to
  `/api/chat`; `retry()` re-sends the same message after rolling the failed turn back (the server
  stored nothing of it).
- **Stop.** `cancel()` reports what the stopped turn kept to `/api/seance/report` (the option
  `report` of `useTutorSession`, defaulting with the parcours transport to `reportTurn`), and the
  hook holds the next turn, a retry or a reset behind that report (`pendingReportRef`, null once it
  settles). A session with its own transport (the discussion) reports nothing.
- **Voice.** The session request carries no transcript in any mode. A spoken parcours turn is
  reported to `/api/seance/report` with `{course_id, chapter_id, entries}`, through the same
  code path and batching as a discussion's and as a stop (`reportTurn` in `voice/client.ts`, the
  route chosen by `scope.mode`); a `start_section` entry carries `review`.
- **The cahier** (`/courses/$courseId/chapters/$chapterId/notebook`, `components/celestin/notebook.tsx`)
  reads `GET …/notebook` and the chapter view. Sections follow the path, each headed by its number,
  kind and title; every card except `title` is drawn by the board's own `CardView` in reading mode:
  no answer widget is wired, there is no page-turn button and no history strip, a worked example
  shows all its steps, and a check question reveals its right option and feedback once an option is
  picked. « Afficher les échanges » shows the tutor's and the learner's lines between the cards,
  rendered by the transcript's `Entry`. A `#<section_id>` hash scrolls to that section. With nothing
  stored the page says so. The content is under the course-language provider; the chrome is in the
  interface language, and the bar, the back link and the toggle are hidden in print.
- **Entry points.** The chapter map offers « Relire », a link to the cahier at the section, on every
  row whose section has stored cards (`seances[id].cards > 0` in the `GET …/seance` reply) or has had a card shown on the
  board this page load; done rows keep « Revoir ». The chapter bar has a « Cahier » link, in the
  lesson and in a discussion (in the `⋯` menu on a phone). « Recommencer le chapitre » says the
  cahier is erased too; after a saved reset the session starts empty with the opening turn and no
  row offers « Relire ».

Frontend seams: `sessionFromEntries` serves both modes and now replays `start_section` (with
`review`), `complete_section` (with `next_section_id`), `skip_section` (with both ids: the
page-turn button is left as it is while `active_section_id` names a section, otherwise it proposes
`next_section_id` or goes out) and `propose_next_step`; a learner entry is
followed by a `turn.start`, as it is live, so a proposed step is put out exactly as it was. The
session's `history` is no longer posted on a text turn; it remains the model-facing view a spoken
or a stopped turn reports. `state.section` is the section the board belongs to. `CardView` is the one pure card
renderer the board and the cahier share. `lib/tutor/seance.ts` holds `lessonStartQuery`,
`notebookQuery` and `SEANCE_REPORT_URL`. `useTutorSession().resetProgress()` resolves to whether the
reset was saved.

Checked in a browser against the real model on 15 November 2026 (a scratch database, the seeded
chapter): the opening turn, a step, a reload (transcript, board, strip and page-turn button back,
« séance reprise »), an answer after the reload (Célestin continues from the stored exchange), the
cahier, and a turn stopped mid-stream under uvicorn: the browser's report answers 204, and after a
reload the learner's message, the card shown and the text received before the stop are back.

## Tests

`tests/unit/test_seance_service.py` (the split rule in every branch, what the model reads, the
opening refusal, busy, the rollover, the reprise cards, the notebook, versions, reset, coexistence,
the quota, the reprise cards read once per set of rows, the reported turn's checks and the row cap),
`tests/unit/test_reprise_note.py` (the note per language, the cap, byte identity without it and on
replay, no note for a review), `tests/unit/test_history.py` (a long parcours row still starts with
the brief, within the budget plus that call; a discussion carries none),
`tests/unit/test_chat_stream_mechanics.py` (one store hook: a completed turn stored once; failed,
disconnected and cancelled turns store nothing), `tests/unit/test_discussion_schema.py` (the restored
review and the replay agree), `tests/unit/test_layering.py` (no wire schema imports a service),
`tests/integration/test_seance_endpoint.py` (the routes end to end, the DTO shapes, failed and
dropped turns storing nothing and retried once, a stopped turn reported then followed, the report's
validation, rate limit and row cap, the discussion's spoken turn checked the same way, ownership,
readiness, the leak and log sweeps, the voice seed), and `test_migrations.py` (0012 up and down with
data). In the browser, `use-tutor-session-hook.test.tsx` covers the stop: the report holds exactly
the turn's entries and the next turn's POST waits for it, a failed report does not block, a reset
waits too, a network failure is retried with the same message and no report, an opening turn that
failed is retried as an opening turn, a discussion reports nothing. The migration was checked on SQLite by the tests and rendered for PostgreSQL offline
(`alembic upgrade 0011:0012 --sql`); it has not been run against a PostgreSQL server.

## Manual checklist

1. Open a ready chapter: Célestin greets once. Start the first section, see a card, reload: the
   transcript, the board and the page-turn button are as they were, and no second greeting.
2. Stop a reply after a card is shown, then send another message at once: the next reply comes after
   the stopped one in the transcript, and after a reload the card is there and both turns are stored
   once. Close the tab mid-reply instead and reopen: that turn is not there (nothing was reported),
   and sending the same message again works.
3. Finish a section and start the next: `select section_id, state, closed_reason from conversations
   where mode = 'parcours'` shows the first row `done` and the next one `live`.
4. Leave a section half done for a review of an earlier one, then come back: Célestin says in one
   sentence where you were and continues after the last card.
5. Open the cahier: the sections in path order, their boards read-only, the exchange behind the
   toggle.
6. Open a discussion on the same chapter while the séance is live: both are restored independently.
7. « Recommencer le chapitre »: the progress, the séances and the cahier are gone; the discussion is
   still there.
8. Edit the chapter's pack: the next open starts a fresh séance and the cahier is empty.
