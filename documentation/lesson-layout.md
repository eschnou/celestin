# The lesson's layout

How the séance screen (and the discussion, which shares its frame) is put together on a desktop and on a
phone. Most students work on a smartphone, so the phone layout is the one to judge a change by. It was
built without an SDD spec, at the user's request; the reasoning is below.

## Two frames, one tree

`TutorBoardSplit` (`components/celestin/tutor-board-split.tsx`) is the frame both modes use. `useIsDesktop`
(`hooks/use-is-desktop.ts`, the `lg` breakpoint, 1024 px) picks one of two layouts and mounts only that one,
so there is never a second copy of the board or the KaTeX trees.

|          | Desktop (≥ 1024 px)                                       | Phone / tablet portrait (< 1024 px)                                 |
| -------- | --------------------------------------------------------- | ------------------------------------------------------------------- |
| Frame    | tutor column left, board right, resizable divider         | the board takes the screen; under it the caption and the composer   |
| Top bar  | one line: course, chapter, language, modes, content, user | `←`, the two modes sharing the bar, one `⋯` menu                    |
| Path     | strip under the tutor's header                            | strip above the board (`top`), a flat line                          |
| Célestin | header, transcript, composer                              | **caption** (his last message), composer; the transcript is a sheet |

`TutorBoardSplit` provides `CompactLayoutProvider` on a phone; `useCompactLayout()` (`compact-layout.ts`) is
how the tutor column, the composer and the strip follow without the lesson and the discussion each passing
a flag down. Components used outside the frame (tests, the standalone discussion route's bar) get `false`.

## The phone layout, piece by piece

- **Bar** (`chapter-bar.tsx`): the arrow goes back to the course (its accessible name is the course's name);
  `ModeSwitch compact` gives each mode half of the bar; `UserMenu compact` is a `⋯` button whose menu starts
  with the user's name, then « Contenu du chapitre » (passed as `children`), settings, sign-out.
- **Path** (`chapter-path.tsx`): the strip and the map sheet with the map's open state. The lesson builds it
  once and hands the same element to `TutorBoardSplit` (`top`, phone) and `TutorColumn` (`path`, desktop);
  only one is ever mounted. `ChapterStrip compact` drops the card, the chapter title and the shadow, and
  puts the count beside the current section. A discussion has no path: its `top` is the chapter's title.
- **Board** (`whiteboard.tsx`): no « Tableau » label, margins halved (`max-lg:` variants, the same
  breakpoint), the history strip only from the second card, the title card does not repeat its eyebrow, and
  « Étape suivante » is a full-width button that is absent (not greyed) until Célestin offers the next step.
- **Caption** (`tutor-caption.tsx`): the last message of Célestin (three lines, one while the keyboard is
  up), a failure that came after it (red, with « Réessayer »), the voice status and countdown, a spinner
  while he answers a line of the learner's. Tapping it opens the whole conversation in a bottom sheet,
  scrolled to its end; a board marker there shows the card and closes the sheet. A discussion's
  « Nouvelle conversation » button sits beside it. The learner's own lines are not in the caption.
- **Call button** (`call-button.tsx`): the telephone that opens the real-time voice session, beside his name on a
  desktop and at the right of the caption row on a phone (the row is always there, for it). The composer's
  microphone is dictation, not the call: [voice.md](./voice.md).
- **Composer** (`composer.tsx`, shared with the desktop column): 40 px touch targets and a 16 px field on a
  phone (below 16 px iOS zooms the page on focus); the symbol palette is one row that scrolls sideways.

## The keyboard

`100vh` ignores the on-screen keyboard and Safari's collapsing bar. `useVisualViewport`
(`hooks/use-visual-viewport.ts`) reads `window.visualViewport`: its height, its offset, and `keyboardOpen`
(more than 150 px lost, so a bar sliding away does not count). `LessonFrame` (same file as the split, used by
the lesson and the discussion route) sets the screen's height to it on a phone, over a `100dvh` fallback;
the split hides `top` and the caption shrinks to one line while the keyboard is up, so the board keeps what
room is left. Without the API (jsdom, an old browser) the state is unknown and the CSS height stays.

## Tests

jsdom has no `matchMedia`: `stubLayoutApis()` (`src/test/jsdom-stubs.ts`) answers « phone » by default and
`stubLayoutApis({ desktop: true })` answers « desktop ». The English sweep of the lesson runs on both, plus
the conversation sheet on a phone; `useIsDesktop` itself stays on its desktop default when there is no
`matchMedia`. `tutor-caption.test.tsx`, `use-visual-viewport.test.tsx`, the compact strip and the phone bar
(`settings-page.test.tsx`) cover the new pieces.

## Not done

- No swipe between the board's cards: on a phone the history strip (from the second card) is the way back.
- A tablet in portrait (768–1023 px) gets the phone layout; a two-column layout from `md` is a choice to
  make with a real tablet in hand.
- (The camera is live: [work-reading.md](./work-reading.md).)
- The keyboard behaviour is tested with fakes and checked at 390 × 760 in a desktop browser, not on an iPhone
  or an Android with a real keyboard: do that before relying on it.
