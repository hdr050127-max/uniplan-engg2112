# End-to-end pipeline evaluation (classifier: ollama-short:uniplan-parse-7b-r2 via http://192.168.1.120:11434 (linear model, then keywords, if it fails))

Sentences: `llm/parse/exam/exam.csv`, written by Claude (Opus 5.5) — **not real student data**. Each sentence is planned twice on the same courses: with its hand-written conditions and with what `parse()` reads. Run on this Mac only.

- Clause classifier: ollama-short:uniplan-parse-7b-r2 via http://192.168.1.120:11434 (linear model, then keywords, if it fails)
- Ranker: trained pairwise model (llm/rank/model.json)
- Reasons: template (the page asks local Qwen afterwards; not timed here)

| | |
| --- | --- |
| Sentences | 304 |
| 1. Parsed conditions equal the hand-written ones | 237/304 (78%) |
| Plannable: hand-written / parsed / both / neither | 194 / 196 / 188 / 102 |
| 2. Planned from parsed conditions, some pick breaks a hand-written hard condition | 16/196 (8%) |
| — picks that break one | 40/579 (7%) |
| 3. Same first pick (both plannable) | 174/188 (93%); same set of picks 164/188 (87%) |
| 4. Seconds from sentence to recommendation (median, max) | 0.58, 1.42 |
| Sentences parsed while the model runtime had fallen back | 0 |
| — of which parse() (median, max) | 0.392, 1.212 |

Fields that differ (sentences): unavailable_windows 33, cares 27, lunch 8, preferred_hours 6, max_daily_minutes 4, max_days_per_week 4, max_daily_span 3, in_person_only 1

"Breaks a hard condition" is checked by `uniplan.advisor.hard_violations` (clashes, avoided times, daily class minutes, time on campus, lunch, days per week); "only in-person classes" is not re-checked.

## Sentences whose picks break a hand-written hard condition

| id | sentence | parsed vs hand-written | first problem |
| --- | --- | --- | --- |
| e023 | first class to last class shouldn't be longer than 8 hrs, and I need a 30 min feed somewhere in the middle | max_daily_minutes, max_daily_span | too long on campus on 2026-08-03 |
| e029 | Don't mind gaps, do mind 8am classes | unavailable_windows, cares | class in avoided time on 2026-08-04 |
| e091 | I'd prefer to finish by 5 on Wednesdays | unavailable_windows, preferred_hours, cares | class in avoided time on 2026-08-12 |
| e093 | no gaps no mornings no online | unavailable_windows, in_person_only | class in avoided time on 2026-08-05 |
| e099 | Ideally nothing before 9 on any day and Wednesdays off for my placement | unavailable_windows, preferred_hours, cares | class in avoided time on 2026-08-05 |
| e105 | I like having my classes in the morning so the arvo's free for work | unavailable_windows, cares | class in avoided time on 2026-08-03 |
| e121 | no 9ams please, and I'd like to be finished by 4 if possible | unavailable_windows | class in avoided time on 2026-08-05 |
| e151 | No classes before 10 except Wednesday when I can do 9 | unavailable_windows | class in avoided time on 2026-08-03 |
| e159 | Not a fan of gaps, not a fan of 8ams either | unavailable_windows, preferred_hours, cares | class in avoided time on 2026-09-14 |
| e164 | I'm doing a 20 hour a week internship so I need classes capped at 4 hours a day | max_daily_minutes | too many class minutes on 2026-08-04 |
| e187 | I don't care about days, I care about not being on campus for 10 hour days, 7 max | max_daily_span | too long on campus on 2026-08-03 |
| e190 | I volunteer with the Rural Fire Service every second Tuesday and every Thursday night | unavailable_windows | class in avoided time on 2026-08-04 |
| e199 | only tues and thurs work for me | unavailable_windows | class in avoided time on 2026-08-03 |
| e229 | Class hours per day: 4 max. Days per week: 3 max. Lunch: yes pls. | max_daily_minutes | too many class minutes on 2026-10-13 |
| e248 | I hate 8ams with a passion | unavailable_windows, preferred_hours, cares | class in avoided time on 2026-08-06 |
| e278 | no classes before 10 no classes after 4 no classes on friday | unavailable_windows | class in avoided time on 2026-08-03 |

