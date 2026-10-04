# 004 — Tasks

Phases are testable increments in dependency order. Each ends with a check the user can run. Requirement ids refer to `requirements.md`, section numbers to `design.md`. Tick tasks as they land; record design deviations under `## Fixes after verification

`/sdd:verify` found eighteen items; all but two were fixed in place. Backend tests went from 394 to
413, frontend from 161 to 173.

**Was breaking things**

1. **A fresh clone could not start.** `DATABASE_URL` defaults into a gitignored `data/` that nothing
   created, so the documented `alembic upgrade head` died with `unable to open database file`.
   `make_engine` now creates the parent directory, and `migrations/env.py` goes through it instead
   of building its own engine. Verified by running the whole setup against a missing directory.
2. **A failed background refetch tore down the live lesson.** The chapter route tested `isError`
   before `data`; React Query keeps the last good data on a refetch failure, so a tab switch during
   a network blip replaced a session in progress with a not-found card. `data` is now checked first,
   and the same stacking bug is fixed on both class pages (`isError && !data`).
3. **`not-found.tsx` was untracked** and would have been dropped by a `git add -u`, breaking both
   class routes. Staged.

**Correctness**

4. **Stored progress is repaired on every read**, not only inside the turn context. A renamed or
   removed section id no longer leaves a chapter counted as finished while the tutor still has it
   open, and an `active` that is also done is cleared for the page as well as for the turn.
5. **The cookie outlived nothing.** Its `Max-Age` was the idle window and was never re-issued, so a
   student working daily was signed out thirty days after sign-in and R1.6's ninety-day ceiling was
   unreachable. It is now the absolute window; the server still owns both expiry rules.
6. **An expired session stranded the student.** Nothing dropped the cached identity on a 401, so the
   guard kept passing. `setUnauthorizedHandler`, registered by the router, clears it on any 401 from
   any `/api` call, and the class-list loader gained the `.catch` its siblings had.
7. **The reset race.** `resetProgress` left `send()` unguarded during its round trip, so a click on
   « Étape suivante » started a turn that the wipe then orphaned. A `resettingRef` closes it.
8. **Sign-out could not clear a dead cookie.** It required a valid session, so an expired one 401ed
   and stayed in the browser. The route is public and idempotent now.
9. **Register and enrol were check-then-insert.** Both let the unique constraint decide instead, so
   a concurrent duplicate is a 409 or a silent no-op rather than a bare 500.
10. **`CORS_ORIGINS` was dead for browsers**: the same-origin guard refused every cross-site mutation
    before CORS applied. A listed origin is now trusted.
11. **Usage reporting could 500** despite "never fails the caller": the insert sat outside the try.
    The column also accepted twelve characters where its DTO allowed thirty-two (migration `0002`).

**Observability, restored coverage and polish**

12. `auth_login_failed` is emitted (with a reason, never the address), `progress_saved` is emitted,
    and `turn_complete` and `progress_save_failed` carry `user_id` and `chapter_id` via two new
    optional `TurnContext` fields.
13. `/api/health` re-reads pack and curriculum availability per call and answers `degraded` with
    `chapters_unavailable`. It had been reduced to counts fixed at startup, so a pack deleted after
    boot read as healthy.
14. The voice budget speaks about voice again instead of borrowing the sign-in copy.
15. The class routes carry `Cache-Control: no-store` like the chapter view; they hold per-user data.
16. **Tests that tasks 1.3, 4.5 and R7.4 claimed now exist.** A real `useTutorSession` hook test
    (initial progress, reset through the API, no storage access, the reset race, a failed reset), a
    lesson-route test for the refetch teardown, and restored coverage of the mtime cache *hit* and
    of the full-body "internals never cross the wire" scan, which had been narrowed to three key
    names on one section when the file was ported.
17. Stale references fixed in `chapters.md`, `frontend/CLAUDE.md`, `types.ts`, `ratelimit.py` and
    `accounts-and-classes.md`.

**Not fixed, deliberately**

- **R1.8's per-address registration limit is now implemented**, so the requirement/design divergence
  is gone. What remains unrecorded is nothing.
- **The `Origin`-versus-`Host` fallback** still compares against a `Host` that a proxy may rewrite.
  It only applies to clients that send no `Sec-Fetch-Site`, which current browsers always do, and
  the correct comparison needs a configured public origin that does not exist yet.

## Deviations`.

## Phase 0 — Database foundation

