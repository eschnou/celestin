# 004 — Accounts and classes: from one learner to students

## 1. Introduction

Three specs built a tutor for one learner on one chapter, with no login, one hardwired chapter (`courses/chapitre_1/`), and progress held in the browser's `localStorage`. This epic turns it into a product surface: people register, sign in, see the classes on offer, enrol, pick a chapter, and pick up where they left off on any device.

Vocabulary, fixed here because the code and the copy will use it:

- **User** — an account: email, password, role. Roles are `student`, `parent`, `admin`. This epic implements the student role only; the other two exist as values so nothing has to be renamed later.
- **Class** (« classe ») — a course offering with a name, a subject and a set of chapters. « Mathématiques 5e — 2026-2027 » is a class. In this epic classes are declared in a catalog file next to the courses, not created through any interface.
- **Chapter** — what specs 002 and 003 already call a chapter: a `pack.md` plus a `curriculum.yaml`. Chapters in a class are independent; a student may take them in any order.
- **Enrolment** — a student's membership of a class.
- **Progress** — per student and per chapter, the `{done, active}` section record spec 002 defined, now owned by the server.

Scope:

- Registration with email and password, sign-in, sign-out, and a server-side session that guards every route.
- Roles stored on the user; student-only flows; routes for the other roles refused, not built.
- A class catalog read from the course files; a student lists classes and enrols.
- A class page showing each chapter's progress; entering a chapter opens the existing lesson screen for that chapter.
- Section progress stored on the server, updated by the section tools, restored on the next visit from anywhere.
- Multi-chapter support in the backend: the tutor is built for the chapter the student opened.
- The voice routes tied to the signed-in user (the `VoiceAccess` seam of spec 003 becomes real).

Out of scope, stated so the boundary is unambiguous:

- Email verification, password reset, "remember me", OAuth or social sign-in. Flagged in §4.6 as needed before the product is exposed beyond the household.
- Parent and admin interfaces: class creation, chapter upload, the parent's progress and transcript views (product brief §6.6). The data model must not block them.
- Transcript persistence. A chapter resumes at its section, not mid-conversation. Recorded as a limitation.
- Leaving a class, or re-taking a chapter from scratch through the interface (the existing reset stays as a per-chapter action).
- Multi-tenant or school-level structures, billing, quotas beyond the existing voice rate limit.

## 2. Alignment with product vision

| Product requirement | How this feature serves it |
|---|---|
| §5.4 It remembers | Progress moves from one browser's storage to the student's account, so the tutor starts from her record on any device, and the parent view of a later spec has something to read. |
| §5.5 It works the way she works: short sessions | Resuming is one click: the class page shows where she is in each chapter and « Reprendre » opens the active section. |
| §6.5 Devices: laptop first, tablet-friendly, phone for photos | Signing in on a second device is now possible, which the localStorage design prevented. |
| §7 A session, end to end | The plan card of the brief is replaced by the class page: chapters and their state, then the chapter's locked path as today. |
| §6.6 Parent view | Not built, but every record (user, enrolment, progress, voice usage) carries the student's identity, which that view needs. |
| §3.1 Chapters are what she is tested on | Chapters stay independent within a class; the locked path stays inside a chapter. |
| §10 Risk: works for chapter 1, not chapter 5 | The backend stops being hardwired to one chapter directory; a second chapter is a second directory and a catalog line. |
| §8 Privacy: data owned by the parent, exportable, deletable | Not delivered here; the account model is the prerequisite. Recorded in §4.6. |

Deliberate deviations, for this epic:

- The brief's "one learner, one parent, data owned by the parent" becomes "students own accounts; a parent role exists". The parent-student link is a later spec.
- The backend stops being stateless. It gains a database for users, enrolments, progress and voice usage. The turn pipeline itself stays stateless per request; only progress is read from and written to the store.

## 3. Requirements

### R1 — Registration and sign-in

**As a** student, **I want** to create an account with my email and a password and sign in with it, **so that** my work is mine and follows me.

Acceptance criteria:

