# Spec 019 — The open path: any section, in any order, and « passer »

No SDD trio, at the owner's request (15 November 2026): this file holds the decisions and the
contract. Builds on spec 018 (stored séances).

The user request: skip a lesson — « pratique si on a déjà vu en classe et on veut faire une leçon
précise ». The owner's decision: **the path is entirely open**. The product direction: we assist
autonomous, responsible teenagers; the path is the order Célestin proposes, not a lock.

What does not change: correctness and withholding rules, the pack as only source, one section
worked at a time, a section is finished only by `complete_section` on its criterion.

## Decisions

**D1. No section is ever locked.** `start_section` accepts any section of the chapter. The path
order remains the order Célestin proposes: « the next section » is the first one, in path order,
that is neither done, skipped nor active.

**D2. A third recorded state: `skipped` (« passée »).** Distinct from done, so progress stays
honest: Célestin knows he did not teach it, the map shows it apart, révision (spec 020) can target
it. A skipped section is never proposed as the next one. It stays open: starting it un-skips it.

**D3. Skipping goes through a tool, `skip_section`,** like every other change to the path. The map's
« Passer » button sends an ordinary learner sentence, exactly as « Commencer » and « Revoir » do; the
student can also just say it (« celle-là je l'ai vue en classe »), and it works in a voice session.
Only the student decides: the prompt forbids Célestin to skip on his own initiative, to ask for a
justification or to make the student pass a test first.

**D4. Leaving a section for another parks it.** `start_section(Y)` while X is active makes Y the
active section; X is simply no longer active (not done, not skipped). Its séance row is closed
`left` by spec 018's split, and coming back to X gets the reprise note (018 D5). At most one
active section, as before.

**D5. A chapter is finished when every section is done or skipped.** Counts shown to the student
keep the two apart (« 7 faites · 2 passées »).

**D6. `complete_section` is unchanged**: the active section only. A review (`start_section` on a
done section) is unchanged and changes no progress.

## Progress and path rules

`Progress = {done, active, skipped}`. Migration `0013`: `progress.skipped` JSON, default `[]`.
Normalisation repairs as before: unknown ids dropped; an id both done and skipped is done; an
active that is done or skipped is cleared… except that starting a skipped section un-skips it
(the tool does that, normalisation never sees it).

Section states (`services/path.py`, mirrored display-only in `frontend/src/lib/tutor/path.ts`,
both tested against the shared `path_cases.json`, rewritten for these rules — the lead wrote
`backend/tests/fixtures/path_cases.json`; the frontend keeps its prettier-formatted copy; each case
also pins `next`, the first section that is neither done, skipped nor active):

| State | Rule |
|---|---|
| `done` | in `progress.done` |
| `active` | `progress.active` |
| `skipped` | in `progress.skipped` |
| `available` | the first section, in path order, that is none of the above, **only when nothing is active**: the one Célestin proposes |
| `open` | every other section (replaces `locked`) |

Transitions, enforced in the tools:

| Call | Refused when | Effect |
|---|---|---|
| `start_section(id)` | unknown id | done section: a review, nothing changes. Otherwise `active = id`, and `id` leaves `skipped`. |
| `complete_section(id, summary)` | not the active section | `done += id`, `active = None` |
| `skip_section(id)` | unknown id; section already done | `skipped += id`; `active = None` if it was the active one. Idempotent on an already skipped section. |

`skip_section` answers with what comes next (the same text `complete_section` answers with), so the
tutor can say it in one sentence: the section still being worked, else the next one of the path, else
« Chapitre terminé : toutes les sections sont faites ou passées. » (the skipped sections are named by the
state message, every turn, not in the tool's answer, which is replayed from its record).

**The page-turn rule**, one function, `path.page_turn(curriculum, progress)`: None while a section is
active (skipping another section does not turn the page of the one being worked), else the next
section of the path (None when the chapter is finished). The live `section.done` and
`section.skipped` events and both restored entries (`shown` hooks) read it.

## Tool, event, stored entry

- **Sixth tool**, declared last (after `propose_next_step`) so the declarations before it keep their
  bytes: `skip_section(section_id)`, strict. `start_section`'s description loses « Refusée si la
  section n'est pas encore ouverte » and says any section can be opened. Offered in the parcours
  only. The cached prefix moves once (declarations and the mode layer); the pins are regenerated.
- **SSE event** `section.skipped`: `{section_id, next_section_id, active_section_id, marker}` —
  `active_section_id` is the section still being worked after the skip (null when none);
  `next_section_id` is `path.page_turn` after the skip: the proposed next section when nothing is
  active, else null. Both null: the skip finished the chapter (marker key `marker.section_skipped`,
  with the section label). Browser: add to `progress.skipped`, clear `active` if it was that section;
  while `active_section_id` is set leave the page-turn button as it is, otherwise light it for
  `next_section_id`, or put it out when that is null too; insert the marker.
- **`section.start`** on a skipped section removes it from `progress.skipped` in the browser.
- **Stored entry** (spec 018): `{kind: "tool", name: "skip_section", arguments: {section_id},
  next_section_id, active_section_id}` as stored. The two ids are **recorded** from the event (by
  `entries_from_events`, or by the browser on a reported turn, as `review` is; checked to name
  sections of the chapter; never sent to the model), and a stored `complete_section` records
  `next_section_id` the same way. The `replay` hook rebuilds exactly the live output from the
  recorded ids, whatever the progress became since; an entry without them (stored before this spec)
  is answered from the progress now. Read back (`shown` hook), the entry shows its marker and
  `next_section_id` / `active_section_id` from the **current** progress by the page-turn rule, so the
  restored button proposes something valid now.
- **Cap rollover** (018 D10): the synthetic `start_section` that opens the row after a full one is
  written only when it tells the truth (the row's section is the active one, or the row was a review
  of a done section); otherwise the next row starts unsectioned and empty.
- `ProgressDTO` gains `skipped` (sorted), everywhere it travels (chapter view, séance read, voice tool
  response); the browser reads a progress without it as `skipped: []` (one helper, `progressFrom`).

## What the model reads

- **Mode layer** `prompts/modes/parcours.<lang>.md` — « Le parcours » is rewritten around these
  rules (French below is the reference; English and Dutch say the same in their own register):

  > Le chapitre est découpé en sections, dans l'ordre ci-dessus. Cet ordre est celui que tu
  > proposes : ce n'est pas une obligation. Ton élève est autonome et décide de ce qui se
  > travaille ; toi, tu choisis comment l'enseigner.
  >
  > - **Une section à la fois.** *(unchanged)*
  > - **Ton élève peut ouvrir n'importe quelle section**, même sans avoir fait les précédentes :
  >   parce qu'elle a été vue en classe, parce que l'interrogation porte dessus. Tu l'ouvres avec
  >   `start_section`, sans discuter et sans faire la morale. Si la section s'appuie sur une
  >   notion d'une section pas encore faite, tu le dis en une phrase, une seule fois, et tu
  >   avances ; si ça bloque en route, tu proposes d'aller voir cette section.
  > - **Ton élève peut passer une section** (« je l'ai déjà vue », « on passe »). Tu appelles
  >   `skip_section`, tu dis en une phrase ce qui vient ensuite, et c'est tout : pas de
  >   justification à demander, pas de test à faire passer. Une section passée reste ouverte et
  >   peut être commencée plus tard. Tu ne passes jamais une section de ta propre initiative.
  > - **Quitter une section en cours pour une autre est permis.** Tu ouvres l'autre avec
  >   `start_section`. La section quittée n'est pas terminée : quand ton élève y reviendra,
  >   `start_section` te dira où vous en étiez.
  > - **Une section n'est terminée que par `complete_section`** *(unchanged)*
  > - *(the rest unchanged: revoir, « Ma réponse à la question », c'est ton élève qui tourne la page)*

  The bullet « L'outil te dira si une section n'est pas encore ouverte » is removed. In the opening
  file, « Pas de programme à négocier : le parcours est le programme » becomes: propose the next
  section of the path; if the student prefers another, open it. A finished chapter: say so, and
  offer to go over a done section again or to do a skipped one.
- **Overview and state message** (`curriculum_render`): the lead says only that the order is the one
  Célestin proposes (« Sections dans l'ordre que tu proposes. »; no tool named: the mode layer and the
  declarations state their contract); the
  status line counts done and skipped apart and names the skipped sections; with nothing active it
  names the proposed next one; a finished chapter with skipped sections says which were skipped.
  The discussion's state lines get the skipped count too (read-only, no tool named).
- Tool refusals: `path.WORDS.locked`/`hint` go; a refusal for skipping a done section is added.
- **Authoring** (`prompts/authoring/curriculum.<lang>.md`): the path is the order Célestin proposes,
  not a lock; since a student may open any section first, each section's title and goal stand on
  their own.

All of it in the three course languages, through the existing `by_language` tables and prompt files.

## Interface

- **Chapter map**: every row is actionable.
  - done: « Relire » (cahier, when it has cards) and « Revoir »;
  - active: expanded with its goal; « Passer »;
  - skipped: a « passée » badge; « Commencer »;
  - available / open: « Commencer » — « Reprendre » when the section has a stored séance
    (`seances[id]` in the `GET …/seance` reply) — and « Passer ».
  The proposed next section stays visually the primary one. Actions are learner sentences in the
  course's language (`useLearnerSentences`: a new `skip(title)`), sent to the call when a voice
  session is open. Disabled while a turn is streaming, as today.
- **Chapter strip**: skipped segments are drawn apart from done ones; the done count reads
  « 7 faites · 2 passées » when something is skipped.
- **Course page**: a chapter whose sections are all done or skipped is « terminé ». The row DTO carries
  `skipped_count` beside `done_count`. A started chapter's row counts, never a position (sections are
  done in any order): « 3 faites sur 9 », « 3 faites sur 9 · 2 passées » when something is skipped
  (catalog plurals, fr/en/nl); « 9 sections » before it is started. « Reprendre » leads to the
  chapter as before.
- Copy in French, English and Dutch.

## Invariants touched

None of the non-negotiable ones. The brief's « locked path » (principle 6, §6.4) is rewritten in
`specs/product.md` in the same change.
