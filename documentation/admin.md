# Administration and registration modes

Spec 012. Who may create an account, who may use it, and the administrators who decide. The
accounts themselves (sessions, passwords, roles) are in [accounts-and-courses.md](./accounts-and-courses.md).

## Registration modes

`REGISTRATION_MODE` (backend setting, read at startup; restart to change it) is one of:

| Mode | Registration | Sign-in of a new account |
|---|---|---|
| `open` (default) | anyone, `201` and a session, as before | at once |
| `closed` | `403 registration_closed`; the sign-in page has no link to it and `/register` says it is closed | not applicable; existing accounts still sign in |
| `verification` | `202 {user, pending: true}`, the account is created **disabled**, no cookie | `403 account_disabled` until an admin enables it |

`GET /api/auth/config` (public) answers `{registration}` and is what the sign-in and registration
pages read. The mode lives in configuration rather than in the database on purpose: it is a
deployment decision, and the dashboard shows it (read only) so an admin knows what new visitors see.

In verification mode the registration page says that an administrator checks new accounts, and
after registering shows « Compte créé » instead of signing in. `account_disabled` is said only once
the **password was right**, so the answer cannot be used to find which addresses have an account;
a wrong password for a disabled account is still `invalid_credentials`.

## Enabled and disabled

`users.enabled` (migration `0008`; every existing account reads enabled). A disabled account:

- cannot sign in;
- holds no session: disabling deletes the account's sessions in the same transaction, and
  `AuthService.authenticate` refuses (and deletes) a session whose user is disabled, so the flag is
  read on every request and not only at sign-in;
- keeps its courses, chapters and progress. Enabling it again gives everything back.

The migration's default is the plain string `'1'`, not `sa.text`/`sa.true()`: on SQLite any SQL
expression as a default makes alembic rebuild the `users` table, and with foreign keys on that
**deletes every course of every student**. `test_upgrade_from_0007_…` pins it.

## Admins

The role `admin` existed since spec 004 and admitted nothing. It now admits `/api/admin/*` and the
dashboard. An admin is not a student: the student routes answer `403` to an admin, and the frontend
sends an admin who opens one to `/admin` (a student or a parent who opens `/admin` goes to
`/courses`). Admins keep the settings screen (language, password).

There are **two ways to get an admin**, on purpose, and neither is a promotion: the command line, and — once, on an
instance that has no account at all — the first-run setup (`POST /api/setup`, first visitor wins; see
[first-run-setup.md](./first-run-setup.md)). The command line:

```sh
cd backend && uv run python -m scripts.create_admin --email admin@example.be [--name Admin]
```

The password is asked for twice, not given as an argument (which would sit in the shell history and the
process list); `--password` exists for scripts and tests.

Idempotent. An unknown address gets a new, enabled admin. A known one is made an enabled admin, is
given the new password and is signed out everywhere, which is also how a lost admin password is
recovered. The dashboard does not promote or demote, so a compromised admin cannot mint admins and
a request cannot change a role (`PATCH` refuses any field but `enabled`). `POST /api/setup` cannot add an
admin to an instance that has any account.

## The AI provider (specs 013, 014)

The admin's settings screen has a « Fournisseur d'IA » section: the provider (OpenAI, Groq, OpenRouter, Ollama or
another server), its address and key, a model and a reasoning effort per role, a test with an optional live
check. The routes are `GET/PUT /api/admin/ai`, `GET /api/admin/ai/models` and `POST /api/admin/ai/test` (admin
only, throttled). A key is stored encrypted and never shown again; what the server's environment sets wins and is
read-only. While no provider is configured the dashboard shows a banner and the student's AI routes answer `503`.
Details: [ai-providers.md](./ai-providers.md).

## Routes

All admit `admin` only (`require_roles("admin")`; `test_route_guards.py` still refuses any
unguarded route). A user id is whatever the admin names: there is no ownership here.

| Route | Body | Answer |
|---|---|---|
| `GET /api/admin/users?q=&status=&limit=&offset=` | — | `{users, total, counts: {total, enabled, disabled}, registration_mode}`; `status` is `all`, `enabled` or `disabled`; `q` matches name or email, case-insensitively, `%` and `_` literal; accounts waiting for an admin first, then newest; `limit` 1–200 (default 50) |
| `PATCH /api/admin/users/{id}` | `{enabled}` | `200 {user}`; `404`; `409 own_account` when disabling oneself |
| `POST /api/admin/users/{id}/reset-password` | — | `200 {user, password}` with `Cache-Control: no-store`; `404`; `409 own_account` |