1. A registration form takes an email, a password and a display name (« prénom »). A new account has the `student` role. Registration signs the user in.
2. Email is normalised (trimmed, lower-cased) and unique. A second registration with the same email is refused with a French message that does not reveal whether the address exists in any other flow (sign-in says « email ou mot de passe incorrect », registration says the address cannot be used).
3. Password rules: at least 10 characters, no other composition rule, checked against the display name and email (the password may not contain them). The rule is stated on the form before she types.
4. Passwords are stored as Argon2id hashes with at least the OWASP minimum parameters (m = 19 MiB, t = 2, p = 1). Plain passwords never appear in logs or error messages.
5. Sign-in takes email and password and opens a session. Sign-out ends it. Both are one request each.
6. A session lasts a configurable time (default 30 days of inactivity, absolute maximum 90 days) and is renewed by use. The credential is an httpOnly, `SameSite=Lax`, `Secure`-in-production cookie; page scripts cannot read it.
7. Every route except registration, sign-in, health and the static assets requires a session. An unauthenticated request to an API route gets a 401 with a French message; an unauthenticated visit to a page redirects to sign-in and returns to the requested page after.
8. Sign-in and registration are rate-limited per client (configurable, default 10 per 15 minutes per IP and per email) with a 429 and a French message.

### R2 — Roles

**As a** parent, **I want** the system to know who is a student, a parent or an admin from day one, **so that** the parent and admin views can be added without migrating accounts.

Acceptance criteria:

1. `role` is a required field of a user with exactly the values `student`, `parent`, `admin`. Registration always produces `student`; no request can set another role in this epic.
2. Every API route declares the roles it admits. A signed-in user with another role gets a 403 with a French message. In this epic every route admits `student` only, except sign-out and « who am I », which admit any role.
3. The frontend reads the role from the session and, for a non-student, shows a single page saying the space is not available yet, with sign-out. No parent or admin pages exist.
4. A test proves that a route with no declared roles cannot be registered (the guard is opt-out impossible, not opt-in).

### R3 — Class catalog

**As a** parent, **I want** the classes on offer to come from files next to the courses, **so that** I can add a chapter or a class without a database migration or an interface that does not exist yet.

Acceptance criteria:

1. `courses/classes.yaml` declares the classes: each with an `id` (slug), a `title`, a `subject`, a `level` (e.g. « 5e secondaire »), a one-line `description`, an `open` flag, and an ordered list of `chapters` naming chapter directories under `courses/`.
2. A chapter directory is a `pack.md` plus a `curriculum.yaml`, as today. The curriculum's `id` is the chapter id used everywhere; the catalog refers to directories, the code refers to ids. A duplicate chapter id across directories fails startup with both paths named.
3. The catalog and every referenced chapter are validated at startup, like the curriculum today: a missing directory, a broken curriculum, or an unknown chapter reference aborts startup naming the file.
4. Chapter content stays out of the database. Progress references chapters by id; a chapter that disappears from the catalog leaves its progress rows in place and hidden.
5. `COURSE_PACK_PATH` and `CURRICULUM_PATH` are retired in favour of a single `COURSES_DIR` (default `courses/`). The health route reports the number of classes and chapters loaded.
6. The `chapitre_1` pair is registered in a first class « Mathématiques 5e » so the existing content works unchanged.

### R4 — List classes and enrol

**As a** student, **I want** to see the classes on offer and join one, **so that** the tutor teaches me the course I actually follow.

Acceptance criteria:

1. After sign-in the student lands on « Mes classes »: the classes she is enrolled in, each with title, subject, level and a summary of progress (chapters done / total, and the chapter she was in last, if any).
2. Below or beside it, « Classes disponibles » lists open classes she is not enrolled in, with title, subject, level and description, and a « Rejoindre » button. Closed classes are not listed.
3. Enrolling is one request and is idempotent: a second enrolment in the same class is a no-op, not an error. An enrolment records who and when.
4. Enrolling in a closed or unknown class is refused with a 404 or 409 and a French message; the interface never offers it.
5. A student with no enrolment sees the available classes and one sentence inviting her to join one; the page is never empty.

### R5 — Class page and chapter entry

**As a** student, **I want** to see where I am in each chapter of a class and open any chapter, **so that** I can work on what my next test covers.

Acceptance criteria:

