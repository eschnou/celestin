# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A self-service AI tutor ("Professor Célestin", after the pedagogue Célestin Freinet) for secondary-school students, who bring the course material their teachers gave them. We are not a source of content: the student's material is. The product brief lives in `specs/product.md` and is the source of truth for scope, behaviour and vocabulary — read it before designing anything non-trivial.

The architecture the whole codebase serves:

- **Courses and chapters** (specs 005, 006) — a student creates a course (a name and a locked subject) and adds chapters by dropping the material: one PDF, or photos of its pages. Everything is a database row owned by that student; see `documentation/accounts-and-courses.md`.
- **Authoring agent** — reads the document's pages into a transcription (page markers, handwriting and doubt marked; the document itself is never stored), then turns that text into a **course pack** (structured Markdown following the subject's template) and a **curriculum** (JSON: a locked path of lesson, practice and synthesis sections), validated and repaired, in the background; see `documentation/authoring.md` and `documentation/chapters.md`. The pack is the tutor's only allowed source for definitions, formulas, notation and vocabulary.
- **Tutor** — reads four prompt layers (the subject-neutral tutor prompt, the subject prompt, the chapter's pack and path overview, and the mode's own layer) plus the student's progress, and teaches by calling a fixed tool set (plan, explain, worked example, set exercise, read photographed work, check, hint, discuss, reveal, record, recap). Rules are enforced in the tools, not in the prompt.
- **Modes** (spec 007) — the same chapter, two ways to work on it: **parcours**, the locked path of sections, and **discussion**, a free conversation with the board and no path. A mode selects a prompt layer, a tool set and who owns the transcript; a discussion is offered the board tools only and its turn context has no store, so nothing said there can move the student's progress. See `documentation/discussion.md`.
- **Interface** — a lesson, not a chat. Each tutor tool call renders as a purpose-built board/card. Drawings are typed blocks (specs 008, 009): statistical charts, organigrammes, figures (geometry, number lines, sets) and graphs in a repère. Célestin gives their data, the tools check it, and the board lays it out and draws it in the course's notation; see `documentation/tutor-turn-pipeline.md`. Spec 009 skipped SDD at the user's request: `specs/009-board-drawings/` holds the reviewed designs instead of a requirements/design/tasks trio.
- **Accounts** (spec 004) — students register and sign in; progress is a database row per student and chapter, written by the section tools.
- **Interface language** (spec 010) — the application's own text (buttons, menus, errors, statuses, accessibility text) is French or English, chosen by the user: the browser's language at first, kept on the account at registration, changed on the « Paramètres » screen. It is a different thing from the *course language*, and nothing the model reads ever depends on the interface language; see `documentation/i18n.md`.
- **First-run setup** (spec 013) — an instance with no account sends its first visitor to `/setup` (first visitor wins, closed for good by the first account), generates its secrets into `SECRETS_DIR`, keeps the provider key encrypted in the database (admin settings section, changed without a restart through the provider hub, environment wins), starts and answers `503 ai_not_configured` without a provider, and backs the database up before a migration. `documentation/first-run-setup.md`, `documentation/docker.md`.
- **Admins and registration modes** (spec 012) — `users.enabled` (a disabled account cannot sign in and holds no session), `REGISTRATION_MODE` (`open`, `closed`, `verification`) and the `admin` role: `/admin` lists accounts, enables or disables one, resets a password (shown once). An admin is created only by `scripts/create_admin.py`; the dashboard never promotes. See `documentation/admin.md`.
- **AI providers** (spec 014) — the application runs on any OpenAI-compatible server, not only OpenAI: a default connection (address, key, API style `responses` or `chat`, structured-output mode) plus a model, reasoning effort and optional own connection per role (tutor, authoring, transcription, voice), set by the administrator in the browser or by environment variables (environment wins), applied without a restart by the provider hub; a test with live checks says whether a model can do each job. Nothing a model does can break an invariant: the rules are in the tools. `documentation/ai-providers.md`.
- **Course language** (spec 011) — a course is French or English (`courses.language`, chosen when it is created, never changed). It is the language of the student's material, the pack, the curriculum, Célestin's speech, the voice session and the board's notation: the prompt set has a `*.en.md` file beside every `*.fr.md`, the text the code builds for the model, the tool rules and the board's formatters are per language (`by_language` tables), and a French course reads byte for byte what it always did; see `documentation/course-language.md`.