**Goal:** the backend has a schema, migrations, repositories and a startup check, with nothing yet using them. **Done when** `uv run alembic upgrade head` creates `backend/data/celestin.db`, the app refuses to start on an outdated schema, and the repositories round-trip in tests.

- [x] 0.1 Dependencies: `sqlalchemy>=2.0`, `alembic`, `pwdlib[argon2]`, `email-validator`; `uv sync`. `.gitignore`: `backend/data/`.
- [x] 0.2 `config.py`: `database_url`, `session_secret` (required at startup via `require_session_secret()`), `session_idle_days`, `session_absolute_days`, `cookie_secure`, `argon2_*`, `auth_attempts_per_window`, `auth_window_s`, `courses_dir` (replacing `course_pack_path` / `curriculum_path`, kept for one phase until 2.x removes them). `.env.example` gains `SESSION_SECRET`, `COOKIE_SECURE=false`, `DATABASE_URL`. Tests in `test_config.py`.
- [x] 0.3 `app/db/base.py`: engine from `database_url` (SQLite pragmas `foreign_keys`, `journal_mode=WAL`), `SessionLocal`, `Base`. `app/db/models.py`: the five tables of §4.1. Test `tests/unit/test_models.py`: `create_all` on `sqlite://`; role CHECK rejects `teacher`.
- [x] 0.4 Alembic: `backend/alembic.ini`, `app/db/migrations/env.py` reading `database_url` from settings, first revision `0001_initial`. `app/db/schema.py`: `check_schema(engine)` raising `SchemaOutdated` with the command. Test `tests/unit/test_migrations.py`: `compare_metadata` empty against head; `check_schema` raises on an empty DB and passes after `upgrade`.
- [x] 0.5 `app/db/repositories.py`: `UserRepository` (create, by_email, by_id, update_hash), `SessionRepository` (create, by_token_hash, touch, delete, purge_expired), `EnrolmentRepository` (add idempotent, exists, for_user), `ProgressRepository` (load, save upsert, clear, for_class), `VoiceUsageRepository` (add). Test `tests/unit/test_repositories.py` on an in-memory engine per test.
- [x] 0.6 `tests/conftest.py`: `db_engine` / `db_session` fixtures (`sqlite://`, `StaticPool`, `create_all`); `settings` fixture gains `session_secret="test-secret"`, `cookie_secure=False`, `database_url="sqlite://"`; `create_app` accepts an injected engine for tests (`app.state.engine`).
- [x] 0.7 `main.py`: lifespan opens the engine, runs `check_schema`, disposes on shutdown; `deps.get_db` yields a session that commits on success and rolls back on exception. Test in `test_app.py`: outdated schema aborts with the command in the message.

**Verify:** `cd backend && uv run alembic upgrade head` creates `data/celestin.db`; `uv run pytest` green; deleting the file and starting uvicorn prints the `alembic upgrade head` hint.

## Phase 1 — Authentication and roles

**Goal:** register, sign in, sign out, `me`, with roles enforced on every route and the CSRF and rate-limit guards in place. **Done when** the auth integration tests pass and `curl` can register and read `me` with the cookie.

- [x] 1.1 `domain/user.py` (`Role`, `User`), `domain/password.py` (`check_password`), `domain/errors.py` additions of §4.2 (`RateLimited` replaces `VoiceRateLimited`; `VoiceDisabled` stays). Tests `test_password.py`, `test_errors.py` codes.
- [x] 1.2 `services/auth_service.py` (§3.2): `PasswordHasher` wrapper over `pwdlib` with settings parameters, `AuthService.register/login/logout/authenticate`, dummy-hash verify, HMAC token hash, hourly touch, idle and absolute expiry. Test `test_auth_service.py` with a fake clock and a hasher spy.
- [x] 1.3 `api/deps.py`: `get_db`, `current_user` (cookie `celestin_session` or bearer), `require_roles(...)` with the `__celestin_roles__` marker, `StudentDep`, `AnyUserDep`; rate limiters on `app.state` (`login_limiter` IP+email, `register_limiter` IP). Remove `VoiceAccess`, `voice_session_budget`; `voice_limiter` keyed by `user.id`. Test `tests/unit/test_deps.py`: cookie and bearer both authenticate; expired → 401; wrong role → 403.
- [x] 1.4 `api/middleware.py`: `SameOriginMiddleware` (§3.3); registered in `main.py` for `/api` non-GET requests; CORS gains `allow_credentials=True`. Test `tests/unit/test_middleware.py`: foreign `Origin` 403, `Sec-Fetch-Site: same-origin` passes, missing headers with matching `Origin` passes, bearer skips, GET never checked.
- [x] 1.5 `api/schemas/auth.py` DTOs; `api/routes/auth.py`: register (201 + cookie), login (200 + cookie, `verify_and_update` re-hash), logout (204, row deleted, cookie cleared), me. `set_session_cookie` helper honouring `cookie_secure` and `session_idle_days`. Hashing and repository calls through `run_in_threadpool`.
- [x] 1.6 `tests/unit/test_route_guards.py`: every route outside `PUBLIC` carries the marker (R2.4). Wire `StudentDep` into the existing chat, chapters and voice routes so the test passes now (behaviour otherwise unchanged until Phase 2).
- [x] 1.7 `tests/integration/test_auth_endpoint.py`: the cases of §6; `conftest.make_client` gains `user=` (seed + cookie).
- [x] 1.8 Startup: `require_session_secret()`; `purge_expired` at startup and hourly task in the lifespan. Test in `test_app.py`.