1. « Mes classes » → a class opens its page: the chapters of the class in catalog order, each with title, the section count, and a state: « pas commencé », « en cours (n/m) », « terminé ». The chapter she worked on last is marked.
2. Every chapter is enterable regardless of the state of the others (chapters are independent). Entering a chapter opens the lesson screen of spec 002/003 scoped to that chapter, at the URL `/classes/{classId}/chapters/{chapterId}`.
3. The lesson screen shows the class and chapter it belongs to and a way back to the class page. The chapter strip, map, board, composer and voice controls are unchanged.
4. Opening a chapter the student is not enrolled for, or that is not in that class, gives a 404 page in French with a link to « Mes classes ».
5. The root URL `/` redirects to « Mes classes » when signed in and to sign-in otherwise.

### R6 — Progress owned by the server

**As a** student, **I want** my progress saved as I go, **so that** I can close the laptop and resume on the tablet tomorrow at the same section.

Acceptance criteria:

1. Progress is stored per (user, chapter) as the `{done, active}` record of spec 002, with an `updated_at`. It is created on first access and never deleted by this epic.
2. The section tools persist their transition in the same request that emits `section.start` / `section.done`, on both the text and the voice channel. A refused transition persists nothing. A turn that fails after a persisted transition still leaves the transition persisted (the event reached the browser or it did not; the record is the truth either way).
3. The browser no longer posts `progress` with a turn or a voice tool call, and no longer keeps it in `localStorage`. The turn and voice requests carry the chapter id; the backend reads the record. The `progress` field disappears from the request DTOs; the existing `localStorage` key is ignored and cleared on first visit.
4. The lesson screen receives the progress from the server when it opens and updates it from the section events, as today. The state message, the strip and the map show the same record on every device.
5. Resuming: opening a chapter with an active section starts a fresh conversation whose opening turn situates her in that section (the state message of spec 002 already does this). Opening a finished chapter offers a review. Nothing else is restored.
6. « Recommencer le chapitre » (the existing reset) clears the server record for that chapter after confirmation, as it clears the browser record today.
7. Voice usage rows (spec 003) carry the user id; the voice rate limit becomes per user, not per IP.

### R7 — Multi-chapter tutor

**As a** developer, **I want** the tutor built for the chapter the student opened, **so that** a class with several chapters needs no code change.

Acceptance criteria:

1. Prompt assembly, the course-pack marker substitution, the curriculum overview, the seed for a voice session and the tool context are all derived from the chapter id carried by the request. There is no default chapter.
2. The cached prefix is per chapter (prompt + that chapter's pack + that curriculum's overview). The smoke script takes a chapter id and still proves a cache hit on turn two.
3. The chapter overview route (`/api/chapters/current` today) becomes `/api/classes/{classId}/chapters/{chapterId}` and includes the student's progress. The class list and class page have their own routes.
4. Tool declarations do not vary per chapter. A test proves the declarations are identical for every chapter in the catalog.

## 4. Non-functional requirements

### 4.1 Architecture

1. A relational database behind a repository layer: users, sessions (or the token store the design chooses), enrolments, progress, voice usage. SQLite for development and tests, with the schema and queries kept portable to PostgreSQL. Schema changes go through migrations run explicitly, not on import.
2. Authentication and authorisation live in one dependency layer (`api/deps.py`, extending `VoiceAccess`): the routes declare admitted roles and receive the user; nothing else reads the cookie.
3. The turn pipeline (`TutorService.run_turn`) stays a pure function of its inputs plus the tool context. Reading and writing progress happens at the edges: the controller loads it, the section tools write it through the context. `services/path.py` and the reducer do not change.
4. The course catalog replaces the single-chapter accessor of `CourseService` with a `ChapterCatalog` keyed by chapter id, keeping the mtime-cached file reads and the startup validation.
5. Frontend routing is file-based under `src/routes/` with a layout route that checks the session in `beforeLoad` and exposes the user through the router context. The lesson screen becomes a route component that takes its class and chapter from the URL.
6. Nothing in this epic changes the SSE contract, the tool set, the card types or the voice bridge.

### 4.2 Performance

