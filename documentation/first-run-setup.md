# First-run setup

Spec 013. A fresh instance configures itself in the browser: no administrator to create from a shell, no
secret to invent, no AI provider key in the environment. How the Docker image uses it is in
[docker.md](./docker.md); the administrator's own pages are in [admin.md](./admin.md).

## The first-run state

An instance is **waiting for its first administrator** exactly when the `users` table is empty
(`AuthService.setup_required()`: read from the database, and once an account exists the answer is cached
as « no » for the life of the process, since accounts are never deleted). `GET /api/auth/config` says so
(`{registration, setup_required}`) and the signed-out pages follow:

- `/login` and `/register` lead to `/setup`; `/setup` leads to `/login` once an account exists.
- `POST /api/auth/register` answers `409 setup_required` in every registration mode: otherwise the
  first person to register would be a student, `/setup` would close for good, and the instance would have
  no administrator and no key.
- The backend logs a `setup_pending` warning (path `/setup`) at startup and every hour until the first
  account exists.

## `POST /api/setup`

Public. `{email, name, password}` (the registration fields, the same validation and password rule) creates
an **enabled admin**, signs them in (`201 {user}` and the session cookie) and records the visitor's language
as theirs. It succeeds only while the instance is waiting: the check and the insert are one SQL statement
(`INSERT … SELECT … WHERE NOT EXISTS (SELECT 1 FROM users)`), so two simultaneous calls create one admin and
the other gets `409 setup_done`. Throttled like registration; the same-origin check applies.

**There is no setup token: the first visitor wins.** That is a decision for a small self-hosted project.
Its limits are narrow: it exists only while the instance has no account, an instance that has users but
no admin (an upgrade of an older deployment) answers `409 setup_done`, and registration cannot end the state
as a student. If an instance is reachable before its owner has finished the setup, a stranger could take
it: finish the setup right after the first start, or run `scripts.create_admin` before exposing the port
(which ends the state). This is the one route that creates an admin, and the one deviation from spec 012's
« only the script »; nothing promotes or demotes.

The page (`routes/setup.tsx`) is the registration form with another button. After success it caches the user,
re-reads the config and the health, and lands on `/admin`, where a banner asks for the AI provider (spec 014: [ai-providers.md](./ai-providers.md)).

## Secrets generated on first boot

`SECRETS_DIR` (unset by default; the image sets `/data/secrets`) holds two files, 64 hexadecimal characters
each, created atomically (`O_EXCL`) with mode `0600` in a `0700` directory and never overwritten
(`app/secret_files.py`):

| File | Used for | If it is deleted |
|---|---|---|
| `session_secret` | keys the session-token hash | everyone is signed out; the stored provider keys stay readable |
| `encryption_key` | AES-256-GCM encryption of the stored provider keys | the stored keys are unreadable (reported, the app runs without them); nobody is signed out |

`SESSION_SECRET` in the environment wins for the session secret (16 characters or more, as before). There
is no environment override for the encryption key: without `SECRETS_DIR` nothing can be stored and the
« AI provider » section says to use `OPENAI_API_KEY`. A file that exists but is unreadable or the wrong size stops
the start, naming the file; it is never regenerated silently. With `SECRETS_DIR` unset and the variables
set (local development, every older deployment, the tests) nothing changes.

**A copy of the database alone gives neither a session nor a provider key.** A copy of the whole volume
contains both secrets, so it is as sensitive as the host itself.

## The AI provider and its key

Spec 013 stored one OpenAI key; spec 014 generalised it to a provider (address, key, API style) and a model per
role, all in [ai-providers.md](./ai-providers.md). What 013 established still holds:

- The effective setting is the environment's when set, else what an administrator stored, else a built-in
  default. `OPENAI_API_KEY` set in the environment is read-only in the interface.
- **Stored** in `app_settings`, encrypted with the `SECRETS_DIR` encryption key, never returned: the routes give
  a source and the last four characters. The 013 row `openai_api_key` (`{"v": 1, "ct": …, "last4": "…"}`) is
  still read as the default connection's key, and mirrored on save while the default connection is OpenAI's.
