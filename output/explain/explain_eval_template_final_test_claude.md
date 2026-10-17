# Reason fact-check evaluation (template only)

Sentences: `llm/parse/data/test_claude.csv`, written by Claude (Opus 5.5) — **not real student data**. Conditions are the file's hand-written answers (not `parse()` output); timetables come from the committed 2026 S2C snapshots. Model output was produced with temperature 0 and seed 0.

| | |
| --- | --- |
| Sentences | 142 |
| Planned (feasible) | 106; not planned: {'no_feasible': 36} |
| Recommended timetables | 314; with a time clash or a broken hard condition: 0 |
| Template reasons passing the checker | 314/314 (100%) |
| Pick 1: main reason = the model's biggest difference from pick 2, template | 98/106 (92%) |
| — the reason shown (model rewrite if it passed, else template) | 98/106 (92%) |
| Model sentences returned | 0 (requests by status: {'template': 106}) |
| Model sentences that passed and were shown | 0/0 |
| — pick 1 | 0/0 |
| — pick 2 | 0/0 |
| — pick 3 | 0/0 |

Rejected, by first failed check: none

The checker's rules were refined after spot-checking earlier runs on these same sentences, so this pass rate is in-sample and likely optimistic for new sentences.

Passing means every claim the checker can read (weekdays, clock times, amounts with units, best-of-picks and comparison words, topics it has no facts for) matched the timetable. Claims it cannot read are not verified, so the passed sentences below should be spot-checked by a person.

## Passed model sentences (first 20)

| id | pick | model sentence | template it rewrote |
| --- | --- | --- | --- |

## Rejected model sentences (first 30)

| id | pick | why | model sentence |
| --- | --- | --- | --- |