**Verify:** `uv run pytest` green. With the backend running: `curl -c c.txt -X POST localhost:8000/api/auth/register -H 'content-type: application/json' -H 'origin: http://localhost:8000' -d '{"email":"a@b.be","password":"dix-caracteres!","name":"Léa"}'` → 201; `curl -b c.txt localhost:8000/api/auth/me` → the user; without the cookie → 401.

## Phase 2 — Catalog, multi-chapter tutor, server-owned progress

**Goal:** the backend serves classes from `courses/classes.yaml`, builds the tutor for the requested chapter, and reads and writes progress in the database. **Done when** a chat turn with `start_section` persists `active` and the class routes reflect it.

- [x] 2.1 `courses/classes.yaml` with « Mathématiques 5e » → `chapitre_1`. `domain/catalog.py` (`ClassDef`, `Catalog`, `parse_catalog`, `CatalogInvalid`). Tests `test_catalog_domain.py` with `tests/fixtures/catalog/*.yaml`.
- [x] 2.2 `services/catalog.py`: `PromptSource`, `ChapterSource` (from `CourseService`), `ChapterCatalog` (§3.5) with startup validation, duplicate chapter id detection naming both paths. Delete `CourseService`; `config.py` drops `course_pack_path` / `curriculum_path`. Tests `test_chapter_catalog.py`: real `courses/` loads; unknown dir; duplicate id; mtime reload of a pack.
- [x] 2.3 `tools/context.py`: `save` and `commit` (§3.6); `tools/section.py` uses `commit`; failure message. Tests in `test_section_tools.py`: persists through `save`; raising `save` leaves progress and raises `ToolValidationError`; `save=None` still works.
- [x] 2.4 `TutorService` / `VoiceService` / `history` / `prompt_service`: chapter id in, catalog lookups; `VoiceService.instructions(chapter_id)`. Remove `progress` from `ChatRequest`, `VoiceSessionRequest`, `VoiceToolRequest`; add `class_id`, `chapter_id`. Update `test_tutor_service.py`, `test_voice_service.py`, `test_chat_schema.py`, `test_voice_schema.py`, `test_history.py`, `test_prompt_service.py` (sha fixture unchanged: same rendering).
- [x] 2.5 `deps.enrolled_chapter` (404 unless enrolled and listed); `routes/chat.py`, `routes/voice.py`: load progress, bind `save`, chapter from the catalog; `/voice/usage` writes the row with `user.id`; `/voice/tool` echoes `progress`. Golden tests updated (`{class_id, chapter_id, history}`), persistence asserted through the repository, failing store → `ok:false` and no event, state message from the stored row.
- [x] 2.6 `api/schemas/classes.py` DTOs; `routes/classes.py`: list, enrol, detail, chapter view, reset (§3.9). Remove `routes/chapters.py` and its test. Integration `test_classes_endpoint.py` including cross-user isolation.
- [x] 2.7 `routes/health.py`: `classes`, `chapters`, `prompt_loaded`. `scripts/smoke.py`, `scripts/voice_smoke.py`, `scripts/probe.py`, `scripts/voice_probe.py`: `--chapter` (default first catalog chapter), temporary in-memory database and user. Run `smoke` for real: cache hit on turn two.
- [x] 2.8 `tests/unit/test_layering.py` green; `dump_schema` still runs.

