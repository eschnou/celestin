# Accounts, courses and progress

Students with accounts (spec 004) who own their courses (spec 005). This page covers who is signed
in, how courses and chapters are owned and reached, where progress lives, and how the frontend is
laid out around them. The authoring of a chapter is in [authoring.md](./authoring.md); its content
format in [chapters.md](./chapters.md).

## The shape

```
browser                                  backend                                   SQLite (data/celestin.db)
───────                                  ───────                                   ─────────────────────
/login · /register ──POST /api/auth/*──▶ AuthService ─────────────────────────────▶ users · sessions
_auth layout (ssr: false)                 │ cookie celestin_session (httpOnly) or Authorization: Bearer
  beforeLoad: GET /api/auth/me ──────────▶ current_user → require_roles(...)
/courses ──GET /api/courses─────────────▶ routes/courses.py ──────────────────────▶ courses ⋈ chapters · progress
/courses/$courseId ──GET /api/courses/{id}   · owned_course / owned_chapter (404 unless owner)
   + POST …/chapters ───────────────────▶ AuthoringRunner ─────────────────────────▶ chapters · authoring_runs
/courses/$courseId/chapters/$chapterId ─▶ GET …/chapters/{id} → overview + progress
   lesson ──POST /api/chat {course_id, chapter_id, history}──▶ open_lesson → TurnContext(save=…)
                                          section tools → ctx.commit() ──────────────▶ progress
/…/$chapterId/content ──GET/PUT …/content · pack · curriculum · source
```

The turn pipeline, the tool set, the SSE contract, the reducer and the voice bridge are the ones
described in [tutor-turn-pipeline.md](./tutor-turn-pipeline.md) and [voice.md](./voice.md). Specs 004
and 005 changed the edges: who is asking, which chapter, where it comes from, and where progress is
stored.

## Identity

- **Register** with email, password and first name; the account is a `student`. Emails are
  trimmed and lower-cased; passwords need 6 characters and may not contain the name or the local
  part of the email (`app/domain/password.py`). Hashes are Argon2id at the OWASP minimum
  (`ARGON2_MEMORY_KIB=19456`, `ARGON2_TIME=2`, `ARGON2_PARALLELISM=1`); a login re-hashes when the
  parameters changed.
- **Sessions** are rows: a 256-bit random token, stored as `HMAC-SHA256(SESSION_SECRET, token)`.
  The browser gets it in the `celestin_session` cookie (`HttpOnly`, `SameSite=Lax`, `Secure` unless
  `COOKIE_SECURE=false`, or, with `COOKIE_SECURE=auto`, unless the request came over plain HTTP; `Path=/`); any other client may send the same token as
  `Authorization: Bearer …`. Idle expiry `SESSION_IDLE_DAYS` (30), absolute `SESSION_ABSOLUTE_DAYS`
  (90); `last_seen_at` moves at most once an hour; expired rows are swept at startup and hourly.
  The cookie's own `Max-Age` is the *absolute* window, so a session renewed by use is never dropped
  by the browser before the server would reject it. Sign-out deletes the row, and is public and
  idempotent on purpose: an expired or unknown cookie must still be cleared.
- **Roles** are `student`, `parent`, `admin`. Every route declares the roles it admits through
  `require_roles(...)` in `app/api/deps.py`; `tests/unit/test_route_guards.py` refuses any route
  without it. Every route admits `student` only, except `logout`, `me`, `config` and the password
  change; the `/api/admin/*` routes admit `admin` only (spec 012, [admin.md](./admin.md)). A parent
  who signs in sees one "not yet" page; an admin lands on the dashboard.
- **Language** (spec 010, [i18n.md](./i18n.md)): a user has an interface language, `users.locale`
  (`fr` or `en`, migration `0006`; existing accounts read `fr`). Registration stores the one the
  visitor was reading (their `Accept-Language`; the body carries no language), sign-in and `me`
  return it, and `PATCH /api/auth/me` changes it. It decides the language of every message the
  server writes for that user; it never reaches the model.
