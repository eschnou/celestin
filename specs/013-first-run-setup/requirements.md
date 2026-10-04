# 013 — First-run setup: a self-contained install

## 1. Introduction

Today an instance cannot start without two environment variables (`OPENAI_API_KEY`, `SESSION_SECRET`) and an admin exists only through a shell command (`scripts/create_admin.py`, spec 012). That suits the developer, not a teacher or a parent who pulls a Docker image. This epic makes a fresh instance configure itself in the browser:

- `docker run -p 8080:8080 -v ./data:/data <image>` starts a working server with **no environment variables**.
- The first visitor opens `/setup` and creates the administrator. The administrator then pastes the OpenAI API key in the settings screen. From then on the application is fully usable.
- Secrets the operator should never type (the session secret, the key that encrypts the stored API key) are generated on first boot and kept on the data volume.
- Upgrading is pulling a newer image on the same volume: migrations run at start, after a backup of the database.

Environment variables keep working and win over everything the interface stores, so existing deployments and orchestrators change nothing.

Vocabulary:

- **Setup pending** — the `users` table is empty. The only state in which `/setup` works.
- **Effective key** — the OpenAI API key the application uses: `OPENAI_API_KEY` when set, else the key stored by an admin, else none.
- **Needs-key state** — the application runs and has no effective key.
- **Data volume** — `/data` in the image: database, `secrets/`, `backups/`, `caddy/`.
- **Secrets directory** — `SECRETS_DIR`, where the two generated secrets live. Unset outside the image.

Scope:

- `/setup` and the first-admin route; the registration and sign-in behaviour while setup is pending.
- Generated secrets (`SECRETS_DIR`).
- The OpenAI key: stored encrypted, admin-only settings section, test action, runtime swap of the three provider clients, the needs-key state.
- `COOKIE_SECURE=auto`.
- A backup before a pending migration, and a `scripts.migrate` command.
- The Docker image: no required variables, ownership of `/data`, defaults, compose file and documentation (`chore/docker` already holds the Dockerfile, Caddy and entrypoint).

Out of scope:

- Moving other settings (models, prices, limits, `REGISTRATION_MODE`) into the interface.
- Several replicas or workers (in-process limiters, authoring runs and the key holder assume one process), PostgreSQL.
- Email, password recovery by mail, a setup token, promoting users from the dashboard.
- Several API keys, per-user keys, usage or spend display, any provider other than OpenAI.
- Publishing the image (registry, tags, CI).
- Encrypting the database or the backups at rest.

## 2. Alignment with product vision

| Brief v2.0 | How this epic serves it |
|---|---|
| §5.7 Setup is minutes, not hours | Extended to the person who runs the application: pull, run, open the page, paste a key. |
| §10 Authoring cost per chapter | The key belongs to whoever runs the instance; the existing per-student limits and cost logs are untouched. |
| §3 Users (student, parent) | An administrator is an operator, not a student (spec 012); this epic gives the operator the screens to run the instance. |
| §5.3, §5.4, §8 invariants | Untouched: no tutor, tool, prompt or checker code changes. |

Deviations from specs and `CLAUDE.md`:

1. **Spec 012 « How admins are made: only `scripts/create_admin.py`; no route can promote ».** One route now creates an administrator: `POST /api/setup`, only while setup is pending, so it can never add an admin to an instance that has users. It promotes nobody. `create_admin.py` stays and works at any time. The 012 README and `documentation/admin.md` are amended (R2.6).
2. **`CLAUDE.md` « `OPENAI_API_KEY` and `SESSION_SECRET` are required ».** They are required unless a first-run mechanism provides them (R4, R6). `CLAUDE.md` and `documentation/running-locally.md` say so.
3. **Spec 012 « `REGISTRATION_MODE` is configuration, not a setting ».** Unchanged. Only the OpenAI key moves into the interface.

## 3. Requirements

### R1 — Setup pending and the setup screen

**As a** person who has just started a fresh instance, **I want** the first page to let me create the administrator, **so that** I need no command line.