1. One turn costs at most two additional queries: load progress, save it if a section tool ran. The voice tool endpoint the same.
2. The per-chapter prompt prefix stays byte-stable across users and sessions: nothing user-specific (name, email, ids) enters the cached developer message. The student's first name may appear only in the trailing state message.
3. Sign-in, the class list and the class page each answer in under 200 ms locally with the catalog in memory.
4. Argon2id hashing takes under 300 ms on the development machine with the chosen parameters; the parameters are configuration.

### 4.3 Security

1. Passwords: Argon2id, per-user salt (built into the algorithm), parameters in configuration, hash migration path when parameters change (re-hash on successful sign-in).
2. Sessions: the cookie holds an opaque or signed identifier, never the user record; `httpOnly`, `SameSite=Lax`, `Secure` outside development, path `/`. Sign-out invalidates the session server-side. The server session secret comes from the environment and startup fails without it.
3. State-changing routes (register, sign-in, sign-out, enrol, reset, chat, voice) require the session cookie plus a same-origin check (`Origin`/`Sec-Fetch-Site`) or a CSRF token; the design picks one and a test proves a cross-origin POST is refused.
4. No email enumeration through registration, sign-in or timing: sign-in runs the hash even for an unknown email.
5. Every progress, enrolment and voice route is scoped to the signed-in user by the query, not by a client-supplied user id. A test proves user A cannot read or write user B's progress by URL.
6. Rate limits on sign-in and registration (R1.8) and the voice session mint (per user) share the limiter of spec 003, still process-local, documented as such.
7. Logs carry the user id, never the email, password or cookie. The `x-request-id` middleware stays.
8. The `OPENAI_API_KEY` and session secret are the only secrets; both come from `.env`; `.env.example` lists them.

### 4.4 Reliability

1. Migrations are idempotent and versioned; the backend refuses to start on a schema older than it expects, with a message naming the command to run.
2. A database write failure during a section tool is a tool error returned to the model (« je n'ai pas pu enregistrer, réessaie ») and no event is emitted, so the browser and the record cannot diverge.
3. The catalog is validated at startup; a broken chapter blocks startup as today. A chapter can be added or edited without restart, like the prompt and the pack (mtime cache); the catalog file itself requires a restart.
4. Losing the session (expiry, sign-out elsewhere) mid-lesson shows one French sentence and a sign-in link; the last completed turn is not lost from the server's point of view because progress is already saved.

### 4.5 Usability

1. All copy in French, tutoiement toward the student. Forms show one error per field, under the field, in French, before submission where possible (password length) and after (email taken).
2. Registration and sign-in fit on a phone screen; the class list is usable at 400 px.
3. The class page states the chapter she should continue first (« Reprendre » on the last-worked chapter), so the common case is one click from sign-in to the lesson.
4. Keyboard and screen-reader: forms have labels, the class cards are reachable, the current chapter is announced.

### 4.6 Known limitations carried forward

1. **No password reset and no email verification.** A forgotten password needs a developer today. Both are prerequisites to opening the product beyond the household.
2. **No parent-student link and no parent view.** The role exists; the relationship and the views come in later specs.
3. **Transcripts do not persist.** Resuming a chapter restarts the conversation at the active section.
4. **Classes are files.** Creating a class or uploading a chapter is a file edit and a restart.
5. **Rate limits are process-local**, as in spec 003.
6. **No data export or deletion** for the student, which the brief's privacy principle requires before real use.

## 5. Open questions for the design

1. Session storage: server-side session table versus signed stateless cookie. The requirement (R1.6 renewal, sign-out invalidation) is easier with a table; the design should weigh it against the extra query per request.
2. Whether the voice `Authorization: Bearer` header of spec 003 stays as an alternative to the cookie for the SDP-side calls, or the cookie alone suffices (the voice routes are same-origin through the proxy).
3. Whether `progress` should be keyed by enrolment rather than by (user, chapter), so that the same chapter in two classes (a repeat year) is two records. The requirement keys by (user, chapter) for simplicity; the design may add the enrolment id to the key if it costs nothing now.
4. SQLite versus PostgreSQL from day one for the household deployment, given the frontend's Cloudflare build target and where the backend will actually run.
