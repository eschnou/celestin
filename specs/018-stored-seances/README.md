# Spec 018 — Stored séances: resume a lesson, reread it (the « cahier »)

No SDD trio, at the owner's request (15 November 2026): this file holds the decisions and the
wire contract. Two user requests, one mechanism:

1. **Resume a lesson where it stopped.** Today the parcours transcript and board live in the
   browser; a reload restarts the section. The brief promises « sessions resume where they stopped ».
2. **Reread past lessons, above all the teacher's boards.** Today « Revoir » has the model teach the
   section again: slow, paid, and not the same boards.

Specs 019 (open path, skip a section) and 020 (révision over a whole course) follow and build on
this one. Product direction behind all three: we assist autonomous, responsible teenagers; we give
tools rather than supervise.

## Decisions

**D1. The server owns the parcours transcript**, as it does a discussion's (spec 007). A parcours
turn posts the learner's *message*, not the history. The record is a `conversations` row with
`mode = 'parcours'`.

**D2. One row per section séance.** A parcours row carries a `section_id`. A row holds the exchange
of one stretch of work on one section, from its `start_section` call to the next `start_section`
of another section. At most one **live** parcours row per student and chapter: the séance the lesson
view is in. Closed rows are final: never reopened, never appended to.

**D3. The split happens when a turn is stored.** The route stores a turn once, when it ends
(as a discussion does), walking the turn's entries `[learner?, *produced]` in order:

- an ok `start_section(Y)` entry while the live row has no `section_id` yet (a fresh row: only a
  greeting so far) **adopts** it: `section_id = Y`, the entry is appended to that row;
- an ok `start_section(Y)` while the live row is already Y's: appended, nothing else;
- an ok `start_section(Y)` while the live row is another section's: the entries before it are
  appended to the live row, which is closed (`done` if it contains an ok `complete_section` of its
  own section, else `left`), and a new live row for Y starts with that entry;
- everything else is appended to the current live row (created on the first stored turn if none).

So the text and the learner message that precede a `start_section` in a turn stay with the section
they were said in, and a section's recap card (shown after `complete_section`, before the next
`start_section`) stays with its section.

**D4. What the model reads** on a parcours turn: the live row's entries, then the learner's message.
Nothing of earlier sections' rows (the pack and the trailing state message carry what it needs;
this replaces today's "whole page-load transcript within the token budget"). `history.trim` still
applies.

**D5. Coming back to a section left unfinished gets a reprise note, not a reopened row.** When
`start_section(X)` is called (or replayed) and X is not done, the brief ends with a note built
from the **closed** non-review rows of X at the current content version: the cards already shown
(kind and title/question, in order). The tutor is told to say in one sentence where they were and
continue after the last card, not start over. Deterministic (closed rows are final), so the replayed
output on later turns is identical. No note for a review, none when there is no such row.
The reload case needs no note: the live row is restored exactly.

**D6. Restore on load.** The lesson reads the live séance before mounting the session and folds its
entries back through the same reducer that built them live (`sessionFromEntries`, extended to the
section tools and `propose_next_step`). Non-empty: no opening turn, a « séance reprise » marker at
the end of the transcript, the board and the page-turn button as they were. Empty or none: the
opening turn, as today. Progress shown is always the server's.

