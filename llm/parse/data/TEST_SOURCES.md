# Where the parsing test sets come from

| File | Written by | Sentences / clauses | Language |
| --- | --- | --- | --- |
| `test_claude.csv` | Claude (Opus 5.5, the coordinator session), at the user's request on 2026-10-17 | 142 / 174 | English |
| `test_team.csv` | Team members, by hand (to be added) | target 30+ | any |

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
- Both files are frozen test sets: never train or tune on them. Report each file separately and
  combined. If the scores on the two differ a lot, say so in the report.
