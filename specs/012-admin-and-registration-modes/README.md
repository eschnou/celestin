# 012 — Admins and registration modes

**Status:** implemented on `feature/admin-registration-modes` (2 October 2026). No SDD was used, at
the user's request (one shot, no review stops): this README holds the decisions instead of a
requirements, design and tasks trio, as spec 009 does. How it works is in
[`documentation/admin.md`](../../documentation/admin.md).

## The request

Roles, in particular one or more admins with a dashboard to **enable or disable users** and **reset
their password**; and three registration modes:

- **open**: anyone can sign up and use the app;
- **closed**: sign-up is impossible, and the home page does not even link to it;
- **verification**: sign-up is possible, but the user cannot sign in until an admin enabled the account.

## What was already there

`users.role` (`student`, `parent`, `admin`) and `require_roles(...)` since spec 004, with a test that
refuses any route without a role list. Nothing admitted `admin`, and an account had no state.

## Decisions

| Question | Decision | Why |
|---|---|---|
| Where does the mode live? | `REGISTRATION_MODE` in the configuration, shown read-only on the dashboard | A deployment decision, like `COOKIE_SECURE`; a database setting would need a settings table, a route and a UI for one value. A later spec can move it if admins need to flip it live |
| Account state | one boolean, `users.enabled` (default true) | « pending » and « disabled by an admin » are the same thing to the user and to the admin's action (enable); two states would only add a second button |
| Disabling | deletes the account's sessions in the same transaction, and `authenticate` re-reads the flag on every request | A disabled user must not stay signed in until the cookie expires |
| What a disabled user is told | `account_disabled` **after** a right password only | Telling a stranger « this address has an account, not enabled » would break the no-enumeration rule of spec 004 |
| Verification-mode registration | `202 {user, pending}` and no cookie | The old `201` is a promise of a session; a different status makes the client's branch explicit |
| Closed-mode registration | `403 registration_closed` at the API, no link on the sign-in page, a « closed » page at `/register` | Hiding the link alone is not closing the door |
| How admins are made | only `scripts/create_admin.py` (spec 013 added one exception: `POST /api/setup` creates the first admin of an instance with no account at all) | No route can promote, so a compromised admin cannot mint admins, and the dashboard needs no role editor. Costs a shell for the first admin, which is what a first admin needs anyway |
| Resetting a password | the server generates one, shows it once, ends every session of the account | The admin never chooses (or learns) a password worth keeping; a mail flow does not exist here |
| A way to change it afterwards | `POST /api/auth/password` and a « Mot de passe » section in the settings | Without it a reset would leave a temporary password forever. Spec 010 built the settings screen to receive exactly this |
| Self-service limits | an admin cannot disable or reset themselves (`409 own_account`), and the last enabled admin cannot be disabled (`409 last_admin`, checked in the disabling transaction) | An enabled admin always remains, even when two admins disable each other at once; a reset of oneself would just sign the admin out |
| Do admins use the tutor? | no: student routes answer 403 to an admin and the frontend sends them to `/admin` | An admin owns no courses; a half-working student view would be worse than none |

## Deviation worth knowing

The migration's server default for `enabled` is the string `'1'`. A SQL expression (`sa.text('1')`,
`sa.true()`) makes alembic rebuild the table on SQLite, and with foreign keys enforced that cascades
through `courses`, `chapters` and `progress`: the first draft of the migration deleted every course.
`tests/unit/test_migrations.py::test_upgrade_from_0007_…` pins it.

## Review follow-ups

A review of the first version led to: `users.last_seen_at` instead of deriving it from sessions;
a Unicode-aware search on SQLite; the `last_admin` rule above; a rate limit on the password change;
`create_admin` asking for the password; the pager stepping back when a page empties; the sign-in
page showing the registration link when the mode cannot be read; and a debounce that no longer
resets the page on mount. Accepted as is: one admin can reset another's password (admins are
trusted with each other; it is logged), and the settings password field's rule is client-side
length only, the server's other refusals showing as its message.

## Not built

Promoting or demoting from the dashboard; deleting an account; email notification to an admin of a
pending account or to a user once enabled (the app sends no email at all); switching the mode from
the dashboard; audit history beyond the log lines; an admin view of a student's courses.

## Tests

Backend: `tests/integration/test_admin_and_registration.py` (modes, enabled flag, admin routes and
their guards, password reset and change), `tests/unit/test_create_admin.py`,
`tests/unit/test_migrations.py` (0008). Frontend: `src/routes/__tests__/registration-modes.test.tsx`,
`admin-page.test.tsx` (panel and role routing), the password section in `settings-page.test.tsx`,
the form and `register()` cases in `auth-forms.test.tsx` and `lib/__tests__/auth.test.ts`.
