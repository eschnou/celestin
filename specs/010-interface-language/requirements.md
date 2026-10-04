# 010 — Interface language: French and English

## 1. Introduction

Every word the student reads in the application is French, and nothing in the code knows what a locale is: no preference, no catalog, no `lang` that matches the content (`<html lang="en">` is hard-coded in `__root.tsx`). This epic makes the **interface** bilingual, French and English, and lets each user choose.

The interface is the application's own text: buttons, labels, page titles, form validation, screen-reader text, and the messages the backend writes for the student (errors, statuses). It is not Célestin's teaching, and it is not the course. Those stay French in this epic and become the subject of a follow-up spec on the course language (not yet written). A student who picks English therefore gets an English application around a French tutor, French board and French course material. That is the intended result, not a gap.

Vocabulary:

- **Interface language** (or *locale*, when the code speaks) — the language of the application's own text. A per-user preference. Values: `fr`, `en`.
- **Course language** — the language of the material, the pack, the curriculum, Célestin's speech and the notation the board draws. Always French in this epic; made a property of the course by the follow-up spec.
- **Interface text** — text the student reads that the application wrote: UI copy, its accessibility text, and the backend messages meant for the student.
- **Course text** — text that comes from the course or from the tutor: Célestin's messages, board cards, drawings, chapter titles and sections, the pack, the transcription, the text we send the model on the student's behalf.
- **Catalog** — the per-language set of interface messages.

Scope:

- A catalog and a mechanism in the frontend, with every interface string moved into it.
- A first-visit language taken from the browser's language, a stored preference set at registration, and a settings screen, built to hold several account settings, that ships with one: the language, the only place it can be changed.
- Backend messages meant for the student, localized by the request's language.
- Documentation and invariants updated to say what is now true.

Out of scope:

- Course language: prompts, pack templates, the authoring and transcription prompts, tool declarations, text sent to the model, voice language, board notation. Everything in the model's path stays as it is, byte for byte.
- Any language other than French and English. Adding one must be a catalog and a list entry (NFR 4.1.6), not a project.
- Translating or re-detecting what a student wrote: course names, chapter titles, pack and curriculum text, conversations.
- Professional translation review. English copy is written by us (R6.2).
- Right-to-left layouts, per-region variants (`fr-BE` against `fr-FR`), time zones.
- A language control outside user settings: none on the sign-in and registration pages, none in the app bar or the lesson.
- The other settings the screen is meant to hold later: changing the name, the email address, resetting the password. They are neither implemented nor shown as placeholders; the screen and its update route are only shaped to receive them (R1.2, NFR 4.1.9).
- A cookie for the language: signed out, the browser's language decides; signed in, the account does.

## 2. Alignment with product vision

| Brief v2.0 | How this epic serves it |
|---|---|
| §3.1 French-speaking student; the tutor speaks their teacher's language | Unchanged. The tutor, the board and the notation stay French and follow the course. This epic touches the frame around them, not the content. |
| §5.1 It teaches the student's course | Reinforced by a boundary rule (R4): nothing the interface language changes may reach the model, the board or the notation. |
| §5.7 Setup is minutes | A student lands in their own language with no step: the browser's language decides on the first visit and is kept on the account at registration. Changing it later is one setting. |
| §6.8 The interface | Deviation 1. |
| §8 Privacy | The preference is one short code on the account; no new data about the student. |

Deviations from the brief and from `CLAUDE.md`:

1. **§6.8 says « All interface copy is in French ».** After this epic the interface is French or English at the student's choice, French by default. §6.8 and the root `CLAUDE.md` invariant (« UI copy and tutor speech are in French ») are rewritten to separate interface copy (either language) from tutor speech (the course's language, French for now). §6.8's list of screens also gains « Paramètres », the settings screen.
2. **§12 question 4 (material language) stays open.** This epic does not accept non-French material; it only keeps the interface from assuming French.

## 3. Requirements

### R1 — The settings screen and the language setting

**As a** user, **I want** a settings screen where I change the interface language, **so that** I can use the application in the language I read best, and so that my account settings have one place to live.

Acceptance criteria:

1. The user menu, where the user's name and sign-out already are (the app bar and the chapter bar, one menu shared by both), gains an entry « Paramètres » / "Settings". It leads to the **settings screen**, a route of its own under `_auth` (`/settings`), with a way back to the page the user came from.
2. The screen is a page with a title and a list of **sections**, each a titled block that loads and saves on its own. This epic ships one section, « Langue » / "Language", which lists « Français » and « English » by their own name and marks the current one. The shell does not know what a section contains (NFR 4.1.9).
3. **Nothing else is shown.** No disabled field, no « bientôt » / "coming soon" for the name, the email address or the password.
4. **There is no language control anywhere else.** Not on the sign-in or registration pages, not in the app bar, not in the lesson. The screen is reachable only when signed in.
5. Choosing a language saves it to the account and changes the interface at once, without a page reload; the screen stays open and re-words itself. If saving fails, the interface stays in the previous language and the section shows the error, in that language.
6. Opening the settings from a lesson is a navigation like any other. The parcours transcript is held in memory only, so it ends exactly as it does when the student opens « Mes cours »; progress, which the server owns, is unaffected. Decided: no special handling, the lesson does not stay mounted; this can change later. The design states what an open voice session and an open turn do on leaving, as they do for any navigation.
7. The menu entry and the screen are keyboard operable, with accessible names in the *current* interface language; the language options are a labelled radio group or equivalent, not colour alone.

### R2 — The language: from the browser at first, from the account after

**As a** user, **I want** the application to speak my language from my first visit, **so that** I have nothing to set up.

Acceptance criteria:

1. **Signed out** (the sign-in and registration pages, and any error page), the interface language is the browser's: the first supported language in the request's `Accept-Language`, by quality order, matched on the primary tag (`fr-BE` and `fr-CA` give `fr`; `en-GB` gives `en`). A header with no supported language, or none, gives `fr`. An unsupported or malformed value is skipped, never an error.
2. **Registering stores the language the user was seeing.** The new account's preference is set from the same resolution; the user does not choose it in the form.
3. **Signed in**, the interface language is the account's stored preference (`users.locale`), returned with the user in `/api/auth/me`, sign-in and registration responses. It no longer depends on the browser. A user whose account language differs from the sign-in page's sees the interface change to the account's when sign-in completes.
4. Changing the preference (R1.5) is one authenticated request that validates against the supported list and answers `422` otherwise.
5. Existing accounts are given `fr` by the migration, which is what they have always seen. No existing user changes language on deployment, whatever their browser says.
6. The sign-in and registration pages are server-rendered in the resolved language, with the right `<html lang>`, on the first response. There is no flash of the wrong language.
7. `<html lang>` always carries the interface language. Regions that show course text carry the course language (R4.4).
8. Signing out keeps nothing: the next page is resolved from the browser again. There is no cookie for the language.

### R3 — The whole frontend, in both languages

**As a** user, **I want** no French left where I chose English, **so that** the application feels finished.

Acceptance criteria:

1. Every interface string in `frontend/src` outside `components/ui` moves into the catalog and both languages are complete. The inventory, as a checklist for the design: routes and their `head()` titles and descriptions (including the Open Graph tags); `__root.tsx`'s 404 and error components; `lib/error-page.ts` (English-only today), which has no framework available and resolves its language from `Accept-Language` alone, French by default; the course, chapter, content-editor and document-picker components; `chapter-strip`, `chapter-map`, `chapter-bar`, `app-bar`; `tutor-column` (composer, symbol palette, voice controls and their phase labels); `labels.ts` and the strings it holds; the sign-in and registration forms.
2. **Accessibility text is interface text**: every `aria-label`, `title`, and screen-reader-only description, including those of `charts/`, `figure/`, `flowchart/` and `plot/` (`describe.ts` and the views). The notation inside them still comes from the board's formatter (R4.2).
3. Form validation messages (the Zod schemas) are resolved in the active language when displayed, so a language change re-words an error already on screen.
4. Messages with values are catalog entries with named parameters, not concatenation. Plurals use the language's rules (French treats 0 and 1 as singular; English only 1). No UI code builds a sentence from fragments.
5. Interface numbers and sizes use the interface language: « 12 Mo » / « 12 MB », digit grouping, decimal separator in counts and limits (`document-picker`, `source-editor`). Numbers the **board** draws are not interface numbers (R4.2).
6. Nothing in a component renders a French literal except through the catalog. The design states how that is enforced.
7. Adding a catalog key in one language and not the other fails a check that runs with the tests (and, where the library allows it, the build).