- **Enabled** (spec 012): `users.enabled`. A disabled account cannot sign in and holds no session;
  `REGISTRATION_MODE` decides whether registration exists and whether a new account starts enabled.
  See [admin.md](./admin.md).
- **No enumeration**: sign-in answers « Email ou mot de passe incorrect. » for unknown and wrong
  alike and verifies a dummy hash for unknown emails; registration says the address cannot be used.
- **Rate limits**: sign-in and registration per IP *and* per address
  (`AUTH_ATTEMPTS_PER_WINDOW` per `AUTH_WINDOW_S`), voice minting per user. Process-local, as before.
- **CSRF**: `SameOriginMiddleware` refuses any mutating `/api` request whose `Sec-Fetch-Site` is
  not `same-origin`/`none` (or, when absent, whose `Origin` does not match the host). An origin
  listed in `CORS_ORIGINS` is accepted, so that setting actually works for a browser instead of
  being refused before CORS applies. Bearer requests skip the check: a header cannot be forged
  cross-site.

## Courses and chapters

A **course** belongs to one student: a name (1–80 characters) and a **subject** from the closed list
in `app/domain/subject.py`: four broad categories, grouped by how a subject is taught and answered rather than
by school discipline (the student's material carries the content; the subject only fixes the way of teaching,
writing and checking): **mathematics**, **sciences** (physics, chemistry, biology, general science), **languages**
(French and foreign languages) and **general courses** (« Cours généraux »: history, geography, general studies,
anything learnt from the course). All four are offered in French and in English. The subject cannot change.
See [chapters.md](./chapters.md) for their pack templates.
A course also has a **language**, `fr` or `en` (`courses.language`, migration `0007`; every existing
course reads `fr`): `POST /api/courses` takes `language` (missing means `fr`), refuses an unsupported
one or a language the subject is not offered in with `422 invalid_language`, and no route changes it
(`PATCH` refuses the field). `GET /api/subjects` lists the languages each subject is offered in and
the create form asks for it, starting on the interface language when the course can be written in
it; the course card and header show it by its own name. See [course-language.md](./course-language.md).
A student has at most `MAX_COURSES_PER_STUDENT` courses.

A **chapter** belongs to a course, in creation order (`position`), at most
`MAX_CHAPTERS_PER_COURSE`. It is created from a document (one PDF or photos, spec 006) and becomes ready when authoring adopts a
pack and a curriculum ([authoring.md](./authoring.md)). Chapters inside a course are independent;
the locked path lives inside a chapter ([chapters.md](./chapters.md)). Course and chapter ids are
uuid4 hex; the chat and voice DTOs only accept that form.

**Ownership** is in every query: `owned_course` and `owned_chapter` in `app/api/deps.py` join
`courses.user_id` to the signed-in user, and anything not owned, not found, or a chapter of another
course answers `404`, never `403`, so ownership is not probeable. `lesson_chapter` adds
`409 chapter_not_ready` for a chapter without content. Nothing is shared between students.

## Routes

