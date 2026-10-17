# Where the parsing test sets come from

| File | Written by | Sentences / clauses | Language |
| --- | --- | --- | --- |
| `test_claude.csv` (v1) | Claude (Opus 5.5, the coordinator session), at the user's request on 2026-10-17 | 142 / 174 | English |
| `test_claude_v2.csv` (v2) | Claude (Opus 5.5, the coordinator session), 2026-10-17, after round 1 was scored on v1 | 126 / 146 | English |

- `test_claude.csv` was written by a different model family from the one that generated the
  training clauses (Qwen 2.5 7B), so its sentences do not share the generator's phrasing. It is
  still **not real student data** and must be reported as Claude-written, and listed in the
  report's AI-use appendix.
- The sentences are deliberately hard: slang ("arvo", "tute", "uni"), typos, several requests in
  one sentence, distracting numbers ("internship 3 days a week so only 2 days at uni"), negations
  ("long gaps don't bother me"), opposite requests ("prefer online", "gaps are good for the gym"),
  and reasons split from requests across a full stop.
- The answers follow the conventions in `README.md` in this folder. Rows whose reading is not
  obvious carry a note in the `note` column.
- No team member writes test data (decided 2026-10-17). Both test sets are frozen: never train or
  tune on them. The report must state that they are Claude-written.

## Why there is a second test set (v2)

Round 1 (TF-IDF+LR, 7B zero-shot, 7B QLoRA `uniplan-parse-7b`) was scored once on v1 on 2026-10-17.
Its errors were then read to design round 2 (more English hard-time training clauses, splitter
fixes, an optional rule guard). From that point v1 is no longer clean for round 2, so v1 numbers for
round-2 models are optimistic and must be labelled that way.

`test_claude_v2.csv` was written and frozen **before** any round-2 training data, splitter change or
model existed, by the coordinator, not by the parsing window that builds round 2 (which does not read
it). It follows the same conventions as v1 and roughly the same label mix as v1 (it was not tilted
towards the round-2 error types): blocked_time 56, other 20, prefer_no_early_late 14, max_days 10,
max_daily_hours 10, lunch 10, prefer_less_waiting 10, prefer_fewer_days 9, in_person_only 7.
Every clause was compared with v1 and the round-1 training clauses (character 3-gram cosine); the 14
closest were rewritten and the highest that remains is 0.73. Round 1 vs round 2 is compared on v2.

## Training data written by Claude

`train_claude.csv` (118 sentences, 141 clauses, round 1) holds hard boundary cases written by Claude
for training only: hedged clock times vs. blocked times, day counts vs. "fewer days", class hours
vs. hours on campus, wanting online or wanting gaps, and distracting numbers. It follows the same
conventions. Every sentence was checked against `test_claude.csv`; the three closest (similarity
of 0.7 or more) were rewritten. The highest that remains is 0.71, between sentences that ask for
different things.

## Decision rule for round 2 (written 2026-10-17 19:58, before the round-2 7B QLoRA was scored)

At this point, round 1 had been scored on v2 and the coordinator had read the round-1 7B errors
there, for diagnosis only. The round-2 7B (`uniplan-parse-7b-r2`) replaces round 1 as the
run-time parser only if all three hold:
1. On v2, it is at least as good as round 1 on clause accuracy and on sentences with every
   condition right.
2. No label that round 2 did not target (lunch, max_days, max_daily_hours, in_person_only,
   prefer_fewer_days, prefer_less_waiting, other) gets clearly worse on v2, meaning a drop of
   more than one clause. Gains on the targeted labels (blocked_time, prefer_no_early_late) must
   not come from calling hedged clock times blocked.
3. On the validation set, its best epoch is at least as good as round 1's.

Otherwise round 1 stays. v2 will not be used to design a round 3; a round 3 would need a new
test set (v3) written before it.
