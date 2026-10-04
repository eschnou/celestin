# 010 — Interface language: design

Requirements: `requirements.md` (R1–R6, NFR 4.x). Research evidence: a spike of Paraglide JS in a throwaway worktree of this repo (build, tsc, lint, 1013 tests, SSR curls, Playwright hydration), plus read-only maps of the frontend and backend.

## 1. Overview

One application, one build, two catalogs. The interface language is:

- **signed out**: the first supported language of the request's `Accept-Language` (`fr` otherwise);
- **signed in**: `users.locale`, set from the same rule at registration and changed only on the new `/settings` screen.

Three mechanisms carry it:

1. **Frontend catalog**: Paraglide JS (typed message functions), with two custom strategies instead of URL or cookie. Every interface string becomes `m.some_key()`.
2. **Backend catalog**: a small Python message catalog keyed by stable codes, rendered at the edge (HTTP handler, middleware, SSE, route DTOs) with the request language. Domain code stays language-free; it builds a code and parameters.
3. **A hard wall around the model**: nothing the model reads, and nothing the board draws, depends on the interface language.

### Decisions on the requirements' open questions

| # | Question | Decision |
|---|---|---|
| 1 | Library | **Paraglide JS 2.25.x.** It worked with the Vite setup, Vite 8, `server.ts`/`start.ts` and `nodejs_compat`. Fallback: `react-i18next`. |
| 2 | Where backend text is localized | **Server-side, at the edge**, by request language (account, else `Accept-Language`). The wire shape `{code, message}` is unchanged. The frontend needs no error-code table. |
| 3 | `ContentIssue` volume | Additive `code` + `params` on the dataclass; `message` stays the French text the repair prompt reads. Student rendering uses the catalog when a code exists, else `message` (§4.9). |
| 4 | Product names | Glossary proposal in §5.5, for the user's review (R6.4). |
| 5 | Screen-reader descriptions | Interface text in the interface language; board notation inside stays course notation; no inner `lang` spans. |
| 6 | Plurals and gender | Plural selectors in the message format (frontend) and `.one`/`.other` keys (backend). Gender agreement is avoided by wording. |
| 7 | No raw French in components | Two local ESLint rules (§5.7) plus `i18n:check` in the test gate. |
| 8 | Error page language | A pure `matchLocale` over `Accept-Language`, with no Paraglide dependency (§5.6). |
| 9 | One user menu | New shared `UserMenu` replaces the two bar fragments (§5.4). |
| 10 | Registration language | The server reads `Accept-Language` on the registration request. `RegisterRequest` stays `extra="forbid"`; no client field. |

## 2. Architecture

```
 Browser                          Frontend server (TanStack Start / Nitro)           Backend (FastAPI)
 ───────                          ────────────────────────────────────────           ─────────────────
 Accept-Language ───────────────► server.ts: paraglideMiddleware(request)             
                                   AsyncLocalStorage locale =                         
                                   custom-header strategy(matchLocale(header))        
                                   SSR render: <html lang>, m.*() ◄── messages/*.json 
 hydrate ◄──────────────────────── HTML (Vary: Accept-Language)                       
 client locale =                                                                      
   custom-app strategy:                                                               
   me-cache user.locale ?? <html lang>                                                
 fetch /api/* (cookie + Accept-Language) ─────────────────────────────────────────►  current_user → request.state.locale = user.locale
                                                                                      handler / SSE / DTOs render with
                                                                                      locale_of(request) | user.locale
 PATCH /api/auth/me {locale} ─────────────────────────────────────────────────────►  UserRepository.set_locale
 setLocale(l, {reload:false}) → me-cache → useLocale() → <Fragment key=locale>        

 Model path (unchanged, no locale parameter anywhere):
   prompts/*.fr.md → PromptService → provider ; tool outputs, ToolValidationError, history, curriculum_render
```

Where the language is decided:

| Situation | Frontend | Backend |
|---|---|---|
| Signed-out page (SSR) | custom server strategy over `Accept-Language` | n/a (SSR makes no API call) |
| Signed-out API call (login, register, 401, middleware refusals) | n/a | `parse_accept_language(header)` |
| Signed-in, after hydration | `me`-cache `user.locale` | `request.state.locale` = `user.locale` |
| Error page (SSR crash) | `matchLocale(header)` | n/a |

The two parsers (`matchLocale` in TypeScript, `parse_accept_language` in Python) are pinned to one case table (§7.4), so the SSR page and the API agree.

## 3. Data models

### 3.1 Database

`users.locale String(8) NOT NULL server_default 'fr'`. Existing rows read `fr` (R2.5). No check constraint: the supported list is code (NFR 4.1.6).

Migration `0006_user_locale.py` in the 0005 style (`revision = '0006'`, `down_revision = '0005'`):