| Route | Roles | Body | Answer |
|---|---|---|---|
| `POST /api/auth/register` | public | `{email, password, name}` | `201 {user}` + cookie; `202 {user, pending}` and no cookie in verification mode; `403 registration_closed` |
| `GET /api/auth/config` | public | — | `{registration, setup_required}`: the mode (`open`, `closed` or `verification`), and whether the instance still waits for its first administrator (spec 013) |
| `POST /api/auth/login` | public | `{email, password}` | `200 {user}` + cookie; `403 account_disabled` (right password, account not enabled) |
| `POST /api/auth/logout` | public | — | `204`, row deleted if any, cookie always cleared |
| `GET /api/auth/me` | any | — | `{user}` (`id, email, name, role, locale`) |
| `POST /api/auth/password` | any | `{current_password, new_password}` | `204`; `422 wrong_password` / `weak_password`; ends the user's other sessions |
| `GET /api/admin/users` · `PATCH …/{id}` · `POST …/{id}/reset-password` | admin | see [admin.md](./admin.md) | the dashboard's three routes |
| `PATCH /api/auth/me` | any | `{locale?}` (unknown fields refused) | `200 {user}`; `422` for an unsupported language; acts on the caller's own account only |
| `GET /api/subjects` | student | — | `{subjects: [{id, label}], limits}` (available subjects; text limits and document limits: `document_max_bytes`, `document_max_pages`, `document_min_pixels`, `document_types`) |
| `GET /api/courses` | student | — | `{courses: [summary]}`, newest activity first |
| `POST /api/courses` | student | `{name, subject}` | `201 summary`; `422 invalid_subject`; `409 course_limit` |
| `GET /api/courses/{id}` | owner | — | summary + `chapters: [row]` |
| `PATCH /api/courses/{id}` | owner | `{name}` | `200 summary` |
| `DELETE /api/courses/{id}` | owner | — | `204`, chapters and progress with it |
| `POST /api/courses/{id}/chapters` | owner | multipart `files` (one PDF, or photos in page order) | `202 row` (generating, stage `transcription`); `413 document_too_large`; `422 document_invalid` / `too_many_pages`; `409 chapter_limit`; `429 authoring_busy` / `authoring_quota` |
| `GET …/chapters/{ch}` | owner | — | lesson view: overview + `progress` + `course_id`, `course_name`, `subject`; `409 chapter_not_ready` |
| `GET …/chapters/{ch}/content` | owner | — | pack, full curriculum, source text, `source_kind`, `page_count`, `version`, `authoring_state`, `has_progress` |
| `PUT …/chapters/{ch}/pack` | owner | `{version, pack}` | `200 content`; `422 content_invalid` + `issues`; `409 stale_version` / `authoring_running` |
| `PUT …/chapters/{ch}/curriculum` | owner | `{version, curriculum}` | same |
| `PUT …/chapters/{ch}/document` | owner | multipart `files` | `202 row`; as the add route; `409 authoring_running` |
| `PUT …/chapters/{ch}/source` | owner | `{source_text}` (the corrected transcription) | `202 row`; `422 source_length`; `409 authoring_running`; `429 …` |
| `POST …/chapters/{ch}/retry` | owner | — | `202 row`; `409 nothing_to_retry` / `authoring_running` / `document_needed` (failed before the pages were read: the document is not kept) |
| `DELETE …/chapters/{ch}` | owner | — | `204` |
| `DELETE …/chapters/{ch}/progress` | owner | — | `204` |
| `POST /api/chat` | owner | `{course_id, chapter_id, history}` | SSE, unchanged |
| `GET …/chapters/{ch}/discussion` | owner | — | `{conversation}` or `{conversation: null}` (spec 007) |
| `POST …/chapters/{ch}/discussion` | owner | — | `201 {conversation}`; `429 discussion_quota` |
| `POST /api/discussion/turn` | owner | `{course_id, chapter_id, conversation_id, message}` | SSE; `409 conversation_closed` / `conversation_full` / `conversation_busy`; `422 empty_conversation_expected` |
| `POST /api/discussion/voice/turn` | owner | `{…, conversation_id, entries}` | `204` |
| `POST /api/voice/session` / `/tool` | owner | + `course_id`, `chapter_id` | as spec 003 |

A chapter **row** carries `position`, `title` (null until ready), `ready`, `section_count`,
`done_count`, `state` (`not_started`, `in_progress`, `done`), `last` (newest `progress.updated_at`,
feeds « Reprendre »), `authoring_state`, `authoring_stage` (kept on failure), `pages_done`,
`page_count` and the French `authoring_message`. The
course summary carries `chapters_done`, `chapters_total`, `last_chapter` and `generating`. Both
pages cost two queries: courses joined to the chapters' light columns, then the student's progress.

## Progress

The `progress` table is keyed by `(user_id, chapter_id)` and holds `done`, `active`, `updated_at`.
The controllers load it into the `TurnContext` with `save` bound to the store
(`deps.load_context`); the section tools call `ctx.commit(new_progress)`, which persists first and
adopts second. A failing write is a tool error the model reads (« Je n'ai pas pu enregistrer ta
progression. Réessaie. ») and no event is emitted, so the browser and the record cannot diverge. A
review (`start_section` on a done section) commits nothing. The browser no longer posts progress
or keeps it in `localStorage`; the authenticated layout removes any `celestin.progress.*` key it finds.

