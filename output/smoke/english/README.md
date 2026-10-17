# English site, browser check, 2026-10-17

The page was rebuilt to docs/DESIGN.md: white paper, ink-blue text, one accent (jacaranda), Atkinson
Hyperlegible Next only (Google Fonts, falling back to system-ui), square corners, no cards, shadows or
gradients. The one animation is the underline drawn under each clause of the student's sentence when it
is read (150 ms each, 60 ms apart, `cubic-bezier(0.23, 1, 0.32, 1)`; shown at once under
`prefers-reduced-motion`, and not replayed when an answer redraws the read-back).

Checked in the preview browser with the real parser on the Windows GPU (uniplan-parse-7b-r2), units
ENGG2112 and AMME2301, 2026 S2C. Sentences were written for this check (one is the example in
DESIGN.md), not taken from any test set.

| Screenshot | What it shows |
| --- | --- |
| `01_desktop_underlines_drawing.jpg` | 1280 px, the moment after Read sentence: the first underline is being drawn |
| `02_desktop_read_back.jpg` | The read-back: each clause underlined, its note beside it, a "Which do you mean?" question as two options, the lunch offer as its own line |
| `03_desktop_results.jpg` | "3 timetables, from 5,664 that fit"; option 1 marked with the accent; week view and the four actions |
| `04_desktop_no_timetable.jpg` | "No timetable fits all of these" with one-change fixes and the activities panel |
| `05_mobile_read_back.jpg` | 375 px: notes move under their clause; no sideways scrolling |
| `06_mobile_results.jpg` | 375 px results; "3 h 14 min" stays on one line |
| `07_mobile_week_scrolls_in_place.jpg` | 375 px: the week grid scrolls sideways inside its own box (343 px wide, grid 560 px) |
| `08_dark_results.jpg`, `09_dark_read_back.jpg` | Dark theme (paper #14161D, ink #E7E8EE, accent #A99BEA) |
| `10_keyboard_focus_on_an_answer.jpg` | Keyboard focus: 2 px accent outline, 2 px offset, on the chosen answer |

## Keyboard walk-through

Tab order: skip link, brand, semester, theme, unit field (arrow keys and Enter pick a suggestion),
sentence (Enter reads it), Read sentence, then each clause's "Leave this out" and its question. Each
question, setting and view switch is a radio group with one tab stop; arrow keys move and choose.
Find timetables moves focus to the result heading; then the view switch, What matters, each option's
days (a real button), Compare, the four actions and the tabs (arrow keys move between tabs).

Found and fixed during the walk-through:
- After an answer re-read the sentence, focus fell to the page; it now returns to the chosen answer.
- After Find timetables, focus fell to the top of the page; it now moves to the result heading.
- Choosing an option or a priority redrew the list and dropped focus; it now stays on the same control.
- The week grid showed its own vertical scrollbar (the last hour label overhung by 9 px).

## web-design-guidelines review (Vercel Web Interface Guidelines, fetched 2026-10-17)

Fixed (real problems):
- `#result` and the read-back were `aria-live`, so every redraw would be read out in full; a one-line
  status (`#announce`) now says what happened ("Read 3 parts of your sentence, with 1 question to
  answer.", "3 timetables, from 5,664 that fit").
- Option cards were `role="button"` with buttons inside; the days are now the button.
- No `h1`; heading levels skipped (settings h3 under no h2, hints h4 under h2).
- A wrong setting did not move focus to the field; it now does.
- "Delete saved answers" deleted at once; the first press now asks for a second press, on the page.
- Native selects had no explicit colours for Windows dark mode; no `theme-color`; headings not balanced;
  very long words could overflow a note; no tap and touch-action settings; option cards had no hover state.
- First-person copy ("Save my answers", "Delete my answers", "my friend's classes").

Not changed, because docs/DESIGN.md decides otherwise or the rule does not apply: Title Case (the design
asks for sentence case); `Intl.DateTimeFormat` (dates are written in the exact form DESIGN.md gives,
"Mon 12 October", from ISO dates without time zones); straight apostrophes in copy; animating
`background-size` rather than transform (the underline must follow a clause that wraps onto two lines).

No console errors and no failed requests on the pages checked. The punctuation check from the write
skill finds no dashes, middle dots, arrows or exclamation marks in the visible copy.
