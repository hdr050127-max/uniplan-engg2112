# Who wrote this exam (2026-10-17)

Everything here is synthetic and AI-written; there are no real students.

- `personas.json` (x01–x20, English): written by a fresh Claude subagent that saw only the format
  READMEs and the code, and none of the existing personas, labels, answers or model outputs. It
  changed only the units of 8 personas so that every persona has timetables. `prepare` then made
  540 questions (8 candidates per persona; x09 has 6 and x19 has 7).
- `answers.jsonl`: four more fresh Claude subagents, each answering the questions of 5 personas
  (g1 x01–x05, g2 x06–x10, g3 x11–x15, g4 x16–x20), role-playing the student. They read only their
  own question file, ran no model, and saw neither the key nor any model output.
  Result: 红 240, 蓝 245, 差不多 55. The reasons are in `answers_with_reasons.jsonl`.
- `answers_second.jsonl`: two further subagents re-answered 6 randomly chosen personas (seed
  2112: x02, x04, x09, x10, x15, x16; 155 questions) independently, to measure how far two
  answerers agree. They are not used for scoring.

## Answerer agreement (second answer vs scoring answer)

| persona | same answer | same, where both picked a side |
| --- | ---: | ---: |
| x02 driver paying hourly parking (gap) | 15/28 | 13/22 |
| x04 no Fridays (days, then early/late) | 25/28 | 24/24 |
| x09 no arrival before 9:30 (late, then days) | 15/15 | 15/15 |
| x10 intern, "as bunched up as possible" | 12/28 | 12/27 |
| x15 not a morning person, short gaps | 25/28 | 25/25 |
| x16 placement Mon/Fri (days, then gap) | 25/28 | 23/23 |
| **all 155** | **117/155 (75%)** | **112/136 (82%)** |

The two low personas are genuinely ambiguous. For x10, one answerer read "bunched up" as fewest
days and the other as little waiting. For x02, the answerers disagreed on whether about an hour
less waiting is worth an extra drive in for one class. The other four personas agree on every pair
where both answerers picked a side. So about 82% is a realistic ceiling for any ranker on this exam.

Frozen before scoring:
- personas.json 684178d7…5f943
- questions.jsonl dd160599…b65cb8
- answers.jsonl e3767ed2…1388
- the scored model `llm/rank/model.json` c4d2a264…e42f
