# End-to-end pipeline evaluation (classifier: keyword rules (llm/parse/output/linear_model.json is missing, so parse() falls back))

Sentences: `llm/parse/data/test_claude.csv`, written by Claude (Opus 5.5) — **not real student data**. Each sentence is planned twice on the same courses: with its hand-written conditions and with what `parse()` reads. Run on this Mac only.

- Clause classifier: keyword rules (llm/parse/output/linear_model.json is missing, so parse() falls back)
- Ranker: rule: minus the sum of z-scores of the cared-about features (llm/rank/model.json is missing)
- Reasons: template (the page asks local Qwen afterwards; not timed here)

| | |
| --- | --- |
| Sentences | 142 |
| 1. Parsed conditions equal the hand-written ones | 82/142 (58%) |
| Plannable: hand-written / parsed / both / neither | 106 / 101 / 96 / 31 |
| 2. Planned from parsed conditions, some pick breaks a hand-written hard condition | 9/101 (9%) |
| — picks that break one | 21/299 (7%) |
| 3. Same first pick (both plannable) | 83/96 (86%); same set of picks 76/96 (79%) |
| 4. Seconds from sentence to recommendation (median, max) | 0.08, 0.29 |
| — of which parse() (median, max) | 0.000, 0.001 |

Fields that differ (sentences): unavailable_windows 27, cares 21, max_daily_minutes 6, max_days_per_week 6, lunch 5, preferred_hours 3, in_person_only 3

"Breaks a hard condition" is checked by `uniplan.advisor.hard_violations` (clashes, avoided times, daily class minutes, time on campus, lunch, days per week); "only in-person classes" is not re-checked.

## Sentences whose picks break a hand-written hard condition

| id | sentence | parsed vs hand-written | first problem |
| --- | --- | --- | --- |
| c011 | Keep my Mondays free if you can, I volunteer at the hospital | unavailable_windows | class in avoided time on 2026-08-03 |
| c043 | only want to come to uni twice a week | max_days_per_week | too many campus days in a week |
| c049 | pls no more than four and a half hours of class a day | max_daily_minutes | too many class minutes on 2026-10-13 |
| c095 | I want to keep lunch free from 12:30 to 1:30 for my prayer and meal | lunch | no lunch break on 2026-08-04 |
| c102 | I don't mind long days as long as it's only twice a week | max_days_per_week | too many campus days in a week |
| c105 | Need Wednesday morning free for my weekly therapy session at 10 | unavailable_windows | class in avoided time on 2026-08-05 |
| c118 | I'd like to be done by 3 so I can beat the traffic | unavailable_windows, preferred_hours, cares | class in avoided time on 2026-08-03 |
| c125 | I'm taking care of my newborn so I'd honestly like as few days as possible, maybe 2 | max_days_per_week, cares | too many campus days in a week |
| c133 | Thurs is out bc of my volunteering at the food bank, and I hate waiting around for hours | unavailable_windows, lunch | class in avoided time on 2026-08-13 |

## Parsed conditions that differ (first 40)

| id | fields | sentence |
| --- | --- | --- |
| c003 | unavailable_windows | I drop my daughter at daycare at 8:30 every morning. Long gaps between classes would kill me tbh |
| c005 | cares | I commute 90 mins each way from Campbelltown so the fewer days I have to come in the better |
| c007 | lunch | Could I get a proper lunch break? Like 45 mins |
| c010 | cares | I don't mind early starts but please no classes after 6pm, I have to catch the last bus to Wollongong |
| c011 | unavailable_windows | Keep my Mondays free if you can, I volunteer at the hospital |
| c019 | unavailable_windows | I can only come in Monday, Wednesday and Friday because of my job |
| c023 | max_daily_minutes | please don't give me 3 hour gaps again like last sem, back to back is fine |
| c024 | max_days_per_week | I'm doing an internship 3 days a week so I can only do 2 days at uni |
| c025 | unavailable_windows | I have a standing appointment every thursday arvo |
| c026 | unavailable_windows | I play in a band and we rehearse monday nights from 7 |
| c027 | cares | evening lectures are the worst for me |
| c032 | preferred_hours | if at all possible I'd like to start no earlier than 9 |
| c033 | max_days_per_week | i get really tired if i have more than 6 hrs of lectures and tuts in one day |
| c037 | cares | I don't care about gaps, I just want as few days in as possible |
| c038 | unavailable_windows | can we not have anything on fri afternoon? footy training |
| c043 | max_days_per_week | only want to come to uni twice a week |
| c044 | unavailable_windows | Is it possible to have all my classes on Tuesday and Wednesday? |
| c049 | max_daily_minutes | pls no more than four and a half hours of class a day |
| c052 | cares | Classes after 7pm are a no from me, I don't feel safe walking to Redfern station late |
| c056 | unavailable_windows | tuesday is my only day off work so I'd like all my classes that day if possible lol |
| c059 | cares | long breaks between lectures are fine for me since I study in the library anyway |
| c062 | cares | Can't do mornings Mon to Wed, I'm doing early shifts at the hospital |
| c064 | unavailable_windows | i really need my wednesday afternoons free for my research assistant job and I'd like no gaps longer than an hour |
| c066 | unavailable_windows | Is there any way to have Fridays off? Three-day weekends would help my mental health a lot |
| c067 | max_daily_minutes, cares | I have a 1 hour commute so I'd rather do long days than come in every day |
| c068 | lunch | lunch: any time between 11 and 2 is fine, just need 40 minutes |
| c077 | unavailable_windows | I can only be on campus after 12 on Mondays because I have a morning job |
| c085 | unavailable_windows | Please put all my classes in the afternoon, I'm useless before noon |
| c086 | unavailable_windows | I'm fine with any day except Friday |
| c087 | max_daily_minutes | My visa only lets me work 24 hours a fortnight, I do those shifts Saturday and Sunday |
| c092 | unavailable_windows, max_daily_minutes, cares | I need gaps to be under 2 hours, and nothing on wednesday arvo |
| c094 | unavailable_windows | Saturday classes would actually be great for me |
| c095 | lunch | I want to keep lunch free from 12:30 to 1:30 for my prayer and meal |
| c097 | unavailable_windows | I'm a single parent so classes need to be between 9:30 and 2:30 |
| c098 | cares | I hate having one lecture and then going home, it's a waste of a trip |
| c099 | unavailable_windows, cares | I'll be fasting for Ramadan so no late afternoon classes would be nice |
| c102 | max_days_per_week | I don't mind long days as long as it's only twice a week |
| c103 | in_person_only | no in person stuff please i'm immunocompromised |
| c104 | cares | I'd like at least 30 min between classes in different buildings because I use a wheelchair |
| c105 | unavailable_windows | Need Wednesday morning free for my weekly therapy session at 10 |
