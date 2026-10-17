# Pipeline evaluation: two runs compared

Sentences: `llm/parse/data/test_claude.csv` (written by Claude; not real student data).

| | `pipeline_eval_linear_rule_test_claude.json` | `pipeline_eval_linear_model_test_claude.json` |
| --- | --- | --- |
| Clause classifier | linear model (llm/parse/output/linear_model.json) | linear model (llm/parse/output/linear_model.json) |
| Ranker | rule: minus the sum of z-scores of the cared-about features | trained pairwise model (llm/rank/model.json) |
| Parsed conditions equal the hand-written ones | 88/142 (62%) | 88/142 (62%) |
| Planned from parsed conditions, some pick breaks a hand-written hard condition | 6/105 (6%) | 6/105 (6%) |
| Picks that break one | 17/311 (5%) | 17/311 (5%) |
| Same first pick as with the hand-written conditions | 88/100 (88%) | 94/100 (94%) |
| Same three picks | 85/100 (85%) | 84/100 (84%) |
| Seconds, sentence to recommendation (median, max) | 0.10, 0.30 | 0.16, 0.43 |

With the same hand-written conditions, the two runs put a different timetable first in 40/106 (38%) of the sentences both could plan.
