# PRD — Célestin, an AI tutor for the course you actually follow

**Version:** 2.1 — supersedes v2.0 (16 September 2026). v1.0 described a private tutor for one student, fed by chapters the parent loaded and approved. v2.0 was a pivot: a self-service platform where each student brings the course material their teacher gave them. v2.1 (15 November 2026) shifts the stance from supervising to equipping: the student is an autonomous, responsible teenager, and the product gives them tools — resume a lesson, reread it, open or skip any section, rehearse a whole course (specs 018–020).
**Owner:** [you]
**Date:** 15 November 2026

---

## 1. Summary

A web application where a secondary-school student brings their own course material — the notes, handouts and exercise sheets their teacher gave them — and gets a private AI tutor that helps them learn it, practise it and rehearse it before the test.

The student creates a **course** (a name and a subject, e.g. « Physique 5e », physique) and adds **chapters** to it by uploading the material: a PDF or photos of the pages. An authoring agent turns each chapter into two things: a **course pack**, a structured summary of what the chapter teaches (definitions, formulas, notation, vocabulary, sample exercises), and a **curriculum**, the path of sections the tutor follows through it. The tutor reads both and teaches by calling a fixed set of tools; each tool renders as a purpose-built board or card. The student never talks to a blank chat box; they work through a lesson.

We are not a source of content. The student's material is the only source of truth about *what* is taught; the product supplies the pedagogy.

The first users are French-speaking Belgian secondary students (Fédération Wallonie-Bruxelles). The interface and the tutor speak French by default; a course can also be an English course (spec 011) or a Dutch one (spec 017, Flemish), taught in that language, and the interface is French, English or Dutch at the user's choice (spec 010). Mathematics and physics come first; the other subjects follow on the same machinery.

## 2. Why this, why now

**The evidence says AI tutoring works when it is designed, not when it is a chatbot.** Two findings shape everything below:

- Unrestricted access to a general-purpose LLM *lowered* exam scores in a high-school math trial (Bastani et al., 2024); the same model wrapped in a hint-only tutor did not. What separates a tutor from a homework-solver is whether it withholds answers.
- A custom tutor built on explicit pedagogy beat in-class active learning by a wide margin (Kestin et al., 2025), while a large real-world deployment of a well-built tutor (Khanmigo, Oreopoulos & Low 2026) produced only small gains — because most students barely opened it and rarely engaged it in substantive dialogue. Pedagogy is necessary; *engagement* is the binding constraint.

**The products that exist don't fit.** General chatbots give answers. Khanmigo is tied to Khan Academy's curriculum and doesn't know the student's teacher's course. Photomath and Wolfram show solutions. Nothing available teaches the course the student is actually tested on, in the notation and vocabulary their teacher uses, from their own class material.

**Why self-service.** v1.0 needed a parent to load and approve every chapter; that does not scale past one household, and it puts us between the student and their material. Every student already holds the material that defines their test. Letting them bring it removes the bottleneck and keeps the tutor anchored to what their teacher actually taught.

## 3. Users

### 3.1 The student
- Secondary school, French-, English- or Dutch-speaking, any track. Receives course material from teachers: typed notes, « cours à trous », handouts, exercise sheets with or without corrections.
- Assessed by written tests that mix definitions to recite, procedures to apply, derivations or reasoning to reproduce, and applied problems.
- Does not want to learn a new notation, method or vocabulary — the tutor must speak their teacher's language.
- Motivation is the next test, not badges. Will abandon anything that feels like extra homework with no payoff, or that takes long to set up.
- Owns their account and their courses. Nobody else sees their material or their progress.
- Autonomous and responsible: they know what was covered in class and what the test is on. They decide what to work on and in which order; the product proposes, equips and records honestly, it does not police.

### 3.2 The parent (later)
A parent view (progress, transcripts, weekly recap) remains a goal but is not part of the current phases. No feature may depend on a parent being present.

## 4. Jobs to be done