Every change of a chapter's content (an editor save, an authoring run adopted) deletes the chapter's
progress in the same transaction, so a stored record always matches the current curriculum. The
lesson view still repairs it on read, the same normalisation the turn context applies. `progress`
has a foreign key to `chapters`: deleting a chapter or its course deletes its progress. So do a
chapter's stored discussions, which carry foreign keys to both the student and the chapter.

Repositories (`app/db/repositories.py`) are synchronous and open one short session per call. The
routes run them through `run_in_threadpool`; the one write inside a section tool runs inline. That
is the seam to revisit if the database moves to PostgreSQL.

Voice usage is now a table (`voice_usage`, with the user id) as well as a log line.

## Database and migrations

`DATABASE_URL` (default `sqlite:///./data/celestin.db`, relative to `backend/`), SQLAlchemy 2, Alembic.

```sh
cd backend && uv run alembic upgrade head        # creates data/ , celestin.db and the schema
uv run alembic revision --autogenerate -m "…"    # after editing app/db/models.py
```

Tables: `users` (with `locale`, `enabled` and `last_seen_at`), `sessions`, `courses`, `chapters`, `authoring_runs`, `progress`,
`conversations` (spec 007, [discussion.md](./discussion.md)), `voice_usage`.
Migration `0003` (spec 005) dropped `enrolments` and recreated `progress` with its chapter foreign
key; no data was carried over. SQLite enforces foreign keys (`PRAGMA foreign_keys=ON`), which the
course and chapter cascades rely on.

The app refuses to start behind the migrations and names the command. Tests build the schema from
the models on an in-memory database and one test asserts the Alembic head matches the models.
Types are portable (`String`, `Integer`, `Float`, `JSON`, `DateTime(timezone=True)`; ids are hex
strings), so PostgreSQL is a URL change plus `upgrade head`.

## Frontend

```
src/routes/index.tsx                                            → /courses
src/routes/login.tsx · register.tsx                             public, server-rendered; follow the registration mode (no link when closed)
src/routes/_auth/admin/index.tsx                                « Administration » (spec 012, admin.md)
src/routes/_auth.tsx                                            ssr: false; beforeLoad: requireUser → context {user}
src/routes/_auth/settings.tsx                                   « Paramètres »: the language today (components/celestin/settings/)
src/routes/_auth/courses/index.tsx                              « Mes cours »: cards, « Nouveau cours »
src/routes/_auth/courses/$courseId/index.tsx                    the course: chapters, add, rename, delete; polls while preparing
src/routes/_auth/courses/$courseId/chapters/$chapterId/index.tsx   the lesson (components/celestin/lesson.tsx) or the preparation card
src/routes/_auth/courses/$courseId/chapters/$chapterId/discussion.tsx  discussion mode (components/celestin/discussion-panel.tsx)
src/routes/_auth/courses/$courseId/chapters/$chapterId/content.tsx « Contenu du chapitre »: pack, path, transcription, editors; `?tab=source`
```

`lib/auth.ts` holds the `me` query, `login`/`register`/`logout`, `requireUser` (throws a redirect
to `/login?redirect=…`) and `safeRedirect` (same-site paths only, default `/courses`).
`lib/tutor/courses.ts` holds the subject, course, chapter and content queries and every mutation;
`lib/tutor/chapter.ts` the lesson view. `useTutorSession({courseId, chapterId, initialProgress})`
starts from the progress that came with the chapter and resets through the API; `useVoiceSession`
takes the same scope. A lost session mid-lesson shows the error entry with a « Se connecter » link
back to the lesson.

