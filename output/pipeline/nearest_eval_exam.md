# Closest timetables when nothing fits

Sentences: `llm/parse/exam/exam.csv`, written by Claude (Opus 5.5), **not real student data**. Conditions are the file's hand-written answers; timetables come from the committed 2026 S2C snapshots. The fallback (`uniplan/nearest.py`, docs/DESIGN.md 10.1) was added after the final exam and only runs when the strict search finds nothing.

| | |
| --- | --- |
| Sentences | 304 |
| No timetable under the strict conditions | 110 |
| — now given the closest timetables | 110 / 110 (100%) |
| — of those, by watching one lecture as a recording | 0 |
| — still a dead end | 0 |
| Pick 1: limits broken (mean) | 1.18 |
| Pick 1: limits broken, how often | 1: 90, 2: 20 |
| Pick 1: amount broken, minutes a week (median, mean) | 111, 158 |
| Pick 1: which limits | unavailable_windows 103, max_days_per_week 15, max_daily_minutes 9, lunch 3 |
| Recommended timetables with a real clash | 0 / 293 |
| Template reasons passing the fact check | 293 / 293 (100%) |
| Seconds for the fallback plan (median, max) | 0.34, 1.38 |

Amounts are minutes a week: class time inside avoided times, class time over a daily limit, missed lunch breaks; one extra campus day counts as 180 min and one class with too few seats as 60 min (uniplan/nearest.py). Pick 1 is the closest: fewest limits broken, then the least amount, then the ranking model.

## Examples (first 12)

| id | units | pick 1 says |
| --- | --- | --- |
| e001 | ENGG2112 AMME2301 | Breaks 2 limits: 1 class on Mon after 4 pm; 1 class on Tue. Vs option 2: 4 h 46 min less on campus on its longest day and 3 h less waiting a week; costs 0.9 more days on campus a week. |
| e006 | ENGG2112 CIVL3206 | Breaks one limit: 1 class on Mon before 9 am. Vs option 2: 1 fewer day on campus a week and 2 fewer days a week with just one class; costs 4 h 46 min more on campus on its longest day. |
| e007 | AMME2301 CIVL3206 ENGG2112 | Breaks one limit: 4 days on campus a week, over the limit of 3. Vs option 2: 2 h 18 min less waiting a week and 30 min less early class time a week; costs 0.8 more building changes a week. |
| e009 | ENGG2112 AMME2301 | Breaks one limit: No 60 min lunch break on Wed. Vs option 2: 0.9 fewer days on campus a week and 1 fewer day a week with just one class; costs 4 h 46 min more on campus on its longest day. |
| e010 | ENGG2112 CIVL3206 | Breaks one limit: 2 classes on Mon before 9:30 am. Vs option 2: days that usually end at 5 pm (7 pm in option 2) and 1 h less class outside 9 am to 6 pm a week. |
| e011 | AMME2301 CIVL3206 ENGG2112 | Breaks 2 limits: 1 class on Mon after 5 pm; 1 class on 3 September. Vs option 2: 2 h 23 min less waiting a week and 30 min less early class time a week; costs 0.9 more building changes a week. |
| e012 | AMME2262 AMME2301 CIVL3206 ENGG2112 | Breaks one limit: Up to 6 h of class a day, over the 5 h limit. Vs option 2: 46 min less waiting a week. |
| e014 | ENGG2112 CIVL3206 | Breaks one limit: 2 classes on Mon before 9:45 am. Vs option 2: days that usually end at 5 pm (7 pm in option 2) and 1 h less class outside 9 am to 6 pm a week. |
| e015 | AMME2301 CIVL3206 ENGG2112 | Breaks 2 limits: 2 classes on Mon and Wed after 5 pm; 4 days on campus a week, over the limit of 3. |
| e027 | AMME2301 CIVL3206 ENGG2112 | Breaks one limit: 2 classes on Mon before 10 am. Vs option 2: 0.8 fewer days on campus a week and 1.6 fewer days a week with just one class; costs 39 min more waiting a week. |
| e036 | AMME2262 AMME2301 CIVL3206 ENGG2112 | Breaks one limit: 3 classes on Wed. Vs option 2: 3 h 30 min less waiting a week and 1 h 55 min less on campus on its longest day. |
| e040 | AMME2262 AMME2301 CIVL3206 ENGG2112 | Breaks 2 limits: 8 classes on Mon and Wed before 6 pm; 4 classes on Tue and Thu and 3 classes on 4 dates. Vs option 2: 0.2 fewer days on campus a week and 51 min less waiting a week. |