| Job | Today | With the product |
|---|---|---|
| "Turn my teacher's notes into something I can study" | Re-read the notes | Paste the chapter; get a structured summary and a path through it in a couple of minutes |
| "Explain this part of the course I didn't get in class" | Re-read notes, ask a friend, watch a video in a different notation | Follow the chapter path, or ask the tutor; it explains with the course's own definitions and notation |
| "Practise before Thursday's test" | Redo the same exercises from the sheet | Tutor sets fresh variants of the course's exercises, checks each one, focuses on weak spots |
| "I just want to ask questions about this chapter" | Ask a chatbot that ignores the course | Discuss the material with the tutor, who explains on the whiteboard (later, §6.5) |
| "Do I actually know this?" | Guess | The tutor tests and rehearses the material with them (later, §6.6) |

## 5. Product principles

1. **It teaches the student's course, not the subject in general.** The student's material defines the definitions, formulas, notation, vocabulary and methods. If the teacher writes `]−3; 3[` and `Sₙ = (u₁+uₙ)·n/2`, so does the tutor. Anything else is a defect.
2. **The content is the student's.** We never supply or overrule course content. The authoring agent restructures what the student gave; it does not add material that is not in it.
3. **It withholds answers by construction.** While an exercise is open, the tutor can explain, question and hint; it cannot state the answer. Revealing a solution is a deliberate, gated act and is always recorded.
4. **It never grades from impression.** Where an answer is mechanically checkable (numbers, expressions, intervals, choices), the verdict comes from a checker, not from the model's prose. Free-text answers (definitions, justifications) are graded against an explicit rubric.
5. **It remembers.** Progress through each chapter is kept per student; a lesson resumes where it stopped, with its exchange and its boards, and every past lesson can be reread (the « cahier »).
6. **It is a lesson, not a chat.** The tutor drives the lesson: it proposes the next step and the next section. The student can interrupt or ask anything at any time, and turns the page when ready.
7. **Setup is minutes, not hours.** Creating a course is a name and a subject. Adding a chapter is uploading its pages. No review step stands between the student and their first lesson.
8. **The student is in charge of their work.** The path is the order the tutor proposes, not a lock: any section can be opened, left or skipped, and what was skipped is recorded as skipped, never as done. Freedom covers *what* is worked on and *when*; it never covers principles 3 and 4 — the tutor still withholds answers and still never grades from impression.

## 6. The product

### 6.1 Overview

- **Courses and chapters** — created by the student. A course has a name and a subject; a chapter is the material the student uploads. Private to the student.
- **Subjects** — a closed list we define. Each subject comes with a subject prompt and a pack template that we write, test and maintain.
- **Authoring agent** — turns a chapter's raw text into a course pack and a curriculum, following the course's subject.
- **The tutor** — reads its three prompt layers (§6.3), the pack, the curriculum and the student's progress, and teaches by calling tools. The tools enforce the rules (the path's states, checking, withholding, recording).
- **The interface** — a lesson view where each tutor action appears as a board or card, plus the chapter strip and map showing where the student is.

The tutor works in three modes on the same chapter material:

| Mode | What it is | Status |
|---|---|---|
| **Parcours** | Follow the chapter's curriculum: learn, practise, synthesise, section by section, in the proposed order or the student's own | Built (specs 002–006); stored and resumable (018); open path (019) |
| **Discussion** | Free conversation about the material, with the whiteboard | Built (spec 007) |
| **Révision** | The tutor makes the student retrieve what they know across the chapters of a course, and keeps their own assessment of it | Designed (spec 020), not built yet |

### 6.2 Courses and chapters

**Creating a course.** The student gives a name, picks a subject and says in which language the course is written (French, English or Dutch; the interface language is the natural first guess). That is all. The course appears in « Mes cours ». The subject and the language are locked for good: a student who picked the wrong one creates a new course. The language is the one of the material, the pack, the path, Célestin's speech and the board's notation (spec 011).

**Subjects.** A closed list of four broad categories, defined by us. They are grouped by how a subject is taught and answered, not by school discipline: the student's material carries the content, a subject only fixes the way of teaching, writing and checking.