- **Routes** (all `admin`, throttled per admin, same-origin): `GET/PUT /api/admin/ai`,
  `GET /api/admin/ai/models`, `POST /api/admin/ai/test`. The spec 013 `/api/admin/openai-key*` routes are gone.
- A save is validated against the provider (`GET /models`, free) before anything is written, and the clients are
  swapped last: a rejected key (`422 ai_key_rejected`) or an unreachable server (`502`) changes nothing.
- The **settings section** (`settings/ai-section.tsx`, admin only: `SettingsSection.roles`) replaces the
  « OpenAI » one.

## Changing the provider without a restart

`ProviderHub` (`app/providers/hub.py`) owns one client per role (tutor, authoring, transcription, and Realtime when
voice is on) and hands out three **proxies**, `app.state.llm`, `authoring_llm` and `realtime`, which look up the
current client each call. Applying a new configuration (`hub.build` then `hub.install`, so one that cannot be built
is refused before anything is stored) swaps the clients under the proxies; a call that already resolved its client
finishes with it. With no configuration a proxy raises `AiNotConfigured`. `AiSettingsService` drives it. Single
process: the hub, the setup cache and the limiters are in memory.

## No provider: the needs-config state

The application starts without a usable provider (none of tutor, authoring and transcription resolves). The seven
routes that call it answer `503 ai_not_configured` (« ask whoever runs this instance to choose the AI provider »)
through the `require_ai` dependency, behind authentication (a visitor who is not signed in gets `401`, an admin
`403`): `POST /api/chat`, `POST /api/discussion/turn`, `POST /api/voice/session`, adding a chapter, replacing its
document, editing its source text and retrying it. FastAPI has read the request body by then; nothing is stored or
processed. `tests/integration/test_needs_key.py` pins the list. Everything else works: sign-in, courses and
chapters, reading and editing a pack, progress, settings, the dashboard.

`GET /api/health` reports `ai_configured` and the effective models (`null` while unconfigured), and `voice` is true
only when voice is enabled **and** a Realtime-capable voice connection exists (the mic stays inert). The dashboard
shows a banner linking to the settings while `ai_configured` is false. A configuration removed while a chapter is
being prepared fails that run through the provider-failure path (`AiNotConfigured` is in the agent's
`PROVIDER_ERRORS`): the student can retry once a provider is configured.

## `COOKIE_SECURE=auto`

`COOKIE_SECURE` accepts `true` (the application default), `false` and `auto` (the image's default). In
`auto` the session cookie, when set and when cleared, is `Secure` exactly when the request reached the
application over HTTPS (`app/api/session.py`): the request's scheme, or `X-Forwarded-Proto` when
`TRUST_PROXY` is set (the first value of a list; the image's Caddy sets it, and overwrites a client's own).
Sign-in therefore works on `http://localhost` and on a LAN address; on plain HTTP the cookie travels in
clear, as the password does.

## A backup before a migration

`python -m scripts.migrate` (what the image runs at every start) copies a SQLite database with SQLite's
online backup API before applying a pending migration, into `backups/` beside the database file:
`celestin-<UTC>-from-<revision>.db`, mode `0600` in a `0700` directory (it holds email addresses and
password hashes), one standalone file. The newest `MIGRATION_BACKUPS_KEPT` (default 5) are kept. A new
database, or one at the latest revision, is not copied; for another database the command migrates and
logs that it made no backup. If the backup fails nothing is migrated. `alembic upgrade head` by hand still
works and takes no backup. An older image on a newer database is still refused at startup
(`check_schema`): restore the backup, or run the newer image.

## Tests and tooling worth knowing

- `tests/conftest.py`: `occupy(repos)` gives an instance an account (registration is refused until it has
  one); `fresh_client` is an instance with none; `iter_api_routes(app)` walks the routers FastAPI 0.141
  nests behind `_IncludedRouter` (the route-guard test had been checking nothing until it did).
- `FakeProbe` (`tests/fixtures/fake_probe.py`) stands in for the connection check; `create_app(settings,
  engine=…, probe=…)` takes it.
- `docker/smoke.sh <image>` runs a built image through the setup, a restart, a read-only mount, an upgrade
  from a `0008` database and an unprivileged user, with no OpenAI call.
