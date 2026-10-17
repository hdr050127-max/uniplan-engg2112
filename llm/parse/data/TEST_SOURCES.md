# Where the parsing test sets come from

| File | Written by | Sentences / clauses | Language |
| --- | --- | --- | --- |
| `test_claude.csv` | Claude (Opus 5.5, the coordinator session), at the user's request on 2026-10-17 | 142 / 174 | English |

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
- No team member writes test data (decided 2026-10-17), so this is the only parsing test set.
  It is frozen: never train or tune on it. The report must state that it is Claude-written.

## Training data written by Claude

`train_claude.csv` (118 sentences, 141 clauses, round 1) holds hard boundary cases written by Claude
for training only: hedged clock times vs. blocked times, day counts vs. "fewer days", class hours
vs. hours on campus, wanting online or wanting gaps, and distracting numbers. It follows the same
conventions. Every sentence was checked against `test_claude.csv`; the three closest (similarity
of 0.7 or more) were rewritten. The highest that remains is 0.71, between sentences that ask for
different things.
