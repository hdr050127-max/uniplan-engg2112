# End-to-end pipeline evaluation (classifier: ollama-short:uniplan-parse-7b-r2 via http://192.168.1.120:11434 (linear model, then keywords, if it fails))

Sentences: `llm/parse/data/test_claude_v2.csv`, written by Claude (Opus 5.5) — **not real student data**. Each sentence is planned twice on the same courses: with its hand-written conditions and with what `parse()` reads. Run on this Mac only.

- Clause classifier: ollama-short:uniplan-parse-7b-r2 via http://192.168.1.120:11434 (linear model, then keywords, if it fails)
- Ranker: trained pairwise model (llm/rank/model.json)
- Reasons: template (the page asks local Qwen afterwards; not timed here)

| | |
| --- | --- |
| Sentences | 126 |
| 1. Parsed conditions equal the hand-written ones | 101/126 (80%) |
| Plannable: hand-written / parsed / both / neither | 87 / 84 / 83 / 38 |
| 2. Planned from parsed conditions, some pick breaks a hand-written hard condition | 2/84 (2%) |
| — picks that break one | 6/248 (2%) |
| 3. Same first pick (both plannable) | 81/83 (98%); same set of picks 76/83 (92%) |
| 4. Seconds from sentence to recommendation (median, max) | 0.51, 1.08 |
| Sentences parsed while the model runtime had fallen back | 0 |
| — of which parse() (median, max) | 0.333, 1.070 |

Fields that differ (sentences): cares 12, unavailable_windows 11, preferred_hours 2, max_daily_minutes 2, lunch 2, max_days_per_week 1, max_daily_span 1

"Breaks a hard condition" is checked by `uniplan.advisor.hard_violations` (clashes, avoided times, daily class minutes, time on campus, lunch, days per week); "only in-person classes" is not re-checked.

## Sentences whose picks break a hand-written hard condition

| id | sentence | parsed vs hand-written | first problem |
| --- | --- | --- | --- |
| v053 | I need to be off campus by 3:15 on Mondays for school pick-up | unavailable_windows | class in avoided time on 2026-08-03 |
| v094 | I can come in any day but only for a maximum of 5 hours | max_daily_minutes, max_daily_span | too long on campus on 2026-08-03 |

## Parsed conditions that differ (first 40)

| id | fields | sentence |
| --- | --- | --- |
| v011 | cares | I don't want to be at uni for more than 9 hours on any day, it's too draining |
| v022 | cares | I'm an early riser so 8am starts suit me fine |
| v024 | unavailable_windows | my kids are in school 9 to 3 so that's my window for classes |
| v025 | unavailable_windows, preferred_hours, cares | my sweet spot would be 11 till 5, if possible |
| v039 | cares | I really want everything crammed into as few days as possible, three at most |
| v042 | cares | rather have more days with shorter hours |
| v045 | unavailable_windows | I'm free all week except Thursday evenings, when I have Bible study |
| v053 | unavailable_windows | I need to be off campus by 3:15 on Mondays for school pick-up |
| v063 | unavailable_windows | I'm a night owl, mornings are a write-off |
| v070 | max_days_per_week, cares | four campus days or fewer, if you can |
| v073 | unavailable_windows | can you keep my classes from 12 to 6, I do deliveries in the morning |
| v080 | cares | Shorter days please, max 6 hours of class |
| v084 | cares | I'd like big gaps so I can work at the library cafe between classes |
| v085 | unavailable_windows, preferred_hours, cares | Ideally my day would run 10:30 to 4:30 |
| v090 | cares | pls bunch my classes together, I hate dead time |
| v094 | max_daily_minutes, max_daily_span | I can come in any day but only for a maximum of 5 hours |
| v097 | cares | I'm in a wheelchair and the lifts in Carslaw are slow, so 10 min between classes isn't enough |
| v100 | unavailable_windows | Monday and Wednesday are gym days, but I can come in after 1 |
| v101 | lunch | Fridays are off limits, cap my classes at 4 hours a day, and give me an hour to eat |
| v102 | cares | Early starts don't worry me, but I need to be gone by 3 on Tuesdays and Thursdays for my kids |
| v113 | unavailable_windows | I work weekends and Wednesday nights, and I'd prefer no long gaps |
| v115 | lunch | I cannot do anything between 12 and 2 on weekdays, I'm a lunchtime lifeguard |
| v116 | max_daily_minutes | I'd like 4 hours of class a day max but if it's 5 that's ok |
| v118 | unavailable_windows | classes in the afternoon only please, I work mornings at a cafe |
| v119 | unavailable_windows | I can stay late on Mondays but other days I have to be gone by 4 |