```python
def upgrade() -> None:
    op.add_column("users", sa.Column("locale", sa.String(length=8), nullable=False, server_default="fr"))

def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("locale")
```

`UserRow.locale = mapped_column(String(8), nullable=False, server_default="fr")`. `test_head_matches_the_models` compares `server_default`, so the model and the migration must carry the same value.

### 3.2 Backend types

```python
# app/domain/locale.py  (imports nothing)
Locale = Literal["fr", "en"]
LOCALES: tuple[Locale, ...] = get_args(Locale)
DEFAULT_LOCALE: Locale = "fr"
def is_locale(value: object) -> TypeGuard[Locale]: ...
def parse_accept_language(header: str | bytes | None) -> Locale: ...
```

`parse_accept_language`: split on `,`; per item split on `;`, strip, read `q=` (default 1, malformed q skipped, `q=0` excluded); sort by q descending, stable; map the primary subtag lowercase (`fr-BE` → `fr`, `en-GB` → `en`); the first supported wins; else `DEFAULT_LOCALE`. Whitespace is tolerated (`en; q=0.8`). `*` is ignored.

```python
# app/domain/user.py
@dataclass(frozen=True)
class User:
    id: str; email: str; name: str; role: Role
    locale: Locale = DEFAULT_LOCALE          # default keeps every User(...) call valid
```

DTOs (`app/api/schemas/auth.py`, `_Model` = `extra="forbid"`):

```python
class UserDTO(_Model):    id: str; email: str; name: str; role: Role; locale: Locale
class UpdateMeRequest(_Model):  locale: Locale | None = None     # the only field now
```

### 3.3 Backend catalog

```
app/domain/messages/__init__.py   render(key, locale, **params), render_issue(issue, locale), plural_category(locale, n)
app/domain/messages/fr.py         MESSAGES: dict[str, str]    # the current text, verbatim
app/domain/messages/en.py         MESSAGES: dict[str, str]
```

- Values are `str.format` templates with named fields. `render` looks up `MESSAGES[locale][key]`, falls back to French for a missing English key (logged once per key as `i18n_fallback`, key only), and never raises in production.
- **Plurals:** when `params` has `count`, `render` tries `f"{key}.{category}"` first. `plural_category("fr", n)` is `one` for 0 and 1; `("en", n)` is `one` only for 1; else `other`.
- Key namespaces (one flat dict per locale; the prefix is the owner):

| Prefix | Content | Replaces |
|---|---|---|
| `<error code>` | each `TutorError` (`internal`, `not_authenticated`, `source_length`, …) | `message_fr` |
| `weak_password.too_short` / `.personal` | password policy | `password.py` sentences |
| `document.<reason>` | upload refusals | `DocumentInvalid` strings |
| `conversation_closed.<reason>` | the three composed sentences | `ConversationClosed._WHY` |
| `authoring.<code>`, `transcription.<code>` | chapter failure messages | `AUTHORING_MESSAGES`, `TRANSCRIPTION_MESSAGES` |
| `subject.<id>` | subject labels | `label_fr` |
| `chapter.title`, `chapter.untitled` | `Chapitre {n} — {title}`, `Nouveau chapitre {n}` | `display_title` |
| `marker.<kind>` | `marker.title`, `.explanation`, `.worked_example`, `.exercise`, `.check_question`, `.recap`, `.cleared`, `.section_started`, `.section_review`, `.section_done`, `.step_ready` | card `marker` ClassVars, `CLEAR_MARKER`, section and pace markers |
| `issue.<code>` | content issues shown in the editor | §4.9 |

`MESSAGES` keys are identical in both files (test, §7.1). The French file is the existing text moved verbatim, so every existing assertion on French copy holds.

### 3.4 Frontend types and catalog

```ts
// src/lib/locale.ts  (pure, no Paraglide import: used by the error page and tests)
export const LOCALES = ["fr", "en"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "fr";
export const AUTONYM: Record<Locale, string> = { fr: "Français", en: "English" };
export function isLocale(v: unknown): v is Locale
export function parseAcceptLanguage(header: string | null | undefined): Locale
export function matchLocale(tags: readonly string[]): Locale        // navigator.languages
```

```ts
// src/lib/auth.ts
export type User = { id: string; email: string; name: string; role: Role; locale: Locale };
```

`messages/fr.json` (base) and `messages/en.json`: flat keys, `snake_case`, area prefix (`auth_`, `courses_`, `course_`, `chapter_`, `lesson_`, `board_`, `voice_`, `content_`, `settings_`, `describe_chart_`, `describe_figure_`, `describe_plot_`, `describe_flowchart_`, `error_`, `nav_`). Parameters `{name}`; plurals with the inlang selector form verified in the spike:

```json
"course_chapters": [{
  "declarations": ["input count", "local countPlural = count: plural"],
  "selectors": ["countPlural"],
  "match": { "countPlural=one": "{count} chapitre", "countPlural=other": "{count} chapitres" }
}]
```

`project.inlang/settings.json`: `baseLocale: "fr"`, `locales: ["fr","en"]`, plugin `@inlang/plugin-message-format`. The plugin is resolved from the installed npm package by a relative path, not from the CDN, so builds need no network and the version is pinned by the lockfile. If the SDK refuses a local module path, fall back to the CDN URL pinned to the lockfile's version and record it in `documentation/i18n.md`.

## 4. Backend components

### 4.1 Locale resolution

```python
# app/api/deps.py
def current_user(request, auth) -> User:
    ...
    request.state.locale = user.locale          # the one new line; the lookup already happens

def locale_of(request: Request) -> Locale:
    return getattr(request.state, "locale", None) or parse_accept_language(request.headers.get("accept-language"))
```

No new dependency and no second session lookup: errors raised after authentication find the account's language already on `request.state`; everything earlier (login, register, 401, rate limits) is by definition signed out and uses the header. `locale_of` is not a role marker, so `test_route_guards.py` is untouched.

### 4.2 Errors

`TutorError` (replaces `message_fr`):

```python
class TutorError(Exception):
    code = "internal"; status = 500
    params: Mapping[str, Any] = {}
    @property
    def message_key(self) -> str: return self.code
    def message(self, locale: Locale = DEFAULT_LOCALE) -> str: return render(self.message_key, locale, **self.params)
    def body(self, locale: Locale = DEFAULT_LOCALE) -> dict[str, Any]: return {"code": self.code, "message": self.message(locale)}
    def __init__(self, *args): super().__init__(*args or (self.message(),))     # str(exc) stays the French text
```

Subclasses with values set `self.params` instead of formatting a sentence:

| Class | `params` | Plural / variant |
|---|---|---|
| `SourceLength` | `min`, `max` | none |
| `AuthoringBusy` | `limit`, `count=limit` | `.one` / `.other` |
| `AuthoringQuota` | `retry_at` | none |
| `DocumentTooLarge` | `size_mb` (`max_bytes // 1_048_576`) | none |
| `TooManyPages` | `maximum` | none |
| `DiscussionQuota` | `maximum` | none |
| `WeakPassword(reason)` | `min_length` | key `weak_password.<reason>` |
| `DocumentInvalid(reason, **params)` | per reason | key `document.<reason>` |
| `ConversationClosed(reason)` | none | key `conversation_closed.<reason>` |
| `ContentInvalid(issues)` | `issues` rendered by §4.9 | `body(locale)` overrides |

- `password.check_password` returns `"too_short" | "personal" | None`; `AuthService` raises `WeakPassword(reason)`.
- `DocumentInvalid(reason, **params)` replaces the `message_fr` argument. The two construction sites that both used reason `type` get distinct reasons (`type_unsupported`, `type_mixed`; the final names come from reading `documents.py:164,167`). `_Refusal` carries `reason` and primitive `params` (still picklable) instead of a `message`; `exception()` rebuilds the error.
- `from_code(code)` keeps instantiating no-argument classes.
- `message_fr` is removed. The 5 tests that read it (`test_discussion_service.py:149,175,201`, `test_authoring_runner.py:146,162`) call `.message()`; `documents.py:181` calls `.message()`.

### 4.3 Channels

| Channel | Change |
|---|---|
| HTTP handler `main.py:145` | `lambda request, exc: JSONResponse(status_code=exc.status, content=exc.body(locale_of(request)))` |
| ASGI middleware `middleware.py:56,124` | `exc.body(parse_accept_language(headers.get(b"accept-language")))` from the scope headers; constructor signature unchanged. They run before routing, so the account language is not known (accepted; R5.1 covers it by the signed-out rule). |
| SSE `api/sse.py:73,78,87` | `locale = locale_of(request)` once in `stream_turn`; one helper `_error_event(exc, locale)` replaces the three sites |
| Voice | errors go through the handler; `/api/voice/tool` calls `event_of(outcome, user.locale)` |
| FastAPI `422` | no backend change. `readError` in the frontend already ignores `detail` (§5.6). |

### 4.4 Auth routes and repository

- `UserRepository._user(row)` carries `locale`; `create(..., locale="fr")`; new `set_locale(user_id, locale)`.
- `AuthService.register(email, password, name, locale="fr")`; the route passes `parse_accept_language(request.headers.get("accept-language"))`. `login`/`authenticate` return the stored locale through `_user`.
- `_user_dto` adds `locale`; register, login and `me` share it.
- New route in `api/routes/auth.py`:

```python
@router.patch("/me")
async def update_me(payload: UpdateMeRequest, user: AnyUserDep, auth: AuthServiceDep) -> UserResponse:
    # acts on user.id only; unknown fields are refused by _Model(extra="forbid")
    if payload.locale is not None:
        user = await run_in_threadpool(auth.set_locale, user.id, payload.locale)
    return UserResponse(user=_user_dto(user))
```

Same-origin middleware already covers `PATCH`. An empty body is a no-op returning the user.

### 4.5 Subjects, chapter titles, statuses

- `SubjectInfo.label_fr` → `SubjectInfo.label(locale)` = `render(f"subject.{id}", locale)`. `courses.py:146,165` pass `user.locale`.
- `display_title(position, title, locale)` renders `chapter.title` / `chapter.untitled`. `title` is course text and passes through.
- `authoring_message(chapter, locale)` returns `render(f"authoring.{code}" | f"transcription.{code}", locale)`; the two dicts disappear, the code selection logic stays.
- Every course route that builds a DTO takes `user.locale` from the dependency it already has.

### 4.6 Markers

Outcomes become language-neutral; rendering moves into the one choke point `tool_events.py`.

```python
@dataclass(frozen=True)
class Marker:
    key: str                                  # "marker.exercise"
    params: Mapping[str, str] = field(default_factory=dict)   # {"label": section label} — course text
    def render(self, locale: Locale = DEFAULT_LOCALE) -> str: return render(self.key, locale, **self.params)
```

- Card classes: `marker: ClassVar[str] = "séance ouverte"` → `marker_key: ClassVar[str] = "marker.title"` (and so on). `CLEAR_MARKER` → `Marker("marker.cleared")`. `section.py` and `pace.py` build `Marker("marker.section_review", {"label": …})`, `Marker("marker.section_done", …)`, `Marker("marker.step_ready")`.
- `ToolOutcome.marker: Marker` (was `str`). `event_of(outcome, locale=DEFAULT_LOCALE)` renders it into the event's `marker: str`; the SSE contract is unchanged.
- `marker_for(name, args, locale=DEFAULT_LOCALE)` renders the same keys; `StoredEntry.of(entry, locale)` takes it from the discussion route's `user.locale`.
- Markers never reach the model (`output_of(outcome)` is `outcome.output`; `history.py` maps name and arguments only), so this changes no model input. The French rendering is byte-identical to today's strings.
- Tests that read `outcome.marker` compare `.render()`.

### 4.7 What does not change (R5.7)

`prompts/`, `PromptService`, `tools/*` `output` and `ToolValidationError` text, `curriculum_render.py`, `KIND_LABEL_FR`, `history.py`, `domain/pack.py` messages (still French on `ContentIssue.message`), `voice_service.py` (`"language": "fr"`). No function in these modules gains a `locale` parameter. A test enforces it (§7.1).

### 4.8 Registration and migration order

The migration runs first (the startup schema check refuses to run behind head). `UserRow` and the migration agree on the default; existing rows read `fr`.

### 4.9 Content issues

```python
@dataclass(frozen=True)
class ContentIssue:
    where: str
    message: str                              # French, byte for byte: the repair prompt reads it
    code: str = ""                            # new
    params: Mapping[str, Any] = field(default_factory=dict)   # new
```

- `where` is unchanged: `curriculum-editor.tsx:147` matches the literal `section « id »`.
- `render_issue(issue, locale) -> ContentIssue`: if `issue.code` and `issue.{code}` exist for the locale, returns the issue with the localized `message`; else returns it as is. It also maps the few display words in `where` (`titre`, `document`, `pages`, `page N`, `exercice N`) and leaves `section « id »` and `§ N` as they are.
- `ContentInvalid.body(locale)` renders its issues this way; `agent._repair_message` keeps reading `issue.message` and `issue.where`.
- Producers given codes in this epic: the `issue(...)` helper sites in `pack.py`, the five in `references.py`, and the French `ValueError`s in `curriculum.py:50-90`. The pydantic passthrough (`f"{field} : {msg}"`) gets `code="curriculum.field"` with `field` and `msg` params, so in English it reads `{field}: {msg}` with pydantic's own English `msg`. `transcription.py` issues are model-only and untouched.
- Known gap, accepted by R5.6: any producer without a code shows its French `message` in the English interface. `tests` list the producers without a code so the gap is visible.

## 5. Frontend components

### 5.1 Paraglide wiring

```ts
// vite.config.ts — extra plugins go through the preset's `plugins` option
plugins: [paraglideVitePlugin({
  project: "./project.inlang", outdir: "./src/paraglide", emitTsDeclarations: true,
  strategy: ["custom-account", "custom-header", "baseLocale"],
})],
```