## Parsed conditions that differ (first 40)

| id | fields | sentence |
| --- | --- | --- |
| e003 | cares | I don't mind early starts, 8am is totally fine |
| e005 | lunch | Need a proper lunch break, at least 45 min, sometime between 12 and 2 |
| e010 | lunch | Honestly I don't care about the days, just don't put me in anything that starts before 9:30 and give me an hour for lunch |
| e015 | unavailable_windows | ok so basically i work at a cafe on tuesday and thursday mornings until 11 and i also have a toddler so i need to be home by 5 and i dont want more than 3 days |
| e023 | max_daily_minutes, max_daily_span | first class to last class shouldn't be longer than 8 hrs, and I need a 30 min feed somewhere in the middle |
| e029 | unavailable_windows, cares | Don't mind gaps, do mind 8am classes |
| e033 | cares | I hate having one tiny class on a day by itself, I'd rather the days were full |
| e047 | lunch | my anxiety is worse on long days so cap it at 6 hours on campus and give me a lunch break |
| e050 | cares | no long waits between classes and I'd like an hour for lunch |
| e056 | cares | I don't want long gaps between classes, I'd rather just go home |
| e057 | unavailable_windows | I cant be there tuesday at all and thursday i have to leave by 1 |
| e070 | unavailable_windows | My dog walking business runs 7 to 9am weekdays, and I'd like an hour for lunch, fewer days is better too |
| e072 | cares | I want classes in the morning because I'm sharpest then |
| e081 | cares | 4 days max, 3 if you can manage it |
| e091 | unavailable_windows, preferred_hours, cares | I'd prefer to finish by 5 on Wednesdays |
| e093 | unavailable_windows, in_person_only | no gaps no mornings no online |
| e099 | unavailable_windows, preferred_hours, cares | Ideally nothing before 9 on any day and Wednesdays off for my placement |
| e104 | lunch | I need a meal break somewhere in the day, I'm on a 4 hour feeding schedule for my health |
| e105 | unavailable_windows, cares | I like having my classes in the morning so the arvo's free for work |
| e109 | cares | I'm happy to start early but I want to finish by 2 |
| e113 | cares | i'm an early bird so mornings are actually great for me |
| e114 | unavailable_windows | Assignments are due Fridays so I'd like Thursday free to finish them |
| e117 | max_days_per_week | I need at least one weekday totally off, so 4 days max |
| e119 | unavailable_windows | I'm a single dad, school drop off is 8:30 and pick up is 3 |
| e120 | cares | Can I have at most 5 hrs of class per day and get home before dark |
| e121 | unavailable_windows | no 9ams please, and I'd like to be finished by 4 if possible |
| e122 | unavailable_windows, cares | During Ramadan I'd rather avoid evening classes |
| e125 | cares | mornings and arvos r fine, just not fridays |
| e135 | cares | Compact week, decent lunch break, no Friday |
| e140 | unavailable_windows, lunch | Every Wednesday lunchtime I run a prayer group from 12 to 1 |
| e151 | unavailable_windows | No classes before 10 except Wednesday when I can do 9 |
| e153 | cares | a 1 hour break is fine but anything over 2 is too much |
| e155 | cares | Short days please, like 5 hours on campus max, and back to back where possible |
| e156 | unavailable_windows | Only free on Mon, Tue and Fri this sem, and I'd like it in person |
| e159 | unavailable_windows, preferred_hours, cares | Not a fan of gaps, not a fan of 8ams either |
| e164 | max_daily_minutes | I'm doing a 20 hour a week internship so I need classes capped at 4 hours a day |
| e179 | preferred_hours | I'd prefer to start no earlier than 9 and finish by 5 |
| e181 | cares | keep my days short pls, like 4 hours of class max |
| e186 | unavailable_windows | I work full time 9 to 5 Monday to Thursday, so classes outside those hours or on Friday |
| e187 | max_daily_span | I don't care about days, I care about not being on campus for 10 hour days, 7 max |
