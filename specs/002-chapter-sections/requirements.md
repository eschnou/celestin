# 002 — A chapter as a locked path of sections

## 1. Introduction

Spec 001 gave the tutor a whole chapter and let it choose what to teach. The result varies too much from one session to the next: the tutor picks a different entry point, a different depth, and drifts between topics that her teacher keeps apart. This feature fixes the *structure* of a chapter and keeps the prose live.

A chapter becomes two files: `pack.md`, the course as the teacher presents it (unchanged in shape from 001), and `curriculum.yaml`, an ordered list of sections that says how Célestin walks through it. Sections are of three kinds: pure teaching, exercises, synthesis. The path is locked: a section opens only when the previous one is done, and the learner can always go back to a finished section. Two new tools let the tutor start and close a section, and enforce the path. The interface shows the whole path and where she is on it.

Scope of this feature:

- The chapter 1 pack trimmed to sequences only. Absolute value and number sets are removed; they will be a chapter of their own later.
- A curriculum file format, its loader, and a first curriculum for chapter 1 drafted from the pack's teaching order.
- Two section tools with path enforcement in the tool layer.
- Client-held progress state that survives a reload, and a chapter map in the interface.
- Teaching sections as a distinct tutor behaviour: scripted beats, course quotes, a check question, no exercises.
- The check-question card's answer reaching the tutor, since teaching sections complete on it.

Out of scope, stated so the boundary is unambiguous:

- Any backend persistence. This is still a POC validating a way of teaching; the browser holds progress.
- A mechanical checker, mastery levels, or a notion of "acquis". Practice sections close on the tutor's judgement and the state is called "fait", not "acquis".
- Editing the curriculum from the interface, or any parent view.
- Jumping forward. The path is locked by decision, not by omission.

## 2. Alignment with product vision

| Product requirement | How this feature serves it |
|---|---|
| §5.1 It teaches her course, not "math" | The curriculum follows the pack's teaching order section by section, so a session covers what her teacher covered in one block, in that order. |
| §5.6 It is a lesson, not a chat | The tutor opens by situating her on the path and starting the next section. There is no agenda to negotiate; the chapter *is* the agenda. |
| §6.3 Plan / Explain / Set an exercise | Teaching sections are the "explain" behaviour with a script; practice sections are the "set an exercise" behaviour with a fixed exercise pool. |
| §6.5 Side panel with the session plan and concept map | The mock session plan becomes the chapter map: every section, its state, the current one highlighted. |
| §6.2 A pack is deliberately small and chapter-agnostic | The pack format does not change. Sequencing lives next to it, so a second chapter needs a second pair of files and no code. |
| §10 Risk: works for chapter 1, not chapter 5 | The curriculum format carries nothing specific to sequences. |

Deliberate deviations, for a POC:

- §5.3 "never grades from memory" is still not satisfiable. Closing a practice section is the tutor's judgement against the section's `done_when`. The state name "fait" rather than "acquis" is what keeps this honest until a checker exists.
- §5.4 "It remembers" is served by browser storage only. Progress is per browser, invisible to the parent, and lost if site data is cleared.

## 3. Requirements

### R1 — A homogeneous chapter

**As a** parent, **I want** chapter 1 to cover sequences only, **so that** the tutor teaches one coherent topic per chapter.

Acceptance criteria:

1. `courses/chapitre_1/pack.md` contains the sequences material only: suites numériques, suites arithmétiques, suites géométriques, limite d'une suite, and the exercises that use them.
2. Number sets, absolute value, its notation conventions, its vocabulary, its exercises and its validation points are removed from the pack. The pack header states that this material is out of the pack and will be a chapter of its own.
3. Section numbering inside the pack stays stable (1 objectif … 8 points à faire valider) so cross references such as "voir §8" remain correct.
4. Everything kept is kept verbatim, including page references, methods and the remaining validation points.
5. The pack format is unchanged. Nothing in the loader, prompt assembly or tools needs to know the pack was trimmed.

### R2 — Curriculum file

**As a** parent, **I want** the order and grouping of a chapter in a small readable file next to the course, **so that** I can change how Célestin sequences the chapter without touching the course text or the code.

Acceptance criteria:

1. `courses/chapitre_1/curriculum.yaml` exists beside `pack.md` and is the only source of the chapter's sections.
2. The file declares: a chapter `id`, a `title`, the `pack` file name, and an ordered list of `sections`.
3. Each section has an `id` (unique within the chapter, URL-safe), a `kind` among `teach`, `practise`, `synthesis`, a `title`, a `goal` in one sentence, and a `done_when` sentence stating the completion criterion in the tutor's terms.
4. A `teach` section has an ordered list of `beats`, each a French sentence saying what to do, referencing the pack by heading or example. It has no exercise pool.
5. A `practise` or `synthesis` section has an `exercises` list naming the pack's sample exercises to make variants of, and a `count` of exercises to complete. It has no beats.
6. The file is loaded and validated at startup. A missing file, a duplicate id, a `teach` section without beats, or a `practise` section without exercises fails startup with a message naming the file and the section.
7. Like the pack, the file is cached by modification time, so an edit is picked up on the next request without a restart.
8. The first curriculum for chapter 1 is drafted from the pack's teaching order, alternating teaching and practice, ending with a synthesis on SA/SG recognition and a mock test. It is content, reviewable by the parent like the pack.

### R3 — A locked path

**As a** parent, **I want** the sections to open in order, **so that** she cannot skip the derivation she will be asked to reproduce.

Acceptance criteria:

1. At any moment every section is in exactly one state: `done`, `active`, `available` or `locked`. At most one section is `active`. `available` is the first section that is neither done nor active, and only if no section is active. Everything after it is `locked`.
2. The tutor can start the `available` section, restart the `active` one, or start a `done` one as a review. Starting a `locked` section is refused.
3. The tutor can complete only the `active` section. Completing a done, available or locked section is refused.
4. The refusal is a tool error returned to the model, naming the section it may start instead. It is never an HTTP error and never reaches the learner as a failure.
5. These rules are implemented in the tool layer as a pure function of the curriculum and the progress state, unit-tested, and not restated as prompt instructions the model could ignore.
6. Reviewing a done section does not change its state; it stays `done` and no other section moves.

### R4 — Section tools

**As a** learner, **I want** the tutor to work through one section at a time, **so that** each session has a clear beginning and end.

Acceptance criteria:

1. A `start_section` tool takes a section id. On success its result gives the model the section's brief: kind, title, goal, the beats or the exercise pool with its count, the completion criterion, and whether this is a review of a done section.
2. A `complete_section` tool takes the section id and a one-sentence summary of what was done. On success its result names the next section, or says the chapter is complete.
3. Each successful call emits an event the interface uses to update the chapter map, and a French marker in the transcript ("section commencée : …", "section terminée : …").
4. Both calls are recorded in the transcript as tool entries, like board tools, so the model sees them on later turns. A replayed `start_section` carries the same brief it produced the first time, so the model does not lose the beats after the next message.
5. The tools sit in the cached prompt prefix in a fixed position after the board tools. Adding them must not change the declaration of the board tools.

### R5 — Progress, client-held

**As a** learner, **I want** to find the chapter where I left it, **so that** a session continues the path rather than restarting it.

Acceptance criteria:

1. Progress is `{done: [section ids], active: section id | null}` per chapter, held by the session hook.
2. It is sent with every request so the backend can enforce R3 and inform the tutor (R6) without holding state.
3. It is persisted in browser storage keyed by chapter id, and restored on load. The transcript is not persisted; a reload starts a new conversation on the same progress.
4. A section left `active` stays `active` across reloads. The tutor resumes it.
5. A reset control in the chapter map clears the progress for the chapter after a confirmation, and starts a new conversation.
6. Progress is updated from the section events only. The interface never marks a section done on its own.

### R6 — The tutor knows where she is

**As a** learner, **I want** the tutor to pick up where we stopped, **so that** I do not have to explain what we did.

Acceptance criteria:

1. The prompt receives a rendered overview of the curriculum: the ordered sections with id, kind, title and goal. This overview is static per chapter and sits inside the cached prefix.
2. The current progress is rendered as a short French state message and appended after the transcript, never inside the cached prefix. It names the done sections, the active one if any, and the one that can be started.
3. With an empty transcript, the tutor greets, situates her on the path in one sentence, and starts the active or available section in the same turn. There is no agenda negotiation. If the chapter is complete, it says so and proposes a review.
4. If she asks to go back to a finished section, the tutor starts it as a review, and afterwards returns to the section she was on.
5. The tutor never announces a section as done without calling `complete_section`, and never calls it before the section's `done_when` is met on the evidence in the conversation.

