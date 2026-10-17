# Reason fact-check results (`scripts/evaluate_explain.py`)

Sentences: `llm/parse/data/test_claude.csv` (v1; written by Claude; not real student data), planned with
their hand-written conditions on four committed course combinations. The checker was refined while
spot-checking runs on these same sentences, so every pass rate here is in-sample and optimistic.
File names end in the test set they ran on (`_test_claude` = v1; `--test-file` picks another). The
out-of-sample numbers (v2 and the exam) are in the sections below.

| File | Ranker | Reasons | Model and machine | Checker |
| --- | --- | --- | --- | --- |
| `explain_eval_qwen2.5-7b_test_claude.*` | rule (no `model.json` yet) | template v1 | qwen2.5:7b, Windows RTX 4090 | as of `550bf73` |
| `explain_eval_template_before_test_claude.*`, `explain_eval_qwen2.5-7b_before_test_claude.*` | trained (`llm/rank/model.json`) | template v1: best-of-picks first | qwen2.5:7b, this Mac | as of `8676873` |
| `explain_eval_template_after_test_claude.*`, `explain_eval_qwen2.5-7b_after_test_claude.*` | trained | template v2: why pick 1 beats pick 2 (`llm.rank.contributions`) and its cost | qwen2.5:7b, this Mac (sentences re-checked with the final rules) | final |

## Before and after grounding reasons in the ranking model (same picks, same machine)

| | Before | After |
| --- | --- | --- |
| Recommended timetables with a clash or broken hard condition | 0 / 314 | 0 / 314 |
| Template reasons passing the checker | 313 / 314 (one was too long) | 314 / 314 |
| Pick 1: main reason = the model's biggest contribution difference, template | 74 / 106 (70%) | 98 / 106 (92%) |
| — reason actually shown (7B rewrite if it passed, else template) | 67 / 106 (63%) | 98 / 106 (92%) |
| 7B rewrites that pass the check and are shown | 187 / 314 (60%) | 184 / 314 (59%) |
| — pick 1 | 66 / 106 (62%) | 68 / 106 (64%) |
| Seconds per 7B request on this Mac (median) | 18.6 | 19.4 |

The after column uses stricter rules than the before column (direction and per-day/per-week of each
stated difference must match; "最早/最晚" needs a time), added after spot-checking the after run:
7B had written "多 2 天" for "少 2 天", "每天少换 0.9 次楼" for a weekly figure, and "最晚下课"
without a time. With the checker as first committed for the new reasons (`d37ef49`), before
those rules, the after run passed 194 / 314 (62%).
On the Windows RTX 4090 the same 7B request takes about 1 second.

## Final results (models frozen; `_final_` files, qwen2.5:7b on the Windows RTX 4090)

v1 (`test_claude.csv`) is in-sample for the checker; v2 (`test_claude_v2.csv`, also written by Claude,
frozen before round 2) was never used to write or tune it, so v2 is the out-of-sample result.

| | v1 (in-sample) | v2 (out-of-sample) |
| --- | --- | --- |
| Plannable sentences | 106 / 142 | 87 / 126 |
| Recommended timetables with a clash or broken hard condition | 0 / 314 | 0 / 256 |
| Template reasons passing the checker | 314 / 314 | 256 / 256 |
| Pick 1: main reason = the model's biggest contribution difference, template | 98 / 106 (92%) | 74 / 87 (85%) |
| — reason actually shown | 95 / 106 (90%) | 73 / 87 (84%) |
| 7B rewrites that pass the check and are shown | 193 / 314 (61%) | 143 / 256 (56%) |
| — pick 1 / 2 / 3 | 67% / 66% / 51% | 64% / 56% / 46% |
| Seconds per 7B request (median, max) | 1.2, 4.3 | 1.2, 2.0 |

Manual check of 30 random v2 rewrites that passed (by Claude, the integration session): 29 state only
true facts; 1 names the wrong pick as the comparison ("比第3份" for a difference with pick 1), because
the checker accepts any "第 N 份" as the reference. About 6 more give a difference without saying which
pick it is against. Rules were frozen at this point, so this is reported, not fixed.

## English reasons (docs/DESIGN.md, 2026-10-17)

The site is now in English, so the template, the 7B prompt and the checker were rewritten in English
with the same checks (weekdays, clock times, amounts with units, which option a difference is against,
best-of-picks words, comparisons, opinions, topics with no facts). Files end in `_en_<test set>`.
The English rules were written and then refined once on v1 only (three phrasings the checker misread,
commit `6e602cc`), then frozen before v2 and the exam were run. All runs: qwen2.5:7b on the Windows
RTX 4090, temperature 0, seed 0. Sentences are written by Claude, not real students.

| | v1 Chinese | v1 English | v2 Chinese | v2 English | Exam Chinese | Exam English |
| --- | --- | --- | --- | --- | --- | --- |
| Plannable sentences | 106 / 142 | 106 / 142 | 87 / 126 | 87 / 126 | 194 / 304 | 194 / 304 |
| Recommended timetables with a clash or broken hard condition | 0 / 314 | 0 / 314 | 0 / 256 | 0 / 256 | 0 / 571 | 0 / 571 |
| Template reasons passing the checker | 314 / 314 | 314 / 314 | 256 / 256 | 256 / 256 | 571 / 571 | 571 / 571 |
| Pick 1: main reason = the model's biggest difference, template | 98 / 106 (92%) | 102 / 106 (96%) | 74 / 87 (85%) | 84 / 87 (97%) | 165 / 192 (86%) | 185 / 192 (96%) |
| — reason actually shown | 95 / 106 (90%) | 98 / 106 (92%) | 73 / 87 (84%) | 80 / 87 (92%) | 162 / 192 (84%) | 175 / 192 (91%) |
| 7B rewrites that pass the check and are shown | 193 / 314 (61%) | 76 / 311 (24%) | 143 / 256 (56%) | 73 / 255 (29%) | 384 / 571 (67%) | 194 / 570 (34%) |
| — pick 1 / 2 / 3 | 67% / 66% / 51% | 17% / 22% / 35% | 64% / 56% / 46% | 25% / 28% / 33% | 73% / 64% / 65% | 19% / 39% / 45% |
| Seconds per 7B request (median) | 1.2 | 0.8 | 1.2 | 0.8 | 1.3 | 0.8 |

The "main reason" rows find the feature a reason names first by matching words, and the English word
lists differ from the Chinese ones, so those two rows compare less well across languages than the others.
v1 English was checked again without calling the model after the v1 refinement (`--recheck`), so it
counts 311 rewrites instead of 313.

Most English rewrites are rejected because the 7B drops which option a difference is against ("Fewer
days on campus, but more waiting.") or adds differences the draft does not state. The checker's job is
to keep those off the page, and it did.

Manual check of 30 random English rewrites that passed (v2 and exam, seed 2112, by Claude, the
integration session): 17 state only true facts, 3 are vague ("same as option 1"), and 10 are wrong or
claim something the draft does not say. Examples: "fewer days on campus" for a draft that says less
time on campus on the longest day (both mention "campus"); "earlier classes" for less early class time;
"later finish times", which no draft states; "more time between classes" for more class outside the
preferred hours. The Chinese check of the same kind found 29 of 30 correct. So the English checker
lets through more wrong rewrites than the Chinese one. These failure modes were found on v2 and the
exam, so they were recorded, not fixed (fixing them now would tune on the test sets). Templates are
true by construction in both languages.
