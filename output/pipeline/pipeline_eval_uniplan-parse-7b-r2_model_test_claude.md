# End-to-end pipeline evaluation (classifier: ollama-short:uniplan-parse-7b-r2 via http://192.168.1.120:11434 (linear model, then keywords, if it fails))

Sentences: `llm/parse/data/test_claude.csv`, written by Claude (Opus 5.5) — **not real student data**. Each sentence is planned twice on the same courses: with its hand-written conditions and with what `parse()` reads. Run on this Mac only.

- Clause classifier: ollama-short:uniplan-parse-7b-r2 via http://192.168.1.120:11434 (linear model, then keywords, if it fails)
- Ranker: trained pairwise model (llm/rank/model.json)
- Reasons: template (the page asks local Qwen afterwards; not timed here)

| | |
| --- | --- |
| Sentences | 142 |
| 1. Parsed conditions equal the hand-written ones | 111/142 (78%) |
| Plannable: hand-written / parsed / both / neither | 106 / 104 / 101 / 33 |
| 2. Planned from parsed conditions, some pick breaks a hand-written hard condition | 4/104 (4%) |
| — picks that break one | 12/307 (4%) |
| 3. Same first pick (both plannable) | 98/101 (97%); same set of picks 92/101 (91%) |
| 4. Seconds from sentence to recommendation (median, max) | 0.55, 1.08 |
| Sentences parsed while the model runtime had fallen back | 0 |
| — of which parse() (median, max) | 0.330, 0.803 |

Fields that differ (sentences): unavailable_windows 16, cares 14, preferred_hours 7, lunch 3, max_daily_minutes 2, max_days_per_week 1

"Breaks a hard condition" is checked by `uniplan.advisor.hard_violations` (clashes, avoided times, daily class minutes, time on campus, lunch, days per week); "only in-person classes" is not re-checked.

## Sentences whose picks break a hand-written hard condition

| id | sentence | parsed vs hand-written | first problem |
| --- | --- | --- | --- |
| c044 | Is it possible to have all my classes on Tuesday and Wednesday? | unavailable_windows | class in avoided time on 2026-08-03 |
| c085 | Please put all my classes in the afternoon, I'm useless before noon | unavailable_windows, preferred_hours, cares | class in avoided time on 2026-08-04 |
| c124 | My bus only comes once an hour so long gaps don't bother me but please no classes before 9 | unavailable_windows, preferred_hours, cares | class in avoided time on 2026-08-06 |
| c127 | i dont mind gaps but i dont want to be there past 5 | unavailable_windows, preferred_hours, cares | class in avoided time on 2026-08-03 |

## Parsed conditions that differ (first 40)

| id | fields | sentence |
| --- | --- | --- |
| c004 | cares | max 3 days on campus a week, ideally less |
| c007 | lunch | Could I get a proper lunch break? Like 45 mins |
| c009 | unavailable_windows | wednesdays I have netball from 4 till 6, everything else is flexible |
| c019 | unavailable_windows | I can only come in Monday, Wednesday and Friday because of my job |
| c032 | preferred_hours | if at all possible I'd like to start no earlier than 9 |
| c044 | unavailable_windows | Is it possible to have all my classes on Tuesday and Wednesday? |
| c049 | max_daily_minutes | pls no more than four and a half hours of class a day |
| c059 | cares | long breaks between lectures are fine for me since I study in the library anyway |
| c062 | unavailable_windows | Can't do mornings Mon to Wed, I'm doing early shifts at the hospital |
| c064 | unavailable_windows | i really need my wednesday afternoons free for my research assistant job and I'd like no gaps longer than an hour |
| c066 | max_days_per_week | Is there any way to have Fridays off? Three-day weekends would help my mental health a lot |
| c068 | lunch | lunch: any time between 11 and 2 is fine, just need 40 minutes |
| c071 | cares | Please keep it to 4 hours of classes max per day, I have ADHD and can't concentrate longer |
| c084 | cares | I want to go to the gym between classes so a couple of small gaps is actually good |
| c085 | unavailable_windows, preferred_hours, cares | Please put all my classes in the afternoon, I'm useless before noon |
| c086 | unavailable_windows | I'm fine with any day except Friday |
| c087 | max_daily_minutes | My visa only lets me work 24 hours a fortnight, I do those shifts Saturday and Sunday |
| c088 | unavailable_windows | pls no tutes on monday morning, I have a standing doctor's appt at 9 |
| c097 | unavailable_windows | I'm a single parent so classes need to be between 9:30 and 2:30 |
| c098 | cares | I hate having one lecture and then going home, it's a waste of a trip |
| c105 | unavailable_windows | Need Wednesday morning free for my weekly therapy session at 10 |
| c108 | cares | Can I avoid Monday 9am lectures? It takes me ages to get in after the weekend |
| c110 | unavailable_windows, preferred_hours, cares | Would really appreciate a lunch break and no classes later than 6 |
| c112 | cares | i'd rather 5 short days than 3 super long ones |
| c119 | unavailable_windows, preferred_hours, cares | ugh no 9ams again pls, and keep thursday free for my part time job |
| c122 | unavailable_windows | I'm in the rowing squad, training is 5:30-7:30am every weekday |
| c124 | unavailable_windows, preferred_hours, cares | My bus only comes once an hour so long gaps don't bother me but please no classes before 9 |
| c127 | unavailable_windows, preferred_hours, cares | i dont mind gaps but i dont want to be there past 5 |
| c129 | cares | I need a 30 min lunch somewhere between 11:30 and 1:30, and I'd like to avoid back-to-back 3 hour labs |
| c132 | lunch, preferred_hours | I'm a morning person so early classes are perfect, I'd love to be done by lunch |
| c141 | unavailable_windows, cares | I want a couple of completely free weekdays |