**The course page** is built around one question, « where was I? ». From the top: the head (`course-header.tsx`: the
subject's icon, the name, subject · language · chapters finished, and a « ⋯ » menu holding « Renommer » and
« Supprimer le cours », so the destructive action is never beside the everyday ones); a **« Reprends où tu en étais »**
card (`course-resume.tsx`, only with two chapters or more) with the chapter to go back to and one big button
(`lib/tutor/featured-chapter.ts`: the chapter worked on last if unfinished, else one in progress, else the first not
started, titled « Prochain chapitre »; nothing when all is done); then the chapters as cards (`chapter-row.tsx`: number
or a check, the title, a state badge and « Section 3 sur 9 », a progress bar, **« Reprendre » / « Commencer » /
« Revoir »** as the one filled button and « Discuter » beside it; « Contenu du chapitre » and « Supprimer » are in the
card's « ⋯ » menu, whose delete opens a controlled `ConfirmDialog`); and a dashed « Ajouter un chapitre » card (also the
empty state). The section she is on is `done_count + 1`: the row does not carry the next section's title, which would
mean loading every curriculum for the list (a possible follow-up).

Course-page components live in `components/celestin/` (`course-card`, `create-course-form`,
`course-header`, `course-resume`, `chapter-row`, `add-chapter-form`, `document-picker`, `chapter-state-card`,
`confirm-dialog`, `progress-bar`, `subject-icon`); the content page's in
`components/celestin/content/` (`pack-view`, `pack-editor`, `curriculum-view`, `curriculum-editor`,
`source-editor`). The pack is rendered with `react-markdown` + `remark-gfm` + `remark-math`, raw HTML
skipped, links rendered as text, images dropped, formulas through `Math`.

The user menu (`components/celestin/user-menu.tsx`, in the courses bar and the chapter bar) leads to
« Paramètres » and signs out. The settings screen is a list of sections registered in
`components/celestin/settings/sections.ts`: the language and the password (spec 012).

The authenticated layout renders client-side only, so the guard runs where the cookie is and the
SSR server never needs to forward it. The Vite proxy target can be overridden with `BACKEND_URL`.

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/celestin.db` | Any SQLAlchemy URL. |
| `SESSION_SECRET` | — | Required, 16+ characters; startup fails without it. |
| `SESSION_IDLE_DAYS` / `SESSION_ABSOLUTE_DAYS` | 30 / 90 | |
| `COOKIE_SECURE` | `true` | `false` for `http://localhost`; `auto` is Secure only over HTTPS (the Docker image's default). |
| `ARGON2_MEMORY_KIB` / `ARGON2_TIME` / `ARGON2_PARALLELISM` | 19456 / 2 / 1 | |
| `AUTH_ATTEMPTS_PER_WINDOW` / `AUTH_WINDOW_S` | 10 / 900 | |
| `REGISTRATION_MODE` | `open` | `open`, `closed` or `verification` (spec 012, [admin.md](./admin.md)). |
| `MAX_COURSES_PER_STUDENT` / `MAX_CHAPTERS_PER_COURSE` | 30 / 40 | |
| `DISCUSSION_MAX_ENTRIES` / `DISCUSSION_MAX_CHARS` | 400 / 200000 | A stored conversation is capped; crossing either closes it. |
| `DISCUSSION_CONVERSATIONS_PER_DAY` | 30 | Per student. |
| `CHAPTER_TEXT_MIN_CHARS` / `CHAPTER_TEXT_MAX_CHARS` | 300 / 100000 | An edited text, trimmed; the maximum also bounds a transcription (`too_long`). |
| `PACK_MAX_CHARS` | 60000 | |
| `MAX_BODY_BYTES` | 1048576 | Declared or streamed bytes, refused before parsing (`413`). |
| `DOCUMENT_MAX_BYTES` / `DOCUMENT_MAX_PAGES` / `DOCUMENT_MIN_PIXELS` | 26214400 / 50 / 800 | The two upload routes only (`413 document_too_large`, `422`). |
| `DOCUMENT_WORKERS` / `DOCUMENT_RENDER_TIMEOUT_S` | 2 / 60 | The page-rendering process pool. |
| `PROMPTS_DIR` | `backend/prompts` | Tutor, subject, template and authoring prompts. |
| `TRUST_PROXY` | `false` | Read `X-Forwarded-For` for rate-limit keys. |