**D7. A turn the learner stops is reported by the browser, as far as it went** (parcours only).
Today the browser keeps an interrupted reply in its history; dropping it would lose boards from the
cahier. When the learner presses stop, the browser reports what it kept of that turn (the message,
the text and the cards received) to `POST /api/seance/report`, the route a spoken turn already
uses, and waits for that report before the next turn is sent. The server stores nothing on its own
when a stream ends early: a provider failure, a network drop or a closed tab leave the séance as it
was, which is exactly what `retry()` assumes when it rolls the browser back and re-sends the
message. (A first version stored abandoned turns server-side from the disconnect; the code review
found it raced the learner's next request and duplicated the message on a retry.) The discussion's
policy is unchanged.

**D8. The cahier.** `GET …/notebook` returns, per section in path order, everything shown and said
in that section's rows (all rows of the current content version, live one included, oldest first).
The page shows the boards, read-only, with the exchange between them behind a toggle. No model
call. « Revoir » with Célestin stays available beside it.

**D9. Lifetime.** « Recommencer le chapitre » deletes the chapter's parcours rows with the progress
(the dialog says the cahier goes too). A content change bumps the version: the live row is closed
`content_changed` lazily, and the cahier only reads rows of the current version (old rows stay
until the chapter or the account is deleted — known, accepted). Rows cascade with chapter and user.

**D10. Caps.** The discussion's caps apply per row (`discussion_max_entries`, `discussion_max_chars`).
A live parcours row that is full is closed `capped` when the next turn opens, and a new row for the
same section starts with a synthetic ok `start_section` entry, so the brief (and the reprise note)
is in front of the model again. Long before a row is full, `history.trim` drops its oldest turns
from the model's input: in the parcours the trim never drops the section's brief — the latest ok
`start_section` entry is carried at the head of what the model reads. The discussion's daily quota
counts discussions only. Reported turns (D7, voice) are the one way to write without a model call:
they are validated (known section ids, cards that are valid board cards, bounded texts), rate
limited per student, and refused once a chapter holds `SEANCE_MAX_ROWS` rows (default 200).

**D11. Two tabs.** A second tab on the same chapter writes to the same live row; the optimistic
`expected_count` guard turns simultaneous turns into `409 conversation_busy`. Accepted.

## Data

Migration `0012`:

- `conversations.section_id` `String(40)`, nullable (always null for a discussion).
- `conversations.card_count` `Integer`, default 0: `display_board` entries in the row, maintained
  on append (so the chapter view can say which sections have notes without parsing transcripts).
- `ck_conversations_mode`: `mode in ('discussion','parcours')`.
- `uq_conversations_live` becomes unique on `(user_id, chapter_id, mode) where state = 'live'`.
- closed reasons gain `done` and `left`.

`ToolEntry` gains an optional `review: bool | None` (only set on `start_section` entries): what the
call was at the time, like `ok`. It is never sent to the model.

Every repository method that reads or counts conversations takes the mode; the discussion's
behaviour and wire are unchanged.

## Wire contract

All routes: the student who owns the course (404 otherwise), `409 chapter_not_ready` without content.

### `POST /api/chat` (changed)

```jsonc
{ "course_id": "…", "chapter_id": "…", "message": "…" | null }
```

SSE, the same events. `message: null` is the opening turn, accepted only while there is no live
séance or it is empty (`422 empty_conversation_expected`). `history` is gone.

### `GET /api/courses/{c}/chapters/{ch}/seance`

```jsonc
{ "seance": null | { "id": "…", "section_id": "sa-somme" | null, "entries": [ StoredEntry, … ] },
  "progress": { "done": ["…"], "active": "…" | null },     // read in the same handler as the séance
  "seances": { "<section_id>": { "cards": 7 } } }
```

A pure read (apart from the lazy `content_changed` close). `progress` and `seances` travel with the
séance so the lesson starts from one consistent read: `seances` has one key per section that has at
least one parcours row at the current content version, with its stored card count (what the map
needs to offer « Relire »). `StoredEntry` is the discussion's, with
the section tools readable:

```jsonc
{ "kind": "learner" | "tutor", "text": "…" }
{ "kind": "tool", "name": "display_board", "arguments": { "card": {…} }, "marker": "…" }
{ "kind": "tool", "name": "clear_board", "arguments": {}, "marker": "…" }
{ "kind": "tool", "name": "start_section", "arguments": { "section_id": "…" }, "review": false, "marker": "…" }
{ "kind": "tool", "name": "complete_section", "arguments": { "section_id": "…" },
  "next_section_id": "…" | null, "marker": "…" }      // next: from the *current* progress
{ "kind": "tool", "name": "propose_next_step", "arguments": {}, "marker": "…" }
```

Markers are rendered in the account's interface language, from the same function the live tool builds its
marker with (one source per tool). A discussion's stored entries are the same DTO.
Entries with `ok: false` are not returned (the browser never recorded them either).

### `POST /api/seance/report` → 204

```jsonc
{ "course_id": "…", "chapter_id": "…", "entries": [ Entry, … ] }   // 1..32
```

A parcours turn the browser reports: a spoken one (same deviation as 007 D1), or one the learner
stopped (D7). Stored with the split rule of D3. `start_section` entries may carry `review`.
`422` for an entry that does not validate (unknown `section_id`, a `display_board` whose card is not
a valid board card, a text over the limit), `429 seance_report_rate`, `409 seance_full` at the row cap.

### `POST /api/voice/session` (changed)

`history` is gone from the request for every mode: a parcours session is seeded from the stored
live séance, a discussion from its conversation (as today).

### `GET /api/courses/{c}/chapters/{ch}/notebook`

```jsonc
{ "sections": [
    { "section_id": "sa-somme",
      "items": [ { "kind": "card", "card": {…} }
               | { "kind": "tutor" | "learner", "text": "…" } ] } ] }
```

Sections in path order; only sections with at least one item. Beats, exercise pools and `done_when`
never cross this wire (the existing leak test covers the body).

### `DELETE /api/courses/{c}/chapters/{ch}/progress` (extended)

Also deletes the student's parcours rows of that chapter, in the same transaction.

## Interface

- **Lesson**: loads the séance, restores it (D6). The parcours transport posts the message.
- **Chapter map**: a « Relire » action on every row whose section has stored cards (`seances`, beside
  « Revoir » on done rows), leading to the cahier at that section.
- **Chapter bar**: a « Cahier » link, in the lesson and in a discussion.
- **`/courses/$courseId/chapters/$chapterId/notebook`**: the cahier. Sections in order, each with its
  title and its boards rendered by the board's own components, read-only (no answer widget wired, no
  page-turn button); `title` cards are not repeated (the section heading says it). A toggle shows the
  exchange between the boards. An empty state when nothing is stored yet. Back to the lesson.
- **Voice**: parcours spoken turns are reported to `/api/seance/report`.
- **Stop**: a stopped turn is reported there too, and the next send waits for the report (D7).
- « Recommencer le chapitre » says the cahier is erased too.
- Copy in French, English and Dutch (interface catalogs). The cahier's content is in the course's
  language and rendered under the course-language provider, like the lesson's board.

## Invariants touched

- *No answer while an exercise is open*: the cahier only shows cards that were already shown, as
  they were shown.
- *Privacy*: every new route goes through `owned_chapter`/`lesson_chapter`; logs carry ids and
  counts, never content.
- *Model input wall*: stored entries are rendered for the browser at the edge (markers in the
  interface language); what the model reads takes the course language only.
- The cached prefix does not move in this spec (no prompt or declaration change), except the
  reprise note, which lives in a tool output after the breakpoint.