Prompts and templates we write live in `backend/prompts/`; nothing a student creates lives on the file system.

Non-negotiable invariants from the brief, in case a change looks like it violates one:

- Correctness verdicts come from a mechanical checker (or an explicit rubric for free text), never from model prose.
- While an exercise is open, no tutor output may contain the answer. Reveals are gated, explicit and logged.
- Formulas, notation, methods and vocabulary are restricted to the chapter's pack; the authoring agent restructures the student's material and never adds to it.
- A student's courses, material and progress are private to that student.
- A course is French or English (spec 011); tutor speech, the board's notation and everything sent to the model follow the **course's** language, never the interface's, and follow the notation of the student's own material. French courses are French-speaking Belgian (FWB): decimal commas, `]a; b[` intervals, sequences indexed from `u₁`; English courses use the common international convention (decimal point, `(a, b)` and `[a, b)`, `(2, −1.5)`). Interface copy is French or English at the user's choice, French by default (spec 010).

## Layout

| Path | What |
| --- | --- |
| `README.md`, `LICENSE` | The public face of the project (pitch, Docker quick start, run from source) and its MIT license. Keep the README's quick start in step with `documentation/docker.md`. |
| `specs/product.md` | Product requirements document (v2.0). The brief. |
| `specs/NNN-*/` | Per-feature requirements, design and implementation plan. |
| `documentation/` | How the built system works. Start at `documentation/index.md`. |
| `frontend/` | TanStack Start app — the lesson view. See `frontend/CLAUDE.md`. |
| `backend/` | Python/FastAPI tutor service. See `backend/CLAUDE.md`. |

Each side has its own `CLAUDE.md` with the commands and conventions that only apply there. Read the one for the directory you are working in.

## Running it

Two processes. The frontend proxies `/api` to the backend, so the browser sees one origin.

```sh
cd backend  && uv run alembic upgrade head && uv run uvicorn app.main:create_app --factory --reload --port 8000
cd frontend && npm run dev        # :8080
```

Configuration comes from `.env` in `backend/` or at the repository root; both are gitignored.
`SESSION_SECRET` is required unless `SECRETS_DIR` generates one; `OPENAI_API_KEY` is optional (an administrator can choose the provider and store its key encrypted in the settings screen, specs 013 and 014; `OPENAI_BASE_URL` and the model variables point at another provider); `COOKIE_SECURE=false` (or `auto`) on plain `http://localhost`. A fresh instance is waiting for its first administrator and leads to `/setup`.
Full setup, checks and troubleshooting: `documentation/running-locally.md`. The same thing as one Docker image: `documentation/docker.md`.

## Git

Never rewrite published history: no force push, rebase, amend or squash of commits that are already pushed. Keep the branch you push in a working state.

## Development Process

### Steering Documents
The `./specs` folder contains steering documents for the project:
- `./specs/product.md` - Business-level overview of the application
- `./specs/index.md` - Index of all feature specs

### Spec-Driven Development
Feature specs are written and executed with the `sdd` plugin (marketplace `eschnou/claude-plugins`,
install with `/plugin marketplace add eschnou/claude-plugins` then `/plugin install sdd@eschnou-claude-plugins`).
**Always go through these commands**; never freehand a `requirements.md`, `design.md` or `tasks.md`,
and never run a later step before the user has reviewed the previous one.

| Step | Command | Produces |
| --- | --- | --- |
| 1 | `/sdd:requirement [slug] [description]` | `specs/NNN-<slug>/requirements.md` — what and why |
| 2 | `/sdd:design [slug] [focus]` | `design.md` — architecture, interfaces, data models, errors, tests |
| 3 | `/sdd:plan [slug] [focus]` | `tasks.md` — phases and tasks, doubles as the status report |
| 4 | `/sdd:go [slug] [focus]` | the implementation, phase by phase, on a `feature/<slug>` branch |
| 5 | `/sdd:verify [slug] [focus]` | a review report against the spec; changes nothing |

`/sdd:init` bootstraps `specs/` and is already done here. Specs are numbered sequentially
(`001-`, `002-`, …) and listed in `specs/index.md`, which every step updates.

### Documentation
When a user request is completed, create or update documentation in `./documentation` to reflect the changes:
1. Keep one file per functional or technical domain area
2. **Always update `./documentation/index.md`** when adding new documentation files
3. Before finishing any task that adds or modifies features, check if documentation needs updating
4. Reference `./documentation/index.md` to see existing documentation topics