- `src/paraglide/` is generated (gitignored, excluded from eslint). The Vite plugin writes it on `dev` and `build`; scripts generate it elsewhere:

```
"i18n": "paraglide-js compile --project ./project.inlang --outdir ./src/paraglide --strategy custom-account custom-header baseLocale --emit-ts-declarations --silent"
"i18n:check": "node scripts/check-messages.mjs"
"pretest": "npm run i18n && npm run i18n:check"
"typecheck": "npm run i18n && tsc --noEmit"
```

- `src/lib/i18n.ts` registers both strategies:
  - `defineCustomClientStrategy("custom-account", …)`: `getLocale` = `me`-cache `user.locale` if valid, else `document.documentElement.lang` if valid, else undefined (so hydration matches the server's HTML); `setLocale` writes the `me` cache, sets `<html lang>` and notifies. This is the spike's code, kept as is.
  - `defineCustomServerStrategy("custom-header", { getLocale: (request) => parseAcceptLanguage(request?.headers.get("accept-language")) })`. This makes `locale.ts` the one frontend parser. **Unverified** (the spike used the built-in `preferredLanguage`, which parses the same header with a slightly different rule: `en; q=0.8` with a space is mis-parsed). The first implementation task confirms the server-strategy API; if it is unavailable, use `preferredLanguage` and keep `locale.ts` for the error page only, accepting a divergence on malformed headers.
  - `bindLocaleToQueryClient(client)` (client only, from `router.tsx`), `useLocale()` (`useSyncExternalStore`), and `resetLocale()`: sets `<html lang>` to `matchLocale(navigator.languages)` and notifies. `useSignOut` and the unauthorized handler call it after clearing the cache.

### 5.2 Server entry and shell

- `server.ts`: `paraglideMiddleware(request, () => handler.fetch(request, env, ctx))` around the existing call, and, on HTML responses, `Vary: Accept-Language` plus `Cache-Control: private, no-cache` (the spike's `withVary`, extended). The `Vary` header alone is not enough: the production host is AWS Amplify Hosting, whose CloudFront layer respects an app's `Cache-Control` on dynamic routes and does not put `Accept-Language` in its cache key, so a cacheable HTML response could serve one visitor's language to another. `private, no-cache` keeps the language-dependent HTML out of shared caches; static assets keep their own headers. The catch branch calls `renderErrorPage(parseAcceptLanguage(request.headers.get("accept-language")))`.
- `start.ts`: `errorMiddleware` passes the request's locale the same way. `csrfMiddleware` is untouched.
- `__root.tsx`:
  - `<html lang={getLocale()} suppressHydrationWarning>`: signed-in pages are `ssr:false`, so the account language can replace the server's `lang` after hydration.
  - `head()`: the title, description and `og:*` use `m.*()` (they run in the request scope on the server).
  - `RootComponent`: `const locale = useLocale(); <QueryClientProvider><Fragment key={locale}><Outlet /></Fragment></QueryClientProvider>`. A locale change remounts the route tree, which re-evaluates every `m.*()` including memoised and pure-helper output. It is acceptable because a locale change happens only at sign-in, sign-out and on the settings screen, where no live lesson is mounted (R1.6 decided).
  - The 404 and error components call `m.*()` in render.

### 5.3 Conventions that make the refactor mechanical

1. Components and pure helpers import `m` and call `m.key(params)` **inside function bodies**. No `t` threading.
2. **No `m.*()` call at module scope** (it would evaluate once, outside the request, and be wrong across requests on the server). A module-level table holds **message functions**, not strings: `const STATE_LABEL: Record<State, () => string> = { done: m.state_done, … }`, used as `STATE_LABEL[s]()`.
3. Zod schemas are factories called in render (`useMemo(makeLoginSchema, [])`), because `z…min(1, m.x())` at import would freeze the language.
4. Plural ternaries (`> 1 ? "s"`) become plural messages; sentences are never built from fragments. French agreement ("faite(s) sur") is a plural message with full wording per category.
5. Interface numbers go through `lib/i18n-format.ts`: `INTL_TAG = { fr: "fr-BE", en: "en-GB" }`, `formatCount(n)`, `formatMegabytes(bytes)` (unit from a message: `Mo` / `MB`). The board's `charts/format.ts` is untouched.
6. Reducer-created text (`MAX_ROUNDS_NOTICE`, `RESET_FAILED`, the voice markers, `GENERIC_ERROR`) is produced by calling `m.*()` when the event is applied. No locale change occurs during a lesson, so stored text is never stale.

### 5.4 Settings screen and user menu

New files:

| File | Role |
|---|---|
| `src/components/celestin/user-menu.tsx` | Shared `DropdownMenu`: the user's name as trigger, items « Paramètres » (`Link` to `/settings`) and « Se déconnecter ». Replaces `app-bar.tsx:17-24` and `chapter-bar.tsx:50-59`, with a compact trigger on the chapter bar. |
| `src/routes/_auth/settings.tsx` | Route under `_auth`, `head()` title from `m`, renders `AuthPage` + `SettingsPage`. |
| `src/components/celestin/settings/settings-page.tsx` | Shell: title, back control, maps `SECTIONS`. |
| `src/components/celestin/settings/sections.ts` | The registry: `type SettingsSection = { id: string; title: () => string; Component: ComponentType<{ user: User }> }`; `export const SECTIONS: SettingsSection[] = [languageSection]`. Adding a section is one entry. |
| `src/components/celestin/settings/language-section.tsx` | `RadioGroup` of `LOCALES` labelled with `AUTONYM`, current marked; on change: `updatePreferences({locale})`, then `setLocale(locale, { reload: false })` and `router.invalidate()` (so `head()` titles re-evaluate); on failure the group stays on the previous value and an `Alert` shows the error. |
| `src/lib/settings.ts` | `updatePreferences(patch)`: `sendJson(ME_URL, patch, { method: "PATCH" })` (already supported), returns the `User`. |

- Leaving a lesson for the settings is an ordinary navigation (R1.6, decided): the lesson unmounts, an open turn is aborted by `useTutorSession`'s cleanup, and an open voice session is stopped by `useVoiceSession`'s cleanup (which sends its usage beacon). The parcours transcript is not kept, progress is.
- The back control: `router.history.back()` when there is history to go back to, else a `Link` to `/courses`. (`canGoBack` on the TanStack history is assumed; the task verifies it and uses `window.history.length > 1` if absent.)
- Nothing else is rendered (R1.3).
- **Extension path (NFR 4.1.9):** a future section is a component, catalog keys and a `SECTIONS` entry; email/password sections get their own routes on the backend (they need the current password), not extra fields on `UpdateMeRequest`.

### 5.5 Glossary proposal (R6.3, for the user's review)

| Français | English |
|---|---|
| Mes cours / cours / chapitre | My courses / course / chapter |
| Parcours (mode) | Path |
| Discussion / Nouvelle conversation | Discussion / New conversation |
| Leçon · Exercices · Synthèse | Lesson · Practice · Summary |
| Commencer · Reprendre · Continuer · Revoir | Start · Resume · Continue · Review |
| tableau · séance | board · session |
| Étape suivante | Next step |
| Contenu du chapitre | Chapter content |
| Se déconnecter · Paramètres · Langue | Sign out · Settings · Language |
| Célestin | Célestin (unchanged) |

### 5.6 Remaining frontend sites

- `lib/tutor/labels.ts` splits in two:
  - `lib/tutor/prompts.ts`, **French only and never translated**: `REVIEW_MESSAGE`, `START_MESSAGE`, `NEXT_STEP_MESSAGE`, `NEXT_SECTION_MESSAGE`, `ANSWER_MESSAGE`, `VOICE_TOOL_FAILED` (these reach the model).
  - everything else moves to the catalog, `VOICE_ON_MARKER`/`VOICE_OFF_MARKER` included: they only feed transcript marker entries in the reducer (`use-tutor-session.ts:92,98`) and never enter `history`.
- `lib/tutor/client.ts`: `GENERIC_ERROR` becomes a function; the 422 fallback in `readError` (`client.ts:105-113`) uses `m.error_invalid_request()`. Server `message`s pass through as text.
- Zod messages and the `curriculum-editor` `superRefine` texts use the factory pattern (§5.3.3).
- `lib/error-page.ts`: `renderErrorPage(locale: Locale)`, a two-entry inline table (fr, en). Today it is English-only; it follows `Accept-Language`, French by default.
- **Whiteboard chrome:** the fixed words of the board's own cards (`CARD_LABEL`, "Vérifions que c'est compris", "Ce qu'on retient", "Acquis", "À surveiller", « Étape suivante ») are interface text → catalog. The vocabulary the board draws from the course (`MEASURE_NAME`, box-plot "Minimum/Q1/Médiane", statistical axis terms) is course text and stays French (R4.1 amended).
- **`lang` attributes:** `lib/course-language.ts` exports `COURSE_LANG = "fr"` (the follow-up spec makes it per course). `lang={COURSE_LANG}` goes on the tutor transcript container, the whiteboard and its history strip, the pack, path and source views, and chapter title elements. The rest of the page inherits the interface language from `<html>`.
- `document-picker.tsx`, `source-editor.tsx`: `toLocaleString("fr-BE")` → `formatCount`/`formatMegabytes` (§5.3.5).

### 5.7 Enforcement

Both live in `eslint.config.js`, scoped to `src/**` outside `components/ui`, `__tests__`, `test`, `paraglide`:

1. **`no-restricted-syntax`**: `Literal`, `TemplateElement` and `JSXText` nodes whose value matches `/[àâäçéèêëîïôöûùüÿœÀÂÇÉÈÊËÎÏÔÛÙÜŸŒ«»]/` are errors, with an allowlist (via `overrides`) for `lib/tutor/prompts.ts`, `lib/locale.ts` (autonyms), `lib/course-language.ts`, `components/celestin/charts/format.ts` and the board-vocabulary constants. It does not see unaccented French; review and the English-render tests cover those.
2. **A local rule `i18n/no-module-scope-message`** (about 15 lines in the config): reports a `CallExpression` whose callee is `m.<key>` with no enclosing function.

## 6. Error handling

| Case | Behaviour |
|---|---|
| Missing key in `en` (frontend) | Paraglide silently shows French; `i18n:check` fails `npm test` first. |
| Missing key in `en` (backend) | `render` returns the French text and logs `i18n_fallback` (key only); the parity test fails CI first. |
| Unsupported or malformed `Accept-Language` | Skipped; `fr`. Never an error. |
| `PATCH /api/auth/me` with an unsupported locale | `422` (Pydantic `Literal`); the language section shows the generic error in the previous language and the group reverts. |
| `PATCH` while signed out | `401` `not_authenticated`; the existing unauthorized handler runs. |
| Account language differs from the browser's | Sign-in completes, the `me` cache is set, the interface switches to the account's language. |
| Sign-out or a 401 | `resetLocale()` returns the page to the browser's language. |
| A `ContentIssue` without a code, English interface | Shows its French `message`; the known gap of §4.9. |
| SSR crash | `renderErrorPage(locale)` from the header alone. |

## 7. Testing strategy

### 7.1 Backend

- **Pinning:** tests call with no header and no locale, so the default `fr` applies and existing assertions stay (the 5 `message_fr` reads become `.message()`; `test_subjects.py:10` calls `.label("fr")`; `test_password.py` expects reason codes).
- **Catalog:** same keys and same `str.format` fields in `fr` and `en` (via `string.Formatter().parse`); every `TutorError` subclass (found by walking `__subclasses__()`) has a catalog entry in both languages with its params; every `.one` has an `.other`; every marker, subject, authoring and transcription code is covered.
- **Resolution:** `parse_accept_language` against the shared table (§7.4); `locale_of` precedence (state, else header); the `current_user` side effect.
- **Channels:** an English-account request gets English `message` in the HTTP handler, the middleware (`CrossOrigin`, `PayloadTooLarge` via the header), the SSE `error` event and the voice routes, with `code` unchanged.
- **Auth:** register stores the header's language; login and `me` return it; `PATCH` succeeds, rejects an unknown field and an unsupported value, rejects unauthenticated calls and cannot touch another account; `test_route_guards` unchanged.
- **Migration:** upgrade 0005 → 0006 with a pre-existing user reads `fr`; downgrade works; `test_head_matches_the_models`.
- **Wall (R5.7):** the render goldens (`system_text_sha*.txt`, `brief_*`, `overview*`, `state_*`) and the voice session-config test pass untouched; a test renders a turn for an `fr` user and an `en` user and asserts identical system text, tool declarations, history items and tool outputs; a test greps that `prompts.py`, `curriculum_render.py`, `history.py` and `tools/*` do not import `app.domain.messages`.
- **Markers:** `Marker.render("fr")` equals each old literal (a table); the golden SSE transcripts pass unchanged; a stored discussion read as `en` shows English markers.
- **Content issues:** `render_issue` for coded and uncoded issues; the repair prompt text is byte-identical with and without a locale.

### 7.2 Frontend

- **Pinning:** `src/test/setup.ts` (from the spike) imports `@/lib/i18n` and sets `<html lang="fr">`; in the node environment Paraglide falls back to French. `vitest.config.ts` gains `setupFiles`. The route harness's `USER` gains `locale: "fr"` and a `settings` route. No existing assertion changes.
- **Pure:** `locale.ts` against the shared table; `i18n.ts` (client strategy order, `setLocale` re-render fr→en→fr through `useLocale`, `resetLocale`).
- **Catalog gate:** `i18n:check` (missing, extra and variable-mismatch keys, unknown locale files) runs in `pretest`.
- **Components:** the settings screen (entry in both bars, current language marked, a change re-words the page, a failed `PATCH` reverts and shows the error); the sign-in page rendered with `en` and `fr` (title, form labels, `lang`); a `describe.ts` and a plural case per locale; the lesson's learner messages (`REVIEW_MESSAGE`, …) are the French strings with the interface in English; board notation (`formatPair`, intervals) unchanged under `en`; `lang="fr"` present on the transcript and board containers.
- **Server:** `curl` checks documented as a manual checklist: `/login` with `en-GB`, `fr-BE,fr;q=0.9`, `de`, no header, and the `Vary` header. The spike's build and Node-server run passed. On the Amplify preview, `curl` `/login` twice with different `Accept-Language` headers and check that each response carries its own language and `Cache-Control: private, no-cache`.

### 7.3 Manual

Per `documentation/running-locally.md`: one pass per language (sign-in, registration, settings, a course, a chapter in preparation, a lesson with a drawing, a content-editor refusal, a refused upload, a voice session, the error page).

### 7.4 Shared case table

`backend/tests/fixtures/accept_language_cases.json` ↔ `frontend/src/lib/__tests__/accept_language_cases.json`: byte-identical, formatted with prettier, compared by a frontend test (the existing convention for the flowchart, figure and plot tables). Cases: `fr-BE`, `en-GB`, `en; q=0.8, fr`, `de,en;q=0.5`, `de-DE`, `*`, `q=0`, malformed `q`, empty, absent, uppercase, `EN`.

## 8. Performance

- No extra request: the locale comes with `Accept-Language` (signed out) or the `me` response (signed in). The backend adds one attribute write per request.
- Paraglide tree-shakes per message; both languages of a used message sit in the same module. The inactive catalog costs bytes, not a render delay; no catalog fetch exists.
- A language change is a cache write plus a route-tree remount and `router.invalidate()` on a page with no queries.
- HTML responses are `Vary: Accept-Language` and `Cache-Control: private, no-cache` (§5.2), so neither the browser's shared caches nor Amplify's CloudFront can serve one language to another. The cost is no CDN caching of the SSR shell, which is only the sign-in and registration pages (authenticated routes are `ssr:false`).
- Backend rendering is a dict lookup and `str.format`.

## 9. Security considerations

- Every language value (header, body) is matched against `LOCALES` before use and never interpolated into a path, query, header or HTML. `Literal` validates the `PATCH` body.
- Catalog parameters are rendered as text. The frontend never uses `dangerouslySetInnerHTML` for messages; backend `message` is JSON text shown as text. A course name or chapter title in a message cannot inject markup.
- The `PATCH` route uses `AnyUserDep`, acts on `user.id` only, passes the same-origin middleware and the route-guard test.
- No cookie, no new stored data about a signed-out visitor; the language set at registration comes from the server's reading of the header.
- `ContentIssue.params` can carry course text; it is rendered, never logged.

## 10. Monitoring and observability

- No locale in log lines or event names (NFR 4.3.5). Existing events are unchanged.
- One new backend warning, `i18n_fallback` with the catalog key only, for a missing English entry reached at runtime.
- Frontend: no telemetry added. The silent-fallback hazard is closed by `i18n:check`, not by runtime reporting.

## 11. Documentation to update with the implementation

`documentation/i18n.md` (new): the three languages, resolution table, catalog conventions of §5.3, how to add a string, a section or a language, the wall, the shared table. `documentation/index.md`, `documentation/accounts-and-courses.md` (locale, settings route, `PATCH`), `frontend/CLAUDE.md` (stack, `src/paraglide` is generated, the scripts, the lint rules, the prompts/labels split), `backend/CLAUDE.md` (messages catalog, `message_fr` gone, the shared table), root `CLAUDE.md` (the invariant « UI copy … in French » becomes: interface copy in either language, tutor speech in the course's language, French for now), `specs/product.md` §6.8 (settings screen; interface language), `specs/index.md`.

## 12. Risks

- **Amplify target:** production is AWS Amplify Hosting (Nitro `aws_amplify` preset, a Node.js server), where `AsyncLocalStorage` is native. The Nitro preset is `aws_amplify`, set in `vite.config.ts`. The i18n code assumes only Node-compatible APIs. Risk: CloudFront caching of language-dependent HTML, closed by `Cache-Control: private, no-cache` (§5.2) and checked on the Amplify preview.
- **Server strategy API** (`defineCustomServerStrategy`) unverified; fallback in §5.1.
- **Local plugin path** for `@inlang/plugin-message-format` unverified; CDN fallback pinned to the lockfile version.
- **Tools that type-check on their own** need `src/paraglide` generated first: the Vite plugin writes it on `dev` and `build`, and `npm run typecheck` runs `npm run i18n` before `tsc`.
- **Breadth:** about 45 frontend files and the marker, error and issue plumbing change in one epic. The French output is pinned byte-for-byte by the existing tests, so a regression in French is loud; a regression in English is caught only by the parity gates and the English-render tests.
- **`ContentIssue` coverage** is partial by design (§4.9).
