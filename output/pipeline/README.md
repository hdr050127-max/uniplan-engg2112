# End-to-end pipeline results (`scripts/evaluate_pipeline.py`)

Each sentence is planned twice on the same courses: with its hand-written conditions and with what
`parse()` reads. Sentences are written by Claude, not real students. File names end in the test set.

## Final (models frozen)

Parser `ollama-short:uniplan-parse-7b-r2` on the Windows RTX 4090 (no sentence fell back to the
linear model), ranker `llm/rank/model.json`, template reasons; run under `llm.gpu_lock`.

| | v1 `test_claude.csv` | v2 `test_claude_v2.csv` |
| --- | --- | --- |
| Sentences | 142 | 126 |
| Parsed conditions equal the hand-written ones | 111 (78%) | 101 (80%) |
| Plannable: hand-written / parsed / both / neither | 106 / 104 / 101 / 33 | 87 / 84 / 83 / 38 |
| Planned from parsed conditions, some pick breaks a hand-written hard condition | 4 / 104 (4%) | 2 / 84 (2%) |
| — picks that break one | 12 / 307 (4%) | 6 / 248 (2%) |
| Same first pick as with the hand-written conditions | 98 / 101 (97%) | 81 / 83 (98%) |
| Same three picks | 92 / 101 (91%) | 76 / 83 (92%) |
| Seconds from sentence to recommendation (median, max) | 0.55, 1.08 | 0.51, 1.08 |

Earlier runs (round-1 linear parser, rule vs trained ranker, v1 only) are kept as
`pipeline_eval_linear_*_test_claude.*` and the comparison file next to them.

## Closest timetables when nothing fits (added after the final exam)

`scripts/evaluate_nearest.py`, files `nearest_eval_exam.*`. Added on 2026-10-17 after the final exam
(docs/DESIGN.md 10.1); it does not change any number above, because it only runs when the strict
search finds nothing. The student's limits become soft, a real clash never does: each clash-free
timetable is measured by how many limits it breaks, then by how much (minutes a week), and ties go to
the ranking model. If the units clash even without the limits, one lecture is watched as a recording
(the one missing the least class time). Exam sentences with their hand-written conditions, no model
calls, written by Claude (not real students).

| Final exam (`llm/parse/exam/exam.csv`) | |
| --- | --- |
| Sentences with no timetable under the strict conditions | 110 / 304 |
| — now given the closest timetables | 110 / 110 |
| — by watching one lecture as a recording | 0 (the exam's unit sets never clash on their own) |
| Pick 1: limits broken, mean (1 / 2) | 1.18 (90 / 20) |
| Pick 1: amount broken, minutes a week (median, mean) | 111, 158 |
| Pick 1: which limits | times to avoid 103, days a week 15, hours a day 9, lunch 3 |
| Recommended timetables with a real clash | 0 / 293 |
| Template reasons passing the fact check | 293 / 293 |
| Seconds for the fallback plan (median, max) | 0.34, 1.38 |

The recording path is covered by `tests/test_uniplan_nearest.py` on real data (a pinned ENGG2112
Tutorial 06 meets when AMME2301's only Lecture1 does; the plan watches AMME2301 Lecture1). A timetable
that fits is unchanged with the fallback switched on (also locked by a test).
