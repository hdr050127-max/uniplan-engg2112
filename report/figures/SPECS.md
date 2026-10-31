# Five figure schemes (2026-10-31)

Shared, in every scheme
- Print sizes: Fig 1 pipeline 6.27 × 1.0 in; Fig 2 Pareto 2.95 × 2.4 in (half width, wrapped); Fig 3 results 6.27 × 1.75 in; Fig 4 app 6.27 × 1.7 in; Fig 5 appendix 6.27 × 2.0 in.
- Text on a figure: axis titles with units, tick numbers, panel letters, method names (they are the category axis), pick numbers 1–3. Nothing else. Legends and meaning go in the caption.
- Every value from report/figures/data.js (generated from the tables and the Pareto export). Marks encode one thing each.
- Type sizes follow the Nature range: 5–7 pt on the page (ticks 6.5, titles 7, panel letters 7–8). Lines 0.25–1 pt.
- Pareto x range 5.3–7.3 h (7 dominated types beyond it are omitted; caption says so), y 2.8–5.0 days.
- Colour-blind safety checked with the dataviz validator for every two-colour pair.

## 1 Journal
Nature/Science house style. Helvetica Neue; ticks 6.5 regular, titles 7 regular, panel letters 8 bold lowercase.
Axes: L-frame, 0.5 pt black, ticks outward 2.5 pt. No grid.
Colour: Okabe–Ito blue #0072b2 (the deployed system, picks) and vermillion #d55e00 (the front); greys for the rest; black for the baselines.
Marks: filled circles with a 0.6 pt white edge. Others r 1.5, front r 2.8, picks r 4.6 with white numeral.
Pipeline: 0.5 pt black boxes; learned stages filled light grey; thin arrows with small filled heads.
Screenshots: 0.5 pt grey frame; bold letters.

## 2 Document
Set in the report's own face, Latin Modern Roman, so the figures read as part of the typeset page (Springer/CUP book figures).
Ticks 6.5, titles 7 italic, panel letters small caps.
Axes: L-frame, 0.4 pt black, ticks outward 2 pt. No grid.
Colour: one bordeaux #7b1e2b for what is ours (deployed, picks); black for the front and baselines; others hollow grey circles (book convention).
Marks: others hollow r 1.5 stroke 0.5; front filled black r 2.6; picks filled bordeaux r 4.6 with white numeral.
Pipeline: 0.4 pt rules, learned stages shaded; stage names in small caps.
Screenshots: hairline black frame; "(a)" "(b)" in small caps.

## 3 Swiss
International Typographic Style. Helvetica Neue with weight contrast: ticks Light 6.5, titles Medium 7, panel letters Bold 8.
Axes: no axis lines; light horizontal hairline grid (#d9d9d9, 0.4 pt) and a 0.6 pt black baseline. Ticks are labels only.
Colour: black and Swiss red #e2001a; greys #9b9b9b for the rest.
Marks: geometric, no edges. Others r 1.5 grey, front r 2.8 black, picks r 4.6 red with white numeral in Bold.
Pipeline: modular grid of equal boxes; learned = solid black with white text; code = 0.6 pt outline; arrows are 0.6 pt rules without heads, a 2 pt gap at each box.
Screenshots: no frame; a 1 pt black rule above each panel, letter at its left end.

## 4 Monochrome
Black, white and grey only; difference by shape and fill, as in an engineering drawing. Avenir Next (geometric): ticks 6.5 regular, titles 7 medium, panel letters 7 medium in parentheses.
Axes: full box, 0.5 pt black, ticks inward 2.5 pt on left and bottom. No grid.
Marks: others small filled grey r 1.4; front hollow circles 0.8 pt stroke r 3; picks filled black r 4.6 with white numeral. Front line dashed 0.6 pt (2 2).
Results: whiskers with 2 pt end caps; deployed filled black, baselines hollow, others grey.
Curve: black line, ±SD as a light grey band; bars mid grey #777 with 0.4 pt black outline.
Pipeline: learned stages have a double border (ISO "predefined process"); arrows with filled triangular heads.
Screenshots: 0.6 pt black frame, "(a)" "(b)".

## 5 Tufte
Maximum data-ink. Palatino: ticks 6.5, titles 7 italic, panel letters 7 italic.
Axes: range frames, 0.5 pt warm grey #5a5753: the axis line spans only the data range, labelled at its ends and at round values inside. No box, no grid.
Colour: ink #3b3836 and one accent, burnt orange #b5451b, for the picks; the front is drawn in ink; others are ink at 45 %.
Marks: others r 1.3; front r 2.6; picks r 4.4 with white numeral. Front line 0.5 pt ink, solid.
Results: dot plots with thin interval lines; the category axis has no line.
Bars: Tufte bars, white gridlines cut through the bars at tick values, no axis line. Curve: thin line, band in 12 % accent.
Pipeline: no boxes. Stage names in Palatino with thin arrows; learned stages in the accent; input and output in italic.
Screenshots: no frame; italic letters top-left.
