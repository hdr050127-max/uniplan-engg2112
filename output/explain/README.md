# Reason fact-check results (`scripts/evaluate_explain.py`)

Sentences: `llm/parse/data/test_claude.csv` (v1; written by Claude; not real student data), planned with
their hand-written conditions on four committed course combinations. The checker was refined while
spot-checking runs on these same sentences, so every pass rate here is in-sample and optimistic.
File names end in the test set they ran on (`_test_claude` = v1; `--test-file` picks another). The
out-of-sample numbers will come from v2 (`test_claude_v2.csv`), which has not been run.

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