### R7 — The chapter map

**As a** learner, **I want** to see the whole chapter and where I am, **so that** progress is visible and the end is in sight.

Acceptance criteria:

1. The mock session plan in the tutor column is replaced by the chapter map, fed by the curriculum and the progress state.
2. The map lists every section in order, as a vertical path: number, kind badge (Cours / Exercices / Synthèse), title, and state.
3. States are visually distinct: done (tick, muted), active (accent, expanded to show its goal), available (normal, "à suivre"), locked (dimmed, lock glyph). Locked sections are not interactive.
4. A progress line shows sections done over total, and a bar.
5. Selecting a done section sends a learner message asking to review it, phrased in French; the tutor handles the rest (R6.4). Selecting the available section sends a message asking to start it.
6. The tutor column header names the active section, so it stays visible when the map is collapsed.
7. Below the `lg` breakpoint the map collapses to the progress line and the active section, expandable on tap.
8. Section markers in the transcript (R4.3) use the existing marker style.

### R8 — Teaching sections

**As a** learner, **I want** a teaching section to feel like a short lesson, **so that** I learn the notion before being asked to apply it.

Acceptance criteria:

1. In a `teach` section the tutor follows the beats in order, one board card per beat where the beat teaches something, quoting the course verbatim for definitions and formulas. It sets no exercise cards.
2. Each beat is followed by a one-line check in the conversation before the next beat, in the "small steps" spirit of the prompt.
3. The section ends with a check question on the board. Its answer must reach the tutor: choosing an option on the check-question card sends a learner entry stating the chosen option, and the tutor reacts to it.
4. In a `practise` section the tutor sets exercises one at a time, each a variant of one in the section's pool, and explains only to unblock. It does not re-teach the section's notion unless she asks.
5. In a `synthesis` section the tutor mixes the listed material and does not announce which notion an exercise belongs to.
6. These behaviours are described in the prompt, per kind, in one place, so the parent can read and change them.

## 4. Non-functional requirements

### 4.1 Architecture

1. The curriculum is read through the same accessor as the pack. Replacing the hardwired chapter later touches one module.
2. Path rules (R3) are a pure function `(curriculum, progress) -> state per section`, shared by the tools and the state message, with no I/O.
3. The backend stays stateless: progress comes in with the request and goes out as events.
4. The two new tools are added through the registry like the board tools and touch neither the controller nor the provider adapter.
5. The SSE contract grows by two events. The frontend types, the golden transcript tests and the design document change together.

### 4.2 Performance

1. The cached prefix (prompt, pack, curriculum overview, tool declarations) stays byte-stable across turns and sessions. The smoke script still fails on a cache miss on the second turn.
2. The state message is short (under 300 tokens for a 13-section chapter) since it is re-sent uncached on every turn.
3. Restoring progress from storage does not delay the opening turn.

### 4.3 Security

1. Section ids from the model are validated against the curriculum before use, like every tool argument.
2. Progress from the client is validated: unknown ids are dropped, duplicates removed, and an `active` id that is also in `done` is rejected with a 422.
3. Curriculum content that reaches the client is limited to id, kind, title and goal. Beats and exercise pools stay server-side with the pack.
4. Browser storage holds section ids only.

### 4.4 Reliability

1. A failed turn leaves progress untouched, like the board.
2. Corrupt or unparseable stored progress is discarded and the chapter starts from the beginning, with a console warning, not a blank screen.
3. Reaching `max_rounds` inside a section does not complete it.

### 4.5 Usability

1. All map and marker copy is French, tutoiement, consistent with the interface.
2. The active section is visible without scrolling the map on a laptop screen for a 13-section chapter.
3. Map items are keyboard reachable; locked items are announced as such.

### 4.6 Known limitations carried forward

1. **Practice sections complete on the tutor's judgement.** No checker exists. The state is called "fait", and the summary passed to `complete_section` is the only record of why.
2. **Progress is per browser.** No backend record, no parent view, no sync across devices.
3. **Board interactions other than the check question** remain invisible to the tutor.
4. **Validation points.** Four items in the pack still await parent validation and block the exercises that depend on them, notably the sum 6 + 12 + … + 60 and the bouncing ball.
5. **No exercise checking**, so R8.4 relies on the prompt's rule against stating answers, as in 001.
