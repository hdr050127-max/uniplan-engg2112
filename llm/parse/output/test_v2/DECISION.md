# Test v2: round 1 vs round 2, and the run-time parser

Scored by the coordinator on 2026-10-17 (20:15), once per model, on `data/test_claude_v2.csv`
(126 Claude-written English sentences, 146 clauses; frozen before any round-2 work; SHA-256
4b615558…25b8d5). Not real student data. The adoption rule was committed before the round-2 7B was
scored (95d6e43, `data/TEST_SOURCES.md`).

- `parse_results.*`, `predictions/`: the round-2 code (splitter and reading fixes, e7432c9).
- `round1_code/`: the same test run with the round-1 code (66394b6), to measure the code changes alone.

## Code changes alone (same round-1 7B QLoRA model)

| | round-1 code | round-2 code |
| --- | ---: | ---: |
| split exactly right | 69.8% | 81.7% |
| sentences with every condition right | 67.5% | 79.4% |
| unavailable-time field right | 83.3% | 88.9% |

## Round-2 7B QLoRA vs round 1 (round-2 code)

| | round 1 `uniplan-parse-7b` | round 2 `uniplan-parse-7b-r2` |
| --- | ---: | ---: |
| clause accuracy | 91.8% | 93.8% |
| sentences with every condition right | 79.4% | 80.2% |
| validation accuracy (278 clauses, Ollama q4) | 95.0% | 95.3% |

Per label (correct / total on v2): blocked_time 48 → 55 / 56; prefer_no_early_late 14 → 12 / 14;
max_days 10 → 9 / 10; other 16 → 15 / 20; the rest unchanged.

- Round 2 fixed 8 clauses: "only these days" read as a day limit (4), soft-worded named days read
  as other (2), and unhedged clock times read as preferences (2).
- It broke 5: two hedged clock times now read as hard blocks (the over-correction the rule warned
  about); "four campus days or fewer, if you can" read as fewer-days; "Early starts don't worry
  me" read as a preference; and a lunchtime job read as lunch.
- The net gain is 3 clauses and is not statistically significant (McNemar, 8 vs 5). The direction
  of the errors still changed. Round 1 lost hard conditions in 8 clauses, so a pick could clash with
  work. Round 2 loses a hard condition in 2 clauses and makes 2 preferences too strict.

## Decision

All three adoption conditions hold. Two labels round 2 did not target each dropped by one clause,
which the rule allows. The targeted gains came from blocked_time, not from calling hedged times
blocked. So **`uniplan-parse-7b-r2` becomes the run-time parser**.

Two settings were chosen on the validation set, not on v2:
- Rule guard off: it does not change validation clause accuracy and lowers validation sentence
  accuracy.
- Offline fallback: linear-r1 (88.8% vs 87.8% validation accuracy).

v2 has now been read in detail. It will not be used to design anything further; the final exam
(a new test set) is written after everything is frozen.