Authoring settings are in [authoring.md](./authoring.md) and [running-locally.md](./running-locally.md).

## Failure behaviour

| Situation | Answer |
|---|---|
| No or expired session | `401 not_authenticated`; the layout redirects to sign-in; mid-lesson, an entry with « Se connecter » |
| Wrong role | `403 forbidden`; the "not yet" page |
| Account not enabled (right password) | `403 account_disabled`, under the form; registration closed: `403 registration_closed` |
| Cross-origin mutating request (`POST`, `PUT`, `PATCH`, `DELETE`) | `403 cross_origin` |
| Email taken / weak password | `409 email_taken` / `422 weak_password`, under the field |
| Unknown or wrong password | `401 invalid_credentials`, same message and timing |
| Too many attempts | `429 rate_limited` |
| Course or chapter not owned, unknown, or chapter in another course | `404 not_found` |
| Chapter without content opened as a lesson | `409 chapter_not_ready`; the page shows the preparation state |
| Stored curriculum no longer valid | `500 chapter_unavailable`, `chapter_invalid` logged |
| Content edit invalid / stale | `422 content_invalid` with `issues` / `409 stale_version`; nothing written |
| Document unreadable, of another type, encrypted, too small, too many pages, too large | `422 document_invalid` / `too_many_pages` / `413 document_too_large`, under the picker; no chapter created |
| Retry of a chapter whose pages were never read | `409 document_needed`; the row offers « Redéposer le document » |
| Store write fails in a section tool | tool error to the model, no event, `progress_save_failed` in the log |
| Schema behind the migrations | startup aborts naming `alembic upgrade head` |

## Manual checklist

1. Visit `/courses` signed out: `/login?redirect=%2Fcourses`.
2. Register: « Mes cours » is empty with one sentence; « Nouveau cours », name and « Physique »: the course page.
3. « Ajouter un chapitre », choose a PDF or photos: the row reads « Lecture des pages… (n/N) », then « En préparation… », and turns « pas commencé » without a reload.
4. « Commencer »: Célestin's opening turn starts section 1; the strip shows « 1 · Leçon ».
5. Sign in from another browser: the course page shows « en cours » and « c'est ici que tu en étais ».
6. « Contenu du chapitre »: break a `## N.` heading and save: the issue shows, nothing is saved; a valid edit asks to confirm the progress reset.
7. A second account opening the first one's chapter URL gets « Cette page n'existe pas ».
8. Voice on the lesson page works with the cookie alone.
9. « Discuter » on a ready chapter opens a discussion; it survives a reload and never moves the done count ([discussion.md](./discussion.md)).
10. User menu, « Paramètres », choose English: the page and its title change at once, a reload keeps it, and signing out returns the sign-in page to the browser's language ([i18n.md](./i18n.md)).

Checked on 16 September 2026 through Playwright: 2 to 4 and 6; step 3 with photos on 18 September 2026.

## Logs

`auth_register`, `auth_login_ok`, `auth_login_failed` (with a reason, never the address),
`auth_logout`, `auth_rate_limited`, the admin and registration lines of [admin.md](./admin.md), `course_created`, `course_renamed`, `course_deleted`,
`chapter_created`, `chapter_deleted`, `document_received`, `document_refused`, `chapter_content_saved` (kind, version), `chapter_invalid`,
`progress_saved`, `progress_reset`, `progress_save_failed`, `sessions_purged`,
`conversation_started`, `conversation_closed`, `conversation_appended`,
`conversation_append_failed`, `discussion_quota`, and the `authoring_*`
lines of [authoring.md](./authoring.md); `turn_complete` and the `voice_*` lines carry `user_id` and
`chapter_id`. Never an email, a token, a password, a course name, a chapter title or any content.

`GET /api/health` re-reads the prompt files on every call, so a subject prompt or template deleted
or broken *after* startup shows as `"status": "degraded"` with the file in `prompts_unavailable`;
it also reports `subjects`, `authoring_model` and `authoring_active`.