A user row is `id, email, name, role, locale, enabled, created_at, last_seen_at`. `users.last_seen_at`
is set when a session is opened and at the hourly touch, so it survives sign-out and password
resets (it was first derived from sessions, which are deleted); the migration backfills it from the
open sessions, and `null` reads « Jamais ». Never a hash. Search uses a Unicode-aware `lower()`
registered on SQLite connections (its own folds ASCII only, so « Élodie » would not match « élodie »).

An admin cannot disable or reset **themselves** (`own_account`), and the **last enabled admin** cannot
be disabled (`409 last_admin`): checked in the transaction that disables, so two admins disabling each
other cannot both succeed. Admins are trusted with each other otherwise: one can reset another's
password; the log line names the actor.

## Resetting a password

The server generates a 14-character password from an alphabet without look-alikes (no `0 O 1 l I`,
no symbols; about 80 bits), checked against the password policy, stores only its Argon2id hash,
deletes **every session** of the account, and returns the password once. The dashboard shows it in a
dialog with a copy button; nothing keeps it (not the query cache, not the log). The admin hands it
over; the user changes it in « Paramètres ».

`POST /api/auth/password {current_password, new_password}` (any signed-in user, their own account
only) is that change: it is throttled like sign-in (`429 rate_limited`, per user: a stolen session must not become a way to guess the password), checks the current password (`422 wrong_password`, not 401, which would
sign the browser out), applies the password policy (`422 weak_password`), and ends **every other**
session while the one making the change stays.

## Frontend

```
src/routes/_auth/admin/index.tsx             « Administration »: the registration mode, the users panel
src/components/celestin/admin/users-panel.tsx    filters (all / disabled / enabled, with counts), search, table, paging (25), enable, disable and reset with confirmations, the one-time password dialog
src/components/celestin/settings/password-section.tsx   « Mot de passe » on the settings screen
src/lib/admin.ts                             the queries and the two mutations
src/lib/auth.ts                              authConfigQuery, register() → {status: signed_in | pending}, changePassword, homePath, isAdminPath
```

`_auth.tsx`'s `beforeLoad` does the role routing described above. The row of the signed-in admin has
no buttons. A refusal from the server is shown above the table in the user's language.

## Failure behaviour

| Situation | Answer |
|---|---|
| Register while `closed` | `403 registration_closed` |
| Right password, account not enabled | `403 account_disabled`, no session |
| Wrong password, account not enabled | `401 invalid_credentials` |
| A session of a user disabled behind the service's back | `401 not_authenticated`, the session row deleted |
| Student or parent on `/api/admin/*` | `403 forbidden` |
| Admin on a student route | `403 forbidden` |
| Admin disables or resets themselves | `409 own_account` |
| Disabling the last enabled admin | `409 last_admin` |
| Unknown user id | `404 not_found` |
| `PATCH` with a role or any other field | `422` |

## Logs

`auth_register` (with `pending`), `auth_register_refused` (`reason: closed`), `auth_login_failed`
(reason `disabled`), `admin_user_enabled`, `admin_user_disabled` and `admin_password_reset`
(`actor_id`, `user_id`), `auth_password_changed`, `auth_password_change_failed`. Never an address, a
password or a name.

## Manual checklist

1. `scripts.create_admin` (it asks for the password), then sign in: the page is « Administration », not « Mes cours ».
2. `REGISTRATION_MODE=verification`, register from a private window: « Compte créé », and signing
   in says the account is not active yet.
3. In the dashboard « Désactivés (1) » shows it first; « Activer »: the student can sign in.
4. « Désactiver » on a signed-in student (confirm): their open page gets the sign-in redirect on its
   next request.
5. « Réinitialiser le mot de passe »: the dialog shows the password once; the old one no longer works;
   the student signs in with the new one and changes it in « Paramètres ».
6. `REGISTRATION_MODE=closed`, restart: no « Créer mon compte » on the sign-in page, `/register`
   says it is closed, `POST /api/auth/register` answers 403.

Checked through Playwright on 2 October 2026: steps 1 to 3 and 5 (the dialog), and 6.