### R4 — What the interface language must not touch

**As the** product owner, **I want** a hard line between the application's text and the course's, **so that** a language choice never changes what the student is taught or what the tutor is told.

Acceptance criteria:

1. **Course text is never localized by this epic.** That covers Célestin's messages, the cards' content, the vocabulary the board draws from the course (a chart's « Effectif », « Fréquence », « Pourcentage », a box plot's « Minimum », « Médiane »), chapter titles and sections, the pack, the transcription, and conversations. The fixed words of the board's own cards (card-kind labels, « Ce qu'on retient », « Acquis », « À surveiller », « Étape suivante ») are interface text (R3.1).
2. **The board's notation follows the course.** `charts/format.ts` keeps its `fr-BE` formatting (decimal comma, `12,5 %`, `[a ; b[`, `(2 ; −1,5)`) whatever the interface language. An English interface over a French course still draws `]−3 ; 3[`.
3. **Nothing sent to the model changes with the interface language.** That covers the cached prefix, the tools and their descriptions, tool results, the history mapping, and the learner messages the interface composes on the student's behalf (`REVIEW_MESSAGE`, `START_MESSAGE`, `NEXT_STEP_MESSAGE`, `NEXT_SECTION_MESSAGE`, `ANSWER_MESSAGE`, `VOICE_TOOL_FAILED`). The voice transcript markers (`VOICE_ON_MARKER`, `VOICE_OFF_MARKER`) only label the transcript and never enter the history, so they are interface text. Those strings are prompt content: they stay French, and live apart from the interface catalog so no one translates them by accident. The voice session's language (`"language": "fr"`) is unchanged.
4. Regions of the page that show course text carry `lang="fr"` (the course language), so a screen reader pronounces the tutor's French in French inside an English interface: the tutor column's transcript, the board and its history strip, chapter titles, and the pack and curriculum views.
5. A test renders the same turn under both interface languages and asserts that the prompt the model receives is identical (R5.7).

### R5 — Backend text meant for the student

**As an** English-reading user, **I want** the errors and statuses the server sends me in English too, **so that** the interface does not turn French the moment something goes wrong.

Acceptance criteria:

1. The backend resolves a **request language** as R2 does (the signed-in user's account, else `Accept-Language`, else `fr`) and uses it for every text it writes for the student. No route takes a language parameter.
2. Errors: every `TutorError` has a message in each language. The wire shape `{code, message}` is unchanged and `code` stays stable; `message` is in the request's language. Errors with values (limits, retry delays, page counts, sizes) take them as parameters, not by formatting a French sentence.
3. The same holds on every channel that carries an error to the student: HTTP bodies, the middleware's errors (body size, same-origin, rate limits), the `error` SSE event and the voice routes. FastAPI's own `422` body is never shown: the frontend replaces it with its own catalog message.
4. Statuses the student reads are localized: the authoring and transcription failure messages (`AUTHORING_MESSAGES`, `TRANSCRIPTION_MESSAGES`), the document errors (`DocumentInvalid`), the password rule.
5. Display fields built by the server are localized: subject labels (`label_fr`; the ids stay), the « Chapitre N — » prefix of `display_title` (the chapter's own title is course text), the board and tool markers the transcript shows (« tableau effacé », « exercice posé », the section markers). Where a stored conversation is read back (discussion), its markers are produced in the request's language at read time, as they are today.
6. **Content issues** (`ContentIssue`: the reasons a pack, curriculum or transcription edit is refused) are shown to the student in the request's language. The same issues are also fed to the authoring model for repair; that text does not change (R4.3). One issue therefore has two renderings, chosen by audience.
7. **Model-facing text does not take the request language.** Tool refusals, path and curriculum rendering, schema descriptions and validation messages returned to the model are unchanged, so every golden hash and fixture in `tests/fixtures/render/` passes without regeneration.
8. A request with no resolvable language answers in French, so every existing caller and test behaves as today.

### R6 — Copy: French as it is, English written to match

**As a** user, **I want** the English to read as natural as the French, **so that** the choice is not a downgrade.

Acceptance criteria:

1. The French catalog is the current text, moved verbatim. No wording is edited in this epic, so every existing assertion on French copy passes unchanged.
2. The English copy is written by us for a secondary-school student: direct, friendly second person, short sentences, the same register as the French « tu ». The product names stay: « Célestin », « Parcours » and « Discussion » are translated only if the design lists them with a decision (open question 4).
3. Vocabulary is consistent across the catalog: one English term for each recurring French one (course, chapter, section, exercise, hint, path, board). The design fixes the glossary.
4. Both catalogs are reviewed by the user before the epic is closed; the glossary and any copy the user changes are applied in the same pass.

## 4. Non-functional requirements

### 4.1 Architecture

1. **One application, one build.** Both languages ship together and the active one is chosen at runtime. There are no per-language builds, routes or deployments, and no locale in the URL: the application is behind a sign-in, so there is nothing for a localized URL to serve.
2. **The library is a design decision, recorded with its evidence.** Candidates: Paraglide JS (the one TanStack Router's i18n guide features), `react-i18next`, `use-intl`. It must work with the project's Vite setup, with the custom `src/server.ts` and the CSRF re-registration in `src/start.ts`, and with the hosted build. The design runs a short spike on these three before choosing, and falls back to the next candidate if the first fights the setup.
3. **Typed keys.** A missing or misspelt key is a TypeScript error under the current strict configuration, not a runtime blank.
4. **The locale lives in one place on each side.** A single resolver in the frontend (used by the root route, SSR, and `error-page.ts`) and a single dependency in the backend (`Locale`, resolved per request) implement R2. The two supported-language lists are pinned equal by a test.
5. **Backend messages become catalog entries keyed by code**, not a second class attribute per language. `message_fr` is replaced, not duplicated. The design chooses between server-side localization and `code` plus parameters translated in the browser (open question 2), once, for all channels of R5.3.
6. **A third language is a catalog, a list entry and a migration-free change.** `users.locale` holds a short code with a check against the supported list in code, not a database enum; nothing in a component or an error class names a specific language except the catalogs.
7. `users.locale` is added by one Alembic migration following the `NNNN_slug` convention, existing rows set to `fr` (R2.5), with a working `downgrade`. The startup schema check and `tests/unit/test_migrations.py` keep passing.
8. **The settings are shaped for what comes next.** The screen is a shell that renders a list of section components registered in one place; adding « Nom », « Adresse e-mail » or « Mot de passe » later is a section, its catalog keys and its own route, with no change to the shell, the menu or the resolver. The preference route takes a body of optional fields with unknown ones refused (the `_Model` `extra="forbid"` convention), `locale` being the only field now. Changes that need proof of identity (email, password) will need the current password or a verification step and get routes of their own; this epic neither builds nor reserves them.
9. The course language is not modelled here. Nothing added by this epic assumes it equals the interface language, and the code names the two concepts differently (`interface locale`, `course language`) so the follow-up does not have to untangle them.

### 4.2 Performance

1. No extra round trip to render a page: the locale arrives with the request's `Accept-Language` header (signed out) or the user (signed in), the catalog with the application.
2. Changing the language does not refetch data.
3. The catalog for the inactive language does not delay first render. If the library loads catalogs per language, the design states how SSR avoids a flash (R2.6).

### 4.3 Security and privacy

1. A language value from a header or a request body is matched against the supported list before use. It is never interpolated into a path, a query, a header or HTML.
2. The server keeps no language state for a signed-out visitor: nothing is stored, set or logged about them. The language stored at registration is derived by the server from the request, not trusted from a client field, unless the design justifies one (open question 10).
3. The preference-change route declares its roles with `require_roles(...)`, acts only on the caller's own account, and passes the same-origin middleware. `tests/unit/test_route_guards.py` keeps passing untouched.
4. Parameters in messages are rendered as text by the catalog, never as HTML. A course name or a chapter title inside a message cannot inject markup.
5. No new data is logged. Log lines and event names stay English and unchanged; the locale is not added to them.

### 4.4 Reliability and quality

1. **French is the default and the fallback**, in the browser, on the server and in tests. A missing English message in production shows the French one, not a key or a blank.
2. Tests pin the interface language to `fr` in the shared setup (`frontend/src/test`, the backend fixtures), so no existing test changes. The 44 frontend and ~170 backend assertions on French literals are the regression net for R6.1.
3. New tests:
   - catalog parity: the same keys and the same parameter names in both languages;
   - `Accept-Language` resolution on both sides: quality order, region tags (`fr-BE`, `en-GB`), unsupported and malformed values, an absent header;
   - the sign-in page rendered in the language of the header, with `lang`;
   - registration stores the language the visitor was seeing; sign-in with a different stored language switches to it;
   - the settings screen: the entry in both bars, the language section with the current language marked, a failed save leaving the previous language, no language control on the sign-in and registration pages;
   - every `TutorError` and every status message has both languages, and parameters are present in both;
   - the render goldens and the prefix byte-stability tests pass without regeneration (R5.7);
   - the preference route: success, unsupported value, unauthenticated, someone else's account;
   - the migration up and down, and existing rows read `fr`.
4. The manual checklists in `documentation/` gain one pass per language: sign-in, the settings, a course, a chapter in preparation, a lesson with a drawing, a content-editor refusal, a refused upload, a voice session.

### 4.5 Usability

1. The settings are reachable from the user menu on every authenticated page, in the same place each time (R1.1).
2. English strings differ in length from the French. Layouts that were checked at 400 px (the lesson stacks board-first below `lg`) still fit with the longer of the two in every place, with no truncated button and no horizontal scroll.
3. The settings respect the existing accessibility conventions: labels, focus order, `aria-live` for nothing (a language change is not announced as an event; `lang` changes are enough).
4. No interface text is baked into an image or an SVG as outlines; text in drawings that is interface text is real text (it already is, apart from board labels, which are course text).

## 5. Open questions for the design

1. **Library choice** (4.1.2): result of the spike, and how the compile step, if any, sits in the Vite config.
2. **Where backend text is localized.** Server-side by request language, or `code` plus parameters sent to the browser and translated there. The second keeps one catalog for the user to review, but the stream and voice channels, `ContentIssue`'s two audiences and the `422` bodies decide whether it is enough on its own.
3. **`ContentIssue` volume.** About forty construction sites carry French prose (`pack.py`, `curriculum.py`, `references.py`, `transcription.py`) and the same strings feed the repair prompt. The design may split code and parameters from rendering, or accept a coarser student-facing text (R5.6) while the repair text stays; it must say which.
4. **Product names.** Whether « Parcours » (the mode) and « Discussion » are translated, kept as French words, or given an English equivalent; the same for « séance », « tableau », « cours » in places the brief treats as vocabulary.
5. **Screen-reader descriptions** (R3.2). They are interface text in the interface language wrapped around French board notation. Whether the mixed result reads acceptably in English, or whether the numbers and symbols inside need their own `lang` span.
6. **Plurals and gender.** Which messages need plural forms or agreement in French (« 1 chapitre prêt », « faite » against « fait »), and whether the library's syntax carries them or the catalog avoids them.
7. **Enforcing no raw French in components** (R3.6): a lint rule, a test that scans for accented literals, or review alone.
8. **Where `error-page.ts` and the 404/error boundaries get their language** when they render before, or without, the catalog's runtime.
9. **One user menu.** How the app bar and the chapter bar share one user menu so the « Paramètres » entry is the same in both. (Whether the lesson stays mounted behind the settings is decided: it does not, R1.6.)
10. **Registration language source.** The server reads `Accept-Language` on the registration request, or the form sends the language the page was rendered in. The first cannot be forged; the second is exactly what the visitor saw if the header changed between page load and submit.