Acceptance criteria:

1. Setup is pending exactly when the `users` table has no row. It is read from the database; there is no flag and no setting. Once a user exists the answer stays false for the life of the process (users are never deleted), so it may be cached from then on.
2. `GET /api/auth/config` (public) gains `setup_required: bool` next to `registration`.
3. `/setup` is a public, server-rendered route like `/register`. While setup is pending it shows the same fields and the same client-side password rule as registration (name, email, password) and the same minimal card with the product name and mark. When setup is not pending it redirects to `/login`.
4. While setup is pending, `/login`, `/register`, `/` and the `_auth` guard's redirect all lead to `/setup` (the signed-out pages read `setup_required` from the config query).
5. A successful setup signs the new admin in (spec 004 session and cookie), records the visitor's language as the account's (spec 010 R2.2), invalidates the cached auth config and lands on `/admin`.
6. While setup is pending the backend logs one `WARNING` line `setup_pending` naming the path `/setup`, at startup and on each hourly sweep, and nothing else about it. No secret is ever in that line.
7. All text is French or English per the interface language (spec 010); the new error codes (R2, R3) are in both catalogs.

### R2 — Creating the first administrator

**As a** first visitor, **I want** to become the administrator in one step, **so that** I can configure the instance.

Acceptance criteria:

1. `POST /api/setup {email, name, password}` creates an **enabled `admin`** and answers `201 {user}` with the session cookie, exactly like registration. It validates with the same code as registration and `create_admin.py` (`normalise_email`, `check_password`, name rules) and returns the same errors (`422`).
2. It succeeds only while setup is pending; otherwise `409 setup_done`, permanently, whatever the body.
3. The check and the insert are one transaction: two simultaneous calls on an empty database create exactly one admin, the other gets `409 setup_done`. A test pins it on SQLite.
4. It is throttled like registration (per client address and per email, spec 004 limiters) and subject to the same-origin check of mutating `/api/` requests.
5. There is no token: the first visitor wins. This is a decision for a small self-hosted project, stated in `documentation/docker.md` and `documentation/admin.md` with its remedies: finish setup right after the first start, or run `create_admin.py` before exposing the port (which closes `/setup`).
6. It is the only route that creates an admin; nothing promotes or demotes. The route-guard test (every route lists its roles) gains an explicit allow-list entry for the two public setup routes and fails for any other unguarded route. The spec 012 README and `documentation/admin.md` record the deviation.
7. `log.info("setup_completed")` with the new user id; no email, no password.

### R3 — Registration while setup is pending

**As a** visitor of a fresh instance, **I want** registration not to steal the setup, **so that** the instance does not end up with a student and no admin.

Acceptance criteria:

1. While setup is pending, `POST /api/auth/register` is refused with `409 setup_required` before any account is created, in every registration mode (`open`, `closed`, `verification`).
2. `POST /api/auth/login` while setup is pending behaves as today (no account, `invalid_credentials`).
3. `scripts/create_admin.py` and `scripts/seed.py` create users directly, so running either ends the pending state.
4. An instance that has users but no admin (an existing deployment, upgraded) is **not** setup-pending: `/setup` answers `409 setup_done` and `create_admin.py` remains the way to get an admin (R11.2).

### R4 — Secrets generated on first boot

**As an** operator, **I want** the session secret generated for me, **so that** I do not have to invent and store one.

Acceptance criteria:

1. A setting `SECRETS_DIR` (path, unset by default). The image sets it to `/data/secrets`.
2. Session secret, in order: `SESSION_SECRET` when set (at least 16 characters, as today); else, when `SECRETS_DIR` is set, the file `session_secret` in it, **created on first boot** when missing; else startup fails with `MissingSessionSecret` exactly as today.
3. The encryption key (R5) is the file `encryption_key` in `SECRETS_DIR`, created on first boot when missing. There is no environment override and no fallback: without `SECRETS_DIR` the application has no encryption key and cannot store an API key (R5.8).
4. Both files hold at least 256 bits from the operating system's CSPRNG, are created atomically (`O_CREAT|O_EXCL`) with mode `0600` in a directory of mode `0700`, and are never overwritten.
5. An existing file that cannot be read or has the wrong size stops startup naming the file and what to do. It is never regenerated silently: that would sign everyone out or destroy the stored key.
6. The two are independent. Deleting `session_secret` signs everyone out (sessions no longer verify) and leaves the stored API key readable. Deleting `encryption_key` makes the stored API key unreadable: the application treats it as absent (R5.2 `stored_unreadable`), reports it, and does not crash.
7. Neither secret is ever logged, sent in a response, written to the database or included in an error message.
8. A backup of the database file alone gives neither the means to forge a session nor the stored API key. A backup of the whole data volume contains both, so it is as sensitive as the host; `documentation/docker.md` says so in one sentence.
9. With `SECRETS_DIR` unset and the variables set (every existing deployment, local development, the whole test suite) nothing changes.

### R5 — The administrator stores the OpenAI key

**As an** administrator, **I want** to paste the OpenAI key in the settings screen, **so that** the instance works without a restart or a shell.

Acceptance criteria:

1. A settings section « OpenAI », visible only to an admin. `SettingsSection` (spec 010 `settings/sections.ts`) gains an optional `roles` restriction; the shell filters on it. Students and parents never see it and the backend refuses them independently (below).
2. `GET /api/admin/openai-key` (`require_roles("admin")`) returns `{source: "environment" | "stored" | "none", last4: string | null, stored_unreadable: bool, can_store: bool}`. It never returns the key, the ciphertext or more than the last four characters.
3. `PUT /api/admin/openai-key {key}` trims the key, refuses an empty or whitespace-containing one or one over 256 characters (`422 invalid_openai_key`), checks it with the provider (R5.7), and only when accepted stores it and makes it the effective key (R6). A key the provider rejects (`401`) is `422 openai_key_rejected` and changes nothing; a provider that cannot be reached is `502 provider_unavailable` and changes nothing.
4. The stored key is encrypted with authenticated encryption under the `encryption_key` secret; the plaintext is never persisted. It lives in a new table `app_settings` (`key`, `value`, `updated_at`, `updated_by`) by migration `0009`, with the last four characters kept beside it for display.
5. `DELETE /api/admin/openai-key` removes the stored key; the needs-key state follows if no environment key exists (R7).
6. When `OPENAI_API_KEY` is set: `source` is `environment`, the section is read-only and says so, and `PUT` and `DELETE` answer `409 key_from_environment`.
7. `POST /api/admin/openai-key/test` checks the **effective** key with the provider without consuming tokens (a models call) and answers `{status: "ok" | "rejected" | "unreachable", models: [{id, visible}]}` for the configured tutor, authoring, transcription and voice models; model visibility is informational and never turns `ok` into a failure. The call lives in `app/providers/` (the only place that imports `openai`) behind a protocol so tests use a fake.
8. When there is no encryption key (`SECRETS_DIR` unset): `can_store` is false, `PUT` answers `409 storage_unavailable`, and the section tells the admin to set `OPENAI_API_KEY`.
9. Key routes are throttled per admin (the spec 012 password-change limiter pattern), subject to the same-origin check, and log `openai_key_changed` (actor id and `set` or `removed`), never the key, its length or its last characters.
10. All strings and error codes in both languages. The input is a password-type field with no autocomplete, cleared after saving; the section shows the source, the last four characters, « Test the key » and « Remove ».

### R6 — The effective key and the runtime swap

**As an** administrator, **I want** a key change to take effect at once, **so that** I never restart the container.

Acceptance criteria:

1. The effective key is `OPENAI_API_KEY` when non-empty, else the stored key, else none. Resolution does not read the database on every request: the effective key is held in memory and replaced when a key is stored or removed.
2. The tutor client, the authoring client (which also serves transcription) and the realtime client are built from the effective key. Storing or removing a key replaces them without a restart. Each call resolves the current client when it starts: a call already in flight finishes with the key it started with, the next call uses the new one. No call ever sees a partly built set.
3. `create_app` still accepts injected clients and engines for tests; the existing fakes and fixtures keep working without edits beyond what R7.1 removes.
4. The CLI scripts (`probe`, `smoke`, `voice_*`, `*_eval`, `seed`) keep reading the key from the environment through `require_api_key()`; they are not affected.
5. The provider boundary is unchanged: nothing above `app/providers/` imports `openai` or learns which key source is in use.

### R7 — Running without a key

**As an** administrator or a student on a fresh instance, **I want** a clear answer when the key is missing, **so that** nothing fails obscurely.

Acceptance criteria:

1. Startup no longer requires a key. With no effective key the backend starts in the needs-key state and logs one `WARNING` `ai_not_configured` at startup. The session-secret requirement is R4's.
2. Routes that need the provider are refused with `503 ai_not_configured` **before any side effect**: `POST /api/chat`, the discussion turn route, `POST /api/voice/session`, and every route that starts authoring (adding a chapter, replacing a document, retrying, resetting). Nothing is stored and no upload is read. The message names the next step: for an admin, the settings screen; for anyone else, to ask the administrator.
3. Everything that does not call the provider keeps working: sign-in, course and chapter lists, reading and editing a pack or a path, progress, settings, the admin dashboard.
4. `GET /api/health` gains `ai_configured: bool`. `voice` is true only when voice is enabled **and** a key exists, so the mic stays inert (frontend `useHealth`). `status` keeps its meaning (prompt files); the container healthcheck passes in the needs-key state.
5. While the needs-key state lasts, the admin dashboard shows a banner linking to the settings screen. Student pages show the `503` message through the existing error path; no new student page.
6. Chapters already being authored when a key is removed fail with the existing provider-failure path (`provider_unavailable` family), not a crash; the run is retryable once a key exists.

### R8 — `COOKIE_SECURE=auto`

**As an** operator on plain HTTP, **I want** sign-in to work without knowing about cookie flags, **so that** a LAN address or `localhost` works out of the box.

Acceptance criteria:

1. `COOKIE_SECURE` accepts `true`, `false` and `auto`. The application default stays `true`; the image sets `auto`.
2. In `auto` the session cookie, when set and when deleted, is `Secure` exactly when the request reached the application over HTTPS, as reported by the trusted proxy (`X-Forwarded-Proto` from the proxy in front of the process; the image's Caddy always is). The same trust rule as the client address (`TRUST_PROXY`) applies; a client's own `X-Forwarded-Proto` never counts when the proxy is not trusted.
3. `true` and `false` behave as today. Tests pin all three values, over HTTP and over HTTPS.
4. `documentation/docker.md` states the consequence: behind an HTTPS proxy or Caddy-managed TLS the cookie is `Secure`; on plain HTTP it travels in clear, as the password does.

### R9 — A backup before a migration

**As an** operator upgrading by pulling a new image, **I want** the database copied before it is migrated, **so that** a bad migration does not cost the students their work.

Acceptance criteria:

1. A command `python -m scripts.migrate` replaces the entrypoint's bare `alembic upgrade head`. When a migration is pending on a SQLite database that already has a revision, it first copies the database with SQLite's online backup API (consistent while the file is in use) to `backups/` beside the database file, named with a UTC timestamp and the revision it holds, then migrates.
2. No backup is made for a new database (no revision) or one already at head. For a non-SQLite URL the command migrates and logs that it made no backup.
3. The most recent `MIGRATION_BACKUPS_KEPT` backups (default 5) are kept; older ones are removed. The directory is `0700` and the files `0600`: they hold emails and password hashes.
4. A failed backup (disk full, unwritable) stops the command with the reason and leaves the database untouched; the container does not start.
5. The startup schema check (`check_schema`, spec 004) is unchanged: an older image on a newer database is refused with the existing message, which `documentation/docker.md` follows with how to restore a backup.
6. `alembic upgrade head` run by hand still works and takes no backup. A test covers: backup made and migrated; fresh database untouched; at head, nothing; retention; failure aborts before migrating.

### R10 — The image needs nothing from the operator

**As an** operator, **I want** one command to start, **so that** I can try Célestin in a minute.

Acceptance criteria:

1. `docker run -p 8080:8080 -v ./data:/data <image>` starts with no `-e`. The setup page is reachable; after setup and a key (R1 to R7) the application is fully usable.
2. The entrypoint starts as root only to make `/data` writable by the unprivileged user (uid 10001) when it is not already, then runs migrations and all three processes (uvicorn, Node, Caddy) as that user. This works for a named volume and for a bind-mounted host folder owned by anyone. When `/data` cannot be made writable (read-only mount) the container stops with a message that says why. Started with `--user`, it skips the ownership step and requires a writable `/data`.
3. The image sets `DATABASE_URL=sqlite:////data/celestin.db`, `SECRETS_DIR=/data/secrets`, `COOKIE_SECURE=auto`, `TRUST_PROXY=true` and Caddy's data under `/data/caddy`. No variable is required; the entrypoint's present checks for `OPENAI_API_KEY` and `SESSION_SECRET` are removed.
4. The data volume layout is `celestin.db`, `secrets/`, `backups/`, `caddy/`, documented.
5. Migrations run at every start through `scripts.migrate` (R9).
6. The `HEALTHCHECK` passes while setup is pending and in the needs-key state.
7. `docker-compose.yml` has no required variable and no `COOKIE_SECURE` override. `documentation/docker.md` is rewritten around the three steps (run, setup, key), the environment overrides, upgrading by pulling a tag, restoring a backup, the whole-volume sensitivity (R4.8) and the first-visitor risk (R2.5).
8. Verified by building and running the image on a fresh volume and on a bind-mounted folder owned by another user: setup, key, a tutor turn (manual, real key), restart keeps the data and the key, upgrade from an image built at the previous revision keeps the data and leaves a backup.

### R11 — Existing deployments are unaffected

**As an** operator of an instance already running with environment variables, **I want** nothing to change, **so that** upgrading is safe.

Acceptance criteria:

1. With `OPENAI_API_KEY` and `SESSION_SECRET` set and users in the database, the instance behaves as before: no `/setup`, the key section read-only (`source: environment`), cookies as `COOKIE_SECURE` says.
2. Users but no admin: `/setup` is closed (R3.4); `create_admin.py` works as before.
3. Migration `0009` is additive, has a working `downgrade`, uses no SQL-expression server default on an existing table (spec 012's `users.enabled` lesson: SQLite rebuilds the table and cascades), and a test upgrades a populated `0008` database and checks every course, chapter and progress row survives.
4. A fresh non-Docker run with the variables set also starts setup-pending (empty `users`); `running-locally.md` says so. `seed.py` and `create_admin.py` still work and end the pending state.
5. `REGISTRATION_MODE`, the limits, the models and every other variable are read exactly as before.

## 4. Non-functional requirements

### 4.1 Architecture

1. **The provider boundary holds.** Only `app/providers/` imports `openai`; the key check and the models call are new members of it behind a protocol with a scripted fake. Services and routes learn nothing about the key's source.
2. **The composition root owns the clients.** `create_app` builds a holder of the three clients, rebuilt on key change; dependencies and the authoring agent resolve the current client per call instead of capturing one at construction. No module-level global.
3. **Setup and key logic are services, routes stay thin.** Setup lives next to registration in `AuthService` (same hasher, same validation, same session opening); key storage is its own small service over a repository for `app_settings`. The repository follows spec 004's pattern (a session per call, no ORM objects leaving it).
4. **Vetted cryptography only**: an authenticated-encryption primitive from a maintained library (a new dependency, justified in the design), no home-made scheme. The secrets module has no other job.
5. **Single process stays the rule.** The held key, the setup cache and the limiters are in memory; the design says so and the documentation repeats it.
6. Migration `0009` follows the `NNNN_slug` convention; the startup schema check and `tests/unit/test_migrations.py` keep passing.
7. The frontend adds a route and a settings section through the existing registries (`routes/`, `settings/sections.ts`); no new state library, no change to the query cache conventions beyond one invalidation.
8. Existing French and English catalogs are extended, never reshaped; `i18n:check` and the English-sweep tests keep passing.

### 4.2 Performance

1. Per-request cost is unchanged: the effective key and the setup answer are read from memory after first use; the database is read at most once per process for each, and again only when a key is stored or removed.
2. A key change is visible to the next call without a restart and without a measurable pause.
3. The pre-migration backup is as large as the database and runs only when a migration is pending.

### 4.3 Security and privacy

1. **The key never leaves the server.** No route, log line, error body, health answer, test report or backup of the database alone reveals it. The interface shows at most the last four characters. Provider error text is never forwarded to the client (existing `translate` rule) and never logged with a key.
2. **Secrets at rest**: `0600` files in a `0700` directory, generated from the OS CSPRNG, independent of each other (R4). The API key is encrypted with authenticated encryption; tampered ciphertext reads as `stored_unreadable`, never as another key.
3. **Admin only**: key routes require the `admin` role, enforced by the route-guard test; the settings section is hidden from other roles as a courtesy, not as the control.
4. **First visitor wins is an accepted risk** (R2.5). Its blast radius is bounded: it exists only while `users` is empty, closes permanently with the first account, and cannot affect an instance that has users.
5. `/setup` and the key routes are throttled and under the same-origin check (spec 004).
6. `COOKIE_SECURE=auto` trusts only the configured proxy's forwarded protocol (R8.2); the cookie stays `HttpOnly` and `SameSite=Lax`.
7. Backups contain personal data: restricted permissions, kept out of the image and the build context (`.dockerignore` already excludes `backend/data`), and counted in the documentation's backup sentence.
8. Nothing new is logged about a person: `setup_completed` and `openai_key_changed` carry ids and an action only.

### 4.4 Reliability and quality

1. Setup is atomic (R2.3); a key change is atomic (a failed check or write leaves the previous key effective); the client swap is atomic (R6.2).
2. Startup failures name the file or setting and the remedy: unreadable secret file, unwritable `/data`, schema behind, failed backup.
3. A missing or broken secret never causes silent regeneration (R4.5); an unreadable stored key degrades to the needs-key state instead of crashing (R4.6, R7).
4. The offline suite drives all of it with fakes: setup (success, repeat, race, registration refused while pending, existing users without admin); secrets (generation, permissions, existing file, wrong size, independence, env precedence, `SECRETS_DIR` unset); the key routes (roles, never returns the key, env read-only, no encryption key, invalid, rejected, unreachable, tampered ciphertext); the swap (a call in flight keeps its key, the next uses the new one); needs-key refusals before side effects; `COOKIE_SECURE` three values over two schemes; `scripts.migrate` (R9.6); migration `0009` on a populated `0008` database; the route-guard allow-list; both catalogs (`error_messages_*` fixtures extended); the English sweep on `/setup` and the OpenAI section.
5. Backend and frontend suites, `tsc`, lint and `i18n:check` pass; `smoke` and the probes are unaffected and unchanged.
6. The image is verified as R10.8 describes; the entrypoint's ownership step is covered by a scripted run on a bind mount owned by another uid.

### 4.5 Usability

1. The default path has no instructions to read: the setup page explains in one sentence that this account administers the instance; the OpenAI section explains where to get a key in one sentence and one link; the dashboard banner and the `503` message say what to do next.
2. The setup form is the registration form, not a wizard: three fields, one button.
3. Error messages are in the visitor's interface language and name the action (« Ask your administrator », « Open Settings »).
4. The new screens meet the accessibility level of the existing forms: labelled fields, error text tied to the field, the key field not announced back, focus on the first error.
5. `docker run` followed by the browser is the whole documented quick start; every environment variable stays documented as an override, not a prerequisite.