| Subject | Interface label | Covers | Way of working |
|---|---|---|---|
| Mathematics | Mathématiques | mathematics | calculation, proof, exact notation |
| Sciences | Sciences | physics, chemistry, biology, general science | quantities and units, laws, chemical equations, structures and processes, experiments, diagrams |
| Languages | Langues | French and foreign languages | rules, vocabulary, conjugations, texts, fill-in exercises |
| General courses | Cours généraux | history, geography, general studies, anything learnt from the course | facts and reference points, causes and consequences, documents |

Each is offered in French, English and Dutch (specs 011, 017). There is no « Autre » and no per-discipline subject: « Cours généraux » is the broad category for a knowledge course. The student's school year is not asked; the tutor takes the level from the material. For a language course, Célestin speaks the course's language (French for a French-speaking student) and works in the language being learnt; the dictation of a language course gets no language hint, since it mixes two.

**Adding a chapter.** The student uploads the chapter's material — one PDF, or photos of the pages taken with the phone — typed notes, « cours à trous » filled by hand, exercise sheets, corrections. A transcription stage reads every page (handwriting and formulas included, doubtful readings marked) into text; that text is the chapter's source, which the student can read and correct. The file itself is not kept. (Specs 005 took pasted text; spec 006 replaces it with upload.)

**Adding pages to a chapter (later).** The student photographs a few new pages and adds them to an existing chapter; the pack and the path are updated from the new pages rather than rebuilt, keeping progress where the path did not change.

**Authoring.** The authoring agent runs in the background; the student sees the chapter as « en préparation » and can leave the page. It produces:

- **The course pack** — the chapter as the teacher presents it, in structured Markdown following the subject's pack template. The maths template, the reference for the others, has:
  - chapter goal, and what the test is likely to expect (definitions to recite, procedures, reasoning to reproduce, types of problems);
  - prerequisites;
  - notation conventions;
  - concepts in teaching order, each with the definition as written in the material, formulas verbatim with their conditions, examples, the derivation if the material gives one, and common errors;
  - vocabulary;
  - numbered sample exercises with the method and the answer, where the material provides or allows one;
  - points the agent could not settle (unreadable, contradictory, answers that do not check out). The tutor does not teach or set exercises that depend on them.
  Other subjects keep the same spirit with their own sections: a physics pack adds quantities, units and laws; a history pack has a timeline, key figures, causes and consequences, and documents to analyse; a language pack has grammar rules, vocabulary lists and conjugations.
- **The curriculum** — the path of `teach`, `practise` and `synthesis` sections through the pack, as structured data, every reference pointing at an existing entry of the pack.

Both are validated mechanically before the chapter is usable. If authoring fails, the chapter shows the failure and the student can retry.

**No review step.** The chapter is ready as soon as authoring succeeds. The pack is shown as the agent's reading of the material, not as a verified document.

**Editing.** The student can edit a chapter — its pack, its curriculum, or its source text followed by a new authoring run. Any edit resets the student's progress on that chapter to zero.

**Storage.** Courses, chapters, packs, curricula and progress live in the database, owned by the student's account. Nothing a student creates lives on the file system.

### 6.3 What the tutor reads

The tutor's instructions come in three layers, assembled in this order:

| Layer | Written by | Contains |
|---|---|---|
| **Tutor prompt** | us, one for all | Who Célestin is and how Célestin teaches: the path, the tools, the whiteboard, what Célestin never does. Subject-neutral. |
| **Subject prompt** | us, one per subject | How the subject is taught, how it is written (LaTeX for maths and physics, units and significant figures, dates…), which kinds of answers exist and how each is checked, what counts as off-topic. |
| **Chapter pack and curriculum** | the authoring agent, from the student's material | Everything specific to the teacher: definitions, notation, vocabulary, methods, exercises, the path. |

Conventions a teacher uses across chapters are repeated in each chapter's pack rather than held at course level, so every chapter stands alone and editing one never affects another. The subject prompt and pack template also drive the authoring agent, and Discussion and Révision modes will reuse them.

### 6.4 The tutor in Parcours mode

The tutor behaves like a good private teacher who has read the chapter and knows the student. It can:

**Follow the path.** Each chapter is a sequence of sections. `teach` sections go through the course's content beat by beat and end with a check question; `practise` sections set a number of exercises in the style of the course's samples; `synthesis` sections mix everything before them, test-style. The order is the one the tutor proposes. The student can open any section, leave one for another, or skip one they have seen in class; a skipped section is recorded as skipped, stays open, and can be done later. A section is done only when its criterion is met. Done sections can be reviewed with the tutor, or simply reread.

**Explain.** Introduce or re-explain a concept using the course's definition and formulas, and check understanding with a quick question before moving on.

**Show a worked example.** Walk through a sample exercise step by step, the student revealing each step; in "faded" mode they supply a step before seeing the next.

**Set an exercise.** Generate a fresh exercise as a variant of the course's sample exercises, matched to the section, with an answer widget that fits the kind of answer.

**Read their work.** The student photographs handwritten work (a phone's camera or gallery, or a computer's webcam); a vision model reads it into text, the student corrects it in the message field, and what she sends is an ordinary message the tutor checks step by step. The tutor never sees the picture (`documentation/work-reading.md`). Not yet: several photos, or showing the picture beside what was read.

**Check.** Every checkable answer is verified mechanically; the verdict, and what differs from the expected answer, is what the tutor responds to.

**Hint.** A three-level ladder: orient, method, first step. Hints contain no part of the answer.

**Discuss.** "Pourquoi ?", "J'ai fait autrement" — the tutor engages with the student's reasoning and compares it with the course's. It prefers questions to statements.

**Reveal.** After repeated attempts, or when asked, the tutor walks through the full solution one step at a time. Every reveal is recorded.

**Remember.** Progress through the path is recorded per student and per chapter, and so is each section's lesson: reopening a chapter brings back the exchange and the board where they stopped, and coming back to a section left unfinished continues from the last card rather than from the start.

**Keep the notebook.** Every board the tutor showed is kept, section by section, in the chapter's « cahier »: the student rereads a past lesson without asking the tutor to teach it again.

### 6.5 Discussion mode

The student talks with the tutor about the chapter: asks questions, asks for another explanation, explores an example. The tutor answers from the pack, and writes and draws on the whiteboard to explain. The same rules hold: the course's notation and vocabulary only, and no solving of homework or test exercises on the student's behalf.

### 6.6 Révision mode

The student picks the chapters of a course that the test covers, and the tutor makes them retrieve what they know, mixed across those chapters: definitions to recite, variants of the course's exercises, reasoning to reproduce. It is the door for a student who saw the material in class: test first, then go and work the sections that turned out weak.

After each question is settled, the tutor puts the course's own wording on the board, the student compares and says how it went — acquis, fragile, à revoir — and that self-assessment is kept per section. It is the student's judgement, not a verdict: the tutor may say when it sees things differently, and never overrules. The next révision starts from what is fragile, what was skipped and what was never done; a « bilan » shows the record and points to the section to work and to its cahier. Nothing in a révision moves the path.

### 6.7 How the tutor behaves

- Speaks the course's language (French with tutoiement, English with an informal « you », or Dutch with « je »), warm and direct. Praise only when earned and specific.
- Uses only the course's formulas, methods and vocabulary. Introduces nothing the material does not contain. If asked about something outside the course, it answers briefly and says it's beyond what the material covers.
- Prefers questions to explanations when the student is stuck. Explains fully when they meet a concept for the first time.
- Recognises recurring errors and names the pattern rather than just correcting the instance.
- Stays on the course. Off-topic requests get a friendly redirect.
- Knows when to stop. Sections have a visible end; the tutor closes with a short recap and what's next.

### 6.8 The interface

- **« Mes cours »**: the student's courses; create a course with a name and a subject.
- **A course**: its chapters in order, each with its state (en préparation, échec, prêt, en cours, terminé); add a chapter by uploading a PDF or photos; « Réviser » will open a révision over the chapters the student picks (spec 020).
- **A chapter**: the lesson view (board, cards, chapter strip and map, voice), the discussion, the « cahier » of past boards, and access to the pack and curriculum for reading and editing. On the map every section can be started, resumed, skipped, reviewed or reread.
- **Cards**: plan, explanation, worked example, exercise with an answer widget matched to the answer type, verdict, hint, solution, check question, recap.
- **« Paramètres »**: from the user menu; the interface language today, built to hold the account's other settings (name, email address, password) later.

