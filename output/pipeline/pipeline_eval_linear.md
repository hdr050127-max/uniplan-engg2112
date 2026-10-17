# End-to-end pipeline evaluation (classifier: linear model from claude/cool-bun-40355d (529db12))

Sentences: `llm/parse/data/test_claude.csv`, written by Claude (Opus 5.5) — **not real student data**. Each sentence is planned twice on the same courses: with its hand-written conditions and with what `parse()` reads. Run on this Mac only.

- Clause classifier: linear model from claude/cool-bun-40355d (529db12)
- Ranker: rule: minus the sum of z-scores of the cared-about features (llm/rank/model.json is missing)
- Reasons: template (the page asks local Qwen afterwards; not timed here)

| | |
| --- | --- |
| Sentences | 142 |
| 1. Parsed conditions equal the hand-written ones | 88/142 (62%) |
| Plannable: hand-written / parsed / both / neither | 106 / 105 / 100 / 31 |
| 2. Planned from parsed conditions, some pick breaks a hand-written hard condition | 6/105 (6%) |
| — picks that break one | 17/311 (5%) |
| 3. Same first pick (both plannable) | 88/100 (88%); same set of picks 85/100 (85%) |
| 4. Seconds from sentence to recommendation (median, max) | 0.09, 0.30 |
| — of which parse() (median, max) | 0.000, 0.001 |

Fields that differ (sentences): unavailable_windows 26, cares 17, max_days_per_week 5, preferred_hours 5, lunch 4, max_daily_minutes 3, in_person_only 3

"Breaks a hard condition" is checked by `uniplan.advisor.hard_violations` (clashes, avoided times, daily class minutes, time on campus, lunch, days per week); "only in-person classes" is not re-checked.

## Sentences whose picks break a hand-written hard condition

| id | sentence | parsed vs hand-written | first problem |
| --- | --- | --- | --- |
| c011 | Keep my Mondays free if you can, I volunteer at the hospital | unavailable_windows | class in avoided time on 2026-08-03 |
| c043 | only want to come to uni twice a week | max_days_per_week | too many campus days in a week |
| c102 | I don't mind long days as long as it's only twice a week | max_days_per_week | too many campus days in a week |
| c118 | I'd like to be done by 3 so I can beat the traffic | unavailable_windows | class in avoided time on 2026-08-03 |
| c125 | I'm taking care of my newborn so I'd honestly like as few days as possible, maybe 2 | max_days_per_week, cares | too many campus days in a week |
| c127 | i dont mind gaps but i dont want to be there past 5 | unavailable_windows | class in avoided time on 2026-08-03 |

## Parsed conditions that differ (first 40)

| id | fields | sentence |
| --- | --- | --- |
| c003 | unavailable_windows | I drop my daughter at daycare at 8:30 every morning. Long gaps between classes would kill me tbh |
| c004 | cares | max 3 days on campus a week, ideally less |
| c007 | lunch | Could I get a proper lunch break? Like 45 mins |
| c010 | cares | I don't mind early starts but please no classes after 6pm, I have to catch the last bus to Wollongong |
| c011 | unavailable_windows | Keep my Mondays free if you can, I volunteer at the hospital |
| c019 | unavailable_windows | I can only come in Monday, Wednesday and Friday because of my job |
| c024 | max_days_per_week | I'm doing an internship 3 days a week so I can only do 2 days at uni |
| c025 | unavailable_windows | I have a standing appointment every thursday arvo |
| c026 | unavailable_windows | I play in a band and we rehearse monday nights from 7 |
| c027 | cares | evening lectures are the worst for me |
| c032 | preferred_hours | if at all possible I'd like to start no earlier than 9 |
| c038 | unavailable_windows | can we not have anything on fri afternoon? footy training |
| c042 | cares | I really dont want to waste time sitting around between classes, my commute is long enough already |
| c043 | max_days_per_week | only want to come to uni twice a week |
| c044 | unavailable_windows | Is it possible to have all my classes on Tuesday and Wednesday? |
| c049 | max_daily_minutes | pls no more than four and a half hours of class a day |
| c054 | cares | Could all my labs be in the same week pattern as Sarah's? we carpool |
| c056 | unavailable_windows | tuesday is my only day off work so I'd like all my classes that day if possible lol |
| c062 | unavailable_windows | Can't do mornings Mon to Wed, I'm doing early shifts at the hospital |
| c064 | unavailable_windows | i really need my wednesday afternoons free for my research assistant job and I'd like no gaps longer than an hour |
| c065 | in_person_only | pls dont put me in any online classes |
| c066 | unavailable_windows | Is there any way to have Fridays off? Three-day weekends would help my mental health a lot |
| c068 | lunch | lunch: any time between 11 and 2 is fine, just need 40 minutes |
| c071 | cares | Please keep it to 4 hours of classes max per day, I have ADHD and can't concentrate longer |
| c077 | unavailable_windows | I can only be on campus after 12 on Mondays because I have a morning job |
| c081 | unavailable_windows, preferred_hours, cares | I don't want to be on campus more than 3 days and I'd rather not have classes before 10 |
| c085 | unavailable_windows | Please put all my classes in the afternoon, I'm useless before noon |
| c086 | unavailable_windows | I'm fine with any day except Friday |
| c087 | max_daily_minutes | My visa only lets me work 24 hours a fortnight, I do those shifts Saturday and Sunday |
| c092 | unavailable_windows, max_daily_minutes, cares | I need gaps to be under 2 hours, and nothing on wednesday arvo |
| c095 | cares | I want to keep lunch free from 12:30 to 1:30 for my prayer and meal |
| c097 | unavailable_windows | I'm a single parent so classes need to be between 9:30 and 2:30 |
| c098 | cares | I hate having one lecture and then going home, it's a waste of a trip |
| c099 | preferred_hours | I'll be fasting for Ramadan so no late afternoon classes would be nice |
| c102 | max_days_per_week | I don't mind long days as long as it's only twice a week |
| c103 | in_person_only | no in person stuff please i'm immunocompromised |
| c105 | unavailable_windows | Need Wednesday morning free for my weekly therapy session at 10 |
| c107 | lunch | Gaps are ok if they're short, like under 30 min |
| c109 | unavailable_windows | After 3pm I'm free, before that I'm at my apprenticeship every Thursday |
| c110 | unavailable_windows, preferred_hours, cares | Would really appreciate a lunch break and no classes later than 6 |
