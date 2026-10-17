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