Interface copy is French, English or Dutch, at the user's choice: the browser's language on the first visit, kept on the account, changed in the settings (spec 010). The tutor, the board and the notation follow the course's language (spec 011). Web app, laptop first, tablet-friendly.

## 7. A first session, end to end

*Sunday, 17:00. Physics test on Thursday.*

The student signs in, creates the course « Physique 5e » with the subject Physique, and adds a chapter: they photograph the teacher's notes on uniform motion and the exercise sheet that goes with it, six pages. The chapter shows « en préparation ».

Two minutes later it is ready: nine sections, from « Référentiel et trajectoire » to « Synthèse ». They open it. Célestin starts section 1, quoting the notes' definition of a référentiel with the teacher's own example of the train and the passenger, and asks a check question.

Two sections later, a practice section: Célestin sets a variant of exercise 3 from the sheet — a cyclist at constant speed, find the time to cover 12 km. They type `40 min`. The checker accepts it. The next exercise they get wrong twice; hint 1 asks which formula links distance, speed and time; hint 2 asks them to convert the speed to km/min first. They get it.

The next day they notice the pack lists « km/h » where the teacher writes « km·h⁻¹ ». They correct the pack; the chapter's progress restarts, and Célestin now writes km·h⁻¹.

## 8. Safety and guardrails

- **No answer leakage** while an exercise is open. Reveals are explicit, gated and logged.
- **No unverified grading**: a correctness verdict comes from the checker, or from a rubric for free text, never from impression.
- **No invented content**: the authoring agent restructures the student's material and adds nothing to it; exercises the tutor sets are variants of the pack's samples; points the agent could not settle are not taught.
- **No drift from the course**: formulas, notation, methods and vocabulary are restricted to the pack.
- **No off-topic use**: the tutor redirects off-topic conversation; it does not do other homework or write essays.
- **Pasted material is data, not instructions**: nothing in a chapter's text can change the authoring agent's or the tutor's rules.
- **Privacy**: a student's courses, material and progress are visible only to them. No third-party analytics. No sharing between students in the current phases.
- **Cost control**: authoring runs are limited in input size and in frequency per student.
- **Age-appropriate**: the tutor is a teacher, not a friend. Tone is warm but professional.

## 9. Success

**Primary:** students use it. ≥ 4 sessions a week during term per active student, sustained past the first month.

**Setup:** a chapter goes from uploaded pages to a first lesson in under 5 minutes, with no manual fix needed in most chapters.

**Authoring quality:** share of chapters the student edits after authoring, and share of authoring runs that fail validation — both tracked, targets set after a baseline.

**Learning:** first-attempt pass rate on synthesis sections; test results relative to before, as reported by students.

**Trust:** answer-leak rate below 1% of tutor messages during open exercises; zero formulas or methods in transcripts that are not in the pack.

**Dialogue quality:** share of exercise turns where the student explains reasoning rather than just submits an answer — above 30%.

## 10. Risks

| Risk | Why it matters | What we do |
|---|---|---|
| Students stop using it after two weeks | Kills the product regardless of quality | Tutor-led lessons, short sections, visible progress, setup in minutes |
| Authoring mangles a formula or misreads an exercise, with no reviewer | Wrong teaching from day one | Agent restructures, never invents; doubtful items flagged and not taught; mechanical validation of structure and references; the pack is always readable and editable by the student |
| Pasted material is incomplete or messy (copy from a PDF, missing figures) | Thin or wrong pack | Agent flags gaps; PDF and image input come later; the student can edit |
| Tutor teaches a method the teacher marks wrong | Destroys trust | Pack-restricted formulas, methods and vocabulary |
| Subjects where answers are not mechanically checkable | Verdicts cannot come from a checker | Each subject prompt fixes its answer kinds; rubric grading for free text; the broad categories (languages, general courses) are drafts to tune on real chapters |
| Generated exercise has a wrong expected answer | Undermines the checking story | Variants of the pack's samples only; independent solve where the type allows; discard on disagreement |
| Tutor leaks answers under pressure ("juste dis-moi") | Reverts to homework-solver | Gating in the tools, not the prompt; reveals logged |
| Authoring cost per chapter | Uncapped spend per student | Input size limit, per-student rate limit, cost logged per run |