**Verify:** `uv run pytest` green; `uv run python -m scripts.smoke` prints `CACHE OK`. With the backend running and the cookie from Phase 1: `POST /api/classes/maths-5e/enrol` → 204; `GET /api/classes` shows it enrolled; `POST /api/chat` with `{"class_id":"maths-5e","chapter_id":"suites","history":[]}` streams a `section.start`; `GET /api/classes/maths-5e/chapters/suites` shows `active: "suites"`; `sqlite3 data/celestin.db 'select * from progress'` shows the row.

## Phase 3 — Frontend: sign-in and navigation

**Goal:** the app has public sign-in and registration pages and an authenticated layout that guards everything else. **Done when** an anonymous visit to `/classes` lands on `/login?redirect=/classes`, registering lands on « Mes classes », and sign-out returns to `/login`.

- [x] 3.1 `lib/auth.ts`: `User`, `meQuery`, `fetchMe` (401 → null), `login`, `register`, `logout`, `requireUser` (§3.10). Tests `lib/__tests__/auth.test.ts`.
- [x] 3.2 `routes/login.tsx`, `routes/register.tsx`: `react-hook-form` + `zod` forms, French copy, password rule shown, API errors under the form, `redirect` search param honoured. Tests `routes/__tests__/login.test.tsx`, `register.test.tsx` (jsdom, mocked `lib/auth`).
- [x] 3.3 `routes/_auth.tsx`: `ssr: false`, `beforeLoad: requireUser`, context `{user}`, `AppBar` (« Célestin », name, « Se déconnecter »), `NotYetPage` for non-students, the one-time `localStorage` cleanup of `celestin.progress.*`. `routes/index.tsx`: redirect to `/classes`. `routes/_auth/classes/index.tsx` placeholder « Mes classes » so the guard is testable.
- [x] 3.4 `lib/tutor/client.ts` `readError`: `not_authenticated` surfaces with its code; `tutor-column.tsx` renders that error entry with a « Se connecter » link. Test in `tutor-column.test.tsx`.
- [x] 3.5 `__root.tsx`: 404 and error copy in French (« Cette page n'existe pas », « Mes classes »). `npx tsc --noEmit`, `npm run lint`, `npm test`.

**Verify:** run both processes; open `/classes` signed out → `/login?redirect=%2Fclasses`; register → « Mes classes »; reload keeps you signed in; « Se déconnecter » → `/login`; a hand-edited `parent` row → the not-yet page.

## Phase 4 — Frontend: classes, chapters, the lesson

**Goal:** a student enrols, sees chapter states, opens a chapter, works, and resumes on another device. **Done when** the manual flow of R4–R6 works end to end and no `localStorage` progress remains.

- [x] 4.1 `lib/tutor/classes.ts`: `classesQuery`, `classQuery`, `enrol`, `resetChapter`; `lib/tutor/chapter.ts`: `chapterQuery(classId, chapterId)` → `ChapterView`; types in `lib/tutor/types.ts`. Tests on request shapes.
- [x] 4.2 `routes/_auth/classes/index.tsx`: enrolled cards (`chapters_done/total`, « Reprendre : … » or « Commencer »), available cards with « Rejoindre » (enrol → invalidate), empty state sentence. Test `routes/__tests__/classes.test.tsx`.
- [x] 4.3 `routes/_auth/classes/$classId/index.tsx`: chapter rows with state badge, count, « Reprendre » / « Commencer » / « Revoir », the last-worked mark; 404 page on `not_found`. Test `class.test.tsx`.
- [x] 4.4 `routes/_auth/classes/$classId/chapters/$chapterId.tsx`: today's lesson body with a slim top bar (« ← Mes classes », class · chapter, name, « Se déconnecter »); loader `ensureQueryData(chapterQuery)`; `useTutorSession(chapter, {classId, chapterId, initialProgress})`. Delete `routes/index.tsx`'s lesson code (it only redirects now).
- [x] 4.5 `use-tutor-session.ts`: initial progress from props, no persistence effect, `resetProgress` → `resetChapter` then restart; delete `lib/tutor/progress-store.ts` and its test. `client.ts` `streamTurn({classId, chapterId, history})`. `voice/client.ts` and `use-voice-session.ts`: `{classId, chapterId}` instead of progress. Update `use-tutor-session.test.ts`, `client.test.ts`, `voice/__tests__/client.test.ts`, `use-voice-session.test.tsx`.
- [x] 4.6 `chapter-map.tsx` reset dialog copy: « Recommencer le chapitre » clears the server record. `chapter-strip` unchanged.
- [x] 4.7 `npx tsc --noEmit`, `npm run lint`, `npm test`; manual flow in the browser: register, enrol, open chapter, complete a section by text, sign in from a second browser profile, see the section done, voice session still works with the cookie.

**Verify:** the manual flow above; `localStorage` has no `celestin.progress.*` key; `sqlite3 data/celestin.db 'select user_id, chapter_id, active from progress'` matches the strip.

## Phase 5 — Documentation and hand-off

**Goal:** the next person can run, migrate and reason about accounts, classes and progress from the docs. **Done when** the documentation index lists the new page and the full check passes.

- [x] 5.1 `documentation/accounts-and-classes.md`: identity (sessions, cookie and bearer, roles, guards), the catalog file, progress ownership and the `commit` rule, migrations, the frontend route map, configuration, failure behaviour, manual checklist. Add to `documentation/index.md`.
- [x] 5.2 Update `documentation/chapters.md` (catalog replaces the env paths, progress lives in the database), `tutor-turn-pipeline.md` (request shape, progress loading, `commit`), `voice.md` (per-user auth and limiter, usage table), `running-locally.md` (migrations, `SESSION_SECRET`, `COOKIE_SECURE`, `DATABASE_URL`).
- [x] 5.3 `backend/CLAUDE.md` and `frontend/CLAUDE.md`: the database layer and its rules, the guard test, the catalog, the route map, the `ssr: false` layout, no `localStorage` progress.
- [x] 5.4 `specs/product.md` §6.6 / §11: note that accounts and classes exist and what remains (parent view, password reset). `specs/index.md` status.
- [x] 5.5 Run `/simplify` over the diff; address findings. *Applied: one `open_lesson` helper (enrolment check + progress load) called once per request off the event loop; tool execution in a thread so a progress write never blocks the stream; a joined session-and-user lookup per authenticated request; a pure-ASGI same-origin check; chapter ids fixed at startup and O(1) class membership; one progress query for the whole class list; `Slug`, `ROLES`, error bodies and `ProgressDTO.from_progress` single-sourced; `AuthService.open_session` and `hasher` public so tests use no private members; `VoiceUsageRepository.add(user_id, report, cost)`; `class_title` in the chapter view instead of a second query; shared `useSignOut` / `useAfterSignIn` / `redirectSearch`; one `ApiError` and `getJson`/`sendJson` for every client module; an `AuthPage` shell and one `NotFoundCard`; no scope refs in the two hooks; queries that do not retry 4xx and do not refetch what the loader just fetched. Skipped: `chapter_state` shared with `path.py` (the strip and the class page already agree because both count `done`), a dependency-based rate limiter, the `_locate` helper, the test-client boilerplate, an upsert in `ProgressRepository.save`, hashing the test password once per module, dropping `forgetLocalProgress` (R6.3 asks for it).*
- [x] 5.6 Full run: `uv run pytest`, `npm test`, `npx tsc --noEmit`, `npm run lint`, `uv run python -m scripts.smoke`, `uv run python -m scripts.voice_smoke`.

**Verify:** every command in 5.6 exits 0; `documentation/index.md` lists the new page.

## Fixes after verification

`/sdd:verify` found eighteen items; all but two were fixed in place. Backend tests went from 394 to
413, frontend from 161 to 173.

**Was breaking things**

1. **A fresh clone could not start.** `DATABASE_URL` defaults into a gitignored `data/` that nothing
   created, so the documented `alembic upgrade head` died with `unable to open database file`.
   `make_engine` now creates the parent directory, and `migrations/env.py` goes through it instead
   of building its own engine. Verified by running the whole setup against a missing directory.
2. **A failed background refetch tore down the live lesson.** The chapter route tested `isError`
   before `data`; React Query keeps the last good data on a refetch failure, so a tab switch during
   a network blip replaced a session in progress with a not-found card. `data` is now checked first,
   and the same stacking bug is fixed on both class pages (`isError && !data`).
3. **`not-found.tsx` was untracked** and would have been dropped by a `git add -u`, breaking both
   class routes. Staged.

**Correctness**

4. **Stored progress is repaired on every read**, not only inside the turn context. A renamed or
   removed section id no longer leaves a chapter counted as finished while the tutor still has it
   open, and an `active` that is also done is cleared for the page as well as for the turn.
5. **The cookie outlived nothing.** Its `Max-Age` was the idle window and was never re-issued, so a
   student working daily was signed out thirty days after sign-in and R1.6's ninety-day ceiling was
   unreachable. It is now the absolute window; the server still owns both expiry rules.
6. **An expired session stranded the student.** Nothing dropped the cached identity on a 401, so the
   guard kept passing. `setUnauthorizedHandler`, registered by the router, clears it on any 401 from
   any `/api` call, and the class-list loader gained the `.catch` its siblings had.
7. **The reset race.** `resetProgress` left `send()` unguarded during its round trip, so a click on
   « Étape suivante » started a turn that the wipe then orphaned. A `resettingRef` closes it.
8. **Sign-out could not clear a dead cookie.** It required a valid session, so an expired one 401ed
   and stayed in the browser. The route is public and idempotent now.
9. **Register and enrol were check-then-insert.** Both let the unique constraint decide instead, so
   a concurrent duplicate is a 409 or a silent no-op rather than a bare 500.
10. **`CORS_ORIGINS` was dead for browsers**: the same-origin guard refused every cross-site mutation
    before CORS applied. A listed origin is now trusted.
11. **Usage reporting could 500** despite "never fails the caller": the insert sat outside the try.
    The column also accepted twelve characters where its DTO allowed thirty-two (migration `0002`).

**Observability, restored coverage and polish**

12. `auth_login_failed` is emitted (with a reason, never the address), `progress_saved` is emitted,
    and `turn_complete` and `progress_save_failed` carry `user_id` and `chapter_id` via two new
    optional `TurnContext` fields.
13. `/api/health` re-reads pack and curriculum availability per call and answers `degraded` with
    `chapters_unavailable`. It had been reduced to counts fixed at startup, so a pack deleted after
    boot read as healthy.
14. The voice budget speaks about voice again instead of borrowing the sign-in copy.
15. The class routes carry `Cache-Control: no-store` like the chapter view; they hold per-user data.
16. **Tests that tasks 1.3, 4.5 and R7.4 claimed now exist.** A real `useTutorSession` hook test
    (initial progress, reset through the API, no storage access, the reset race, a failed reset), a
    lesson-route test for the refetch teardown, and restored coverage of the mtime cache *hit* and
    of the full-body "internals never cross the wire" scan, which had been narrowed to three key
    names on one section when the file was ported.
17. Stale references fixed in `chapters.md`, `frontend/CLAUDE.md`, `types.ts`, `ratelimit.py` and
    `accounts-and-classes.md`.

**Not fixed, deliberately**

- **R1.8's per-address registration limit is now implemented**, so the requirement/design divergence
  is gone. What remains unrecorded is nothing.
- **The `Origin`-versus-`Host` fallback** still compares against a `Host` that a proxy may rewrite.
  It only applies to clients that send no `Sec-Fetch-Site`, which current browsers always do, and
  the correct comparison needs a configured public origin that does not exist yet.

## Deviations

1. **Repositories open their own short session per call** rather than a request-scoped `get_db` dependency (design §3.7). A `yield` dependency's exit runs at a point FastAPI has changed across versions relative to a streaming response, and the section tools commit *during* the SSE stream; per-call sessions make that write independent of the request scope.
2. **Scripts need no database or user** (task 2.7 said "temporary in-memory database and user"): they drive `TutorService` and `VoiceService` directly with a `TurnContext` whose `save` is `None`, exactly as the unit tests do. `scripts/smoke.py` exports `load_catalog`, `pick_chapter` and `context_for` for the other three.
3. **`/api/health` drops `pack_loaded`, `curriculum_loaded` and `sections`** in favour of `prompt_loaded`, `classes`, `chapters` (design §3.9 listed the additions; the old fields had no meaning with several chapters).
4. **Page tests mount the real page components in a small test route tree** rather than the generated tree (task 4.2/4.3): the generated root renders a whole HTML document, which jsdom cannot mount inside a container. The guard, loaders and components under test are the real ones.
5. **Queries do not retry 4xx answers** (`retryOnce` in `lib/tutor/classes.ts`): a 404 or 401 is an answer, and retrying it with backoff delayed the not-found page by seconds.
6. **`ChapterView` carries `class_id`** in addition to the overview and progress, so the lesson route can label itself from one query.