## 11. Scope and phases

**Done.** The lesson for one hand-authored maths chapter: tutor with tools, board and cards, locked path of sections, voice mode, accounts and server-side progress (specs 001–004).

**Phase A — Student-authored courses.** Courses (name and locked subject) and chapters created by the student; a subject-neutral tutor prompt plus subject prompts and pack templates for mathematics and physics; pasted text as chapter input; authoring agent producing pack and curriculum; all content in the database; pack and curriculum editable, an edit resets the chapter's progress. The file-based catalog and its built-in class are retired; the chapter 1 material seeds a local test account.

**Phase A″ — Document upload (spec 006).** PDF and photos replace pasted text as the chapter input, through a vision transcription stage. Later: adding pages to an existing chapter, updating its pack and path incrementally.

**Phase A′ — More subjects.** Done as four broad categories (mathematics, sciences, languages, general courses), each with its subject prompt and pack template in both languages. The three added ones are first drafts, written without sample material from real courses: to tune on real chapters.

**Phase B — Discussion mode.** Done (spec 007). Free conversation about a chapter, with the whiteboard.

**Phase B′ — Tools for an autonomous student.** Done (specs 018, 019). Lessons stored and resumed, the « cahier » of past boards, the open path with skipped sections.

**Phase C — Révision mode.** Designed (spec 020), not built yet. Retrieval practice across the chosen chapters of a course, with the student's self-assessment kept per section. Later: a mechanical checker feeding the same record, voice, a test date shaping the session.

**Later.** Mechanical checker for more answer kinds; parent view; sharing a course with classmates.

**Out of scope for now:** sharing or publishing courses, teacher or classroom accounts, content we author ourselves, native mobile apps, grading of drawn graphs, essay-style subjects where answers cannot be checked or rubric-graded.

## 12. Open questions

1. **Checking outside maths.** Which answer kinds does the checker cover per subject, and when does the tutor fall back to rubric grading?
2. **Authoring failures.** How much of a partially usable result do we keep — a pack with no valid curriculum, a curriculum with dangling references — or is a chapter all or nothing?
3. **Copyright of teacher material.** Material is stored privately for the student who uploaded it; confirm this is acceptable before any sharing feature.
4. **Material language.** Specs 011 and 017 made a course French, English or Dutch, chosen when it is created; what about other languages (German)? And material in a language other than its course's is not detected: only a pack written for the other language's template is. Outside « Langues étrangères », should the language be inferred from the document?
5. **Level.** The school year is not asked for now. Does the tutor need it once several courses and subjects coexist?
6. **Test dates.** Should a course or chapter carry a test date that shapes the path and, later, Révision mode?

## Appendix — Evidence base

- Bloom (1984), the 2-sigma problem: one-to-one mastery tutoring vs classroom.
- Kulik & Fletcher (2016), meta-analysis of intelligent tutoring systems.
- Dunlosky et al. (2013), retrieval practice, spacing and interleaving.
- Bastani et al. (2024), *Generative AI can harm learning* — unrestricted LLM vs hint-only tutor in high-school math.
- Kestin et al. (2025), custom AI tutor vs in-class active learning.
- Oreopoulos & Low (2026), NBER WP 35620, two-year Khanmigo trial — engagement as the limiting factor.
- Wang et al. (2024), Tutor CoPilot — real-time guidance for human tutors.
- Google LearnLM reports — measurable pedagogical behaviours (manage cognitive load, active learning, adaptivity, curiosity, metacognition), used as the rubric for tutor quality.
- Khan Academy engineering notes (2026) — restricting the tutor to the student's completed steps halved answer give-aways.
