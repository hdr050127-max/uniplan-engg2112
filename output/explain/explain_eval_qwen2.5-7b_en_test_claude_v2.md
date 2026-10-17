# Reason fact-check evaluation (qwen2.5:7b)

Reasons, the model prompt and the checker are in English (docs/DESIGN.md); the checks are the same ones the Chinese version made. Sentences: `llm/parse/data/test_claude_v2.csv`, written by Claude (Opus 5.5), **not real student data**. Conditions are the file's hand-written answers (not `parse()` output); timetables come from the committed 2026 S2C snapshots. Model output was produced with temperature 0 and seed 0.

| | |
| --- | --- |
| Sentences | 126 |
| Planned (feasible) | 87; not planned: {'no_feasible': 39} |
| Recommended timetables | 256; with a time clash or a broken hard condition: 0 |
| Template reasons passing the checker | 256/256 (100%) |
| Pick 1: main reason = the model's biggest difference from pick 2, template | 84/87 (97%) |
| — the reason shown (model rewrite if it passed, else template) | 80/87 (92%) |
| Model sentences returned | 255 (requests by status: {'rejected': 44, 'model': 7, 'partial': 36}) |
| Model sentences that passed and were shown | 73/255 (29%) |
| — pick 1 | 22/87 (25%) |
| — pick 2 | 24/87 (28%) |
| — pick 3 | 27/81 (33%) |
| Seconds per request (median, max) | 0.8, 1.8 |

Rejected, by first failed check: comparison 123, number 19, reference 19, direction 13, superlative 4, topic 2, length 1, time 1

These sentences were never used to write or tune the checker: this pass rate is out-of-sample.

Passing means every claim the checker can read (weekdays, clock times, amounts with units, best-of-picks and comparison words, topics it has no facts for) matched the timetable. Claims it cannot read are not verified, so the passed sentences below should be spot-checked by a person.

## Passed model sentences (first 20)

| id | pick | model sentence | template it rewrote |
| --- | --- | --- | --- |
| v003 | 1 | It has 1 h less class outside 10 am to 6 pm a week and 1 h less early class time compared with option 2. | First because, compared with option 2, it has 1 h less class outside 10 am to 6 pm a week and 1 h less early class time a week. On campus Mon, Tue and Wed each week. No classes on Fri. |
| v003 | 2 | It has 1 h more class outside 10 am to 6 pm a week compared with option 1. | A backup to option 1: it has 1 h more class outside 10 am to 6 pm a week. On campus Mon, Tue and Wed each week. No classes on Fri. |
| v003 | 3 | It has 1 h 30 min more class outside 10 am to 6 pm a week compared with option 1. | A backup to option 1: it has 1 h 30 min more class outside 10 am to 6 pm a week. On campus Mon, Tue and Wed each week. No classes on Fri. |
| v005 | 1 | Fewer days on campus compared to option 2, but more waiting. | First because, compared with option 2, it has 0.8 fewer days on campus a week and 1.6 fewer days a week with just one class, but it has 2 h 42 min more waiting a week. On campus Tue and Wed each week. No classes on Thu or Fri. |
| v005 | 3 | Same as option 1, but with more on campus on its longest day. | A backup to option 1: it has 2 h 51 min more on campus on its longest day. On campus Tue and Wed each week. No classes on Thu or Fri. |
| v006 | 2 | More days on campus but less waiting time compared to option 1. | Compared with option 1, it has 2 h 53 min less waiting a week, but it has 0.9 more days on campus a week. On campus Mon, Wed and Thu each week. No classes on Tue or Fri. |
| v007 | 1 | Less waiting and fewer early classes compared with Option 2, but more building changes. | First because, compared with option 2, it has 2 h 18 min less waiting a week and 30 min less early class time a week, but it has 0.9 more building changes a week. On campus Mon, Tue and Wed each week. No classes on Fri. |
| v007 | 3 | Less waiting compared with Option 1, but more days on campus and later classes. | Compared with option 1, it has 25 min less waiting a week and 0.9 fewer building changes a week, but it has 0.8 more days on campus a week. On campus Mon, Tue, Wed and Thu each week. No classes on Fri. |
| v012 | 3 | Same waiting, 5 days on campus, fits lunch break. | Compared with option 1, it has 0.9 fewer building changes a week, but it has 0.9 more days on campus a week. On campus Mon, Tue, Wed, Thu and Fri each week. A 60 min lunch break fits between 11:30 am and 2 pm on every class day. |
| v013 | 2 | It has 2 h 51 min more on campus on its longest day compared with option 1. | A backup to option 1: it has 2 h 51 min more on campus on its longest day. On campus Mon, Tue and Wed each week. No classes on Thu or Fri. |
| v014 | 2 | Less waiting compared to option 1, but more days on campus. Classes on Mon, Wed and Thu. | Compared with option 1, it has 2 h 53 min less waiting a week, but it has 0.9 more days on campus a week. On campus Mon, Wed and Thu each week. No classes on Tue or Fri. |
| v014 | 3 | Less waiting than option 1, but more days on campus. Classes on Mon, Tue and Wed. | Compared with option 1, it has 3 h less waiting a week, but it has 1 more day on campus a week. On campus Mon, Tue and Wed each week. No classes on Fri. |
| v015 | 3 | More waiting compared to option 1, but finishes earlier. | A backup to option 1: it has 2 h 18 min more waiting a week. On campus Mon, Tue and Wed each week. No classes on Fri. |
| v021 | 1 | Less waiting and fewer early classes compared to option 2, but with more building changes. | First because, compared with option 2, it has 2 h 14 min less waiting a week and 30 min less early class time a week, but it has 0.8 more building changes a week. On campus Tue and Wed each week. No classes on Thu or Fri. |
| v028 | 2 | More waiting each week compared to option 1. | A backup to option 1: it has 37 min more waiting a week. On campus Mon, Tue, Wed and Thu each week. No classes on Fri. |
| v029 | 3 | More on campus on its longest day compared to option 1. | A backup to option 1: it has 2 h 51 min more on campus on its longest day. On campus Tue and Wed each week. No classes on Thu or Fri. |
| v032 | 2 | More waiting compared to option 1, with the same number of class days. | A backup to option 1: it has 55 min more waiting a week. On campus Mon, Tue, Wed, Thu and Fri each week. A 30 min lunch break fits between 11:30 am and 2 pm on every class day. |
| v032 | 3 | Fewer class days but more waiting compared to option 1. | Compared with option 1, it has 0.5 fewer days a week with just one class, but it has 4 h 5 min more waiting a week. On campus Mon, Tue, Wed, Thu and Fri each week. A 30 min lunch break fits between 11:30 am and 2 pm on every class day. |
| v035 | 1 | Fewer waits and less time outside preferred hours compared to option 2. | First because, compared with option 2, it has 2 h 18 min less waiting a week and 30 min less class outside 9 am to 6 pm a week. On campus Mon, Tue and Wed each week. No classes on Fri. |
| v036 | 1 | Fewer late classes and less time outside 9 am to 6 pm compared with option 2. | First because, compared with option 2, it has 1 h less class outside 9 am to 6 pm a week and 1 h less late class time a week. On campus Mon, Tue, Wed and Thu each week. No classes on Fri. |

## Rejected model sentences (first 30)

| id | pick | why | model sentence |
| --- | --- | --- | --- |
| v001 | 1 | comparison | Fewer days on campus and just one class per week, but more waiting. |
| v001 | 2 | number | Less waiting and one less day on campus, but more days with classes. |
| v001 | 3 | comparison | Same days on campus as option 1, but longer days there. |
| v005 | 2 | superlative | Less on campus than option 1, with the fewest days overall, but more waiting. |
| v006 | 1 | comparison | Fewer days on campus and just one class per week, with less waiting time. |
| v006 | 3 | comparison | More days on campus but the least waiting time among the three. |
| v007 | 2 | direction | More building changes but less waiting compared with Option 1. |
| v008 | 1 | number | Less waiting by 37 minutes a week compared to option 2. |
| v008 | 2 | number | More days on campus by 1 day a week compared to option 1. |
| v008 | 3 | number | <i></i> 37 minutes more waiting a week compared to option 1.<i></i> On campus Mon, Tue, Wed and Thu each week, no classes on Fri. |
| v009 | 1 | comparison | Fewer days on campus and just one class per week, but more waiting. |
| v009 | 2 | comparison | Less waiting and shorter campus days, but more days on campus on the longest day. |
| v009 | 3 | comparison | Fewer days on campus, but longer days there. |
| v010 | 1 | comparison | Fewer days on campus and fewer days with just one class, but more waiting time. |
| v010 | 2 | comparison | Less waiting time, but more days on campus. |
| v010 | 3 | comparison | Less waiting time, but more days on campus and earlier classes. |
| v011 | 1 | comparison | Fewest days on campus, least waiting, and least early class time compared to other options. |
| v011 | 2 | comparison | More days on campus and longer days compared to option 1, but less waiting overall. |
| v011 | 3 | number | Longer days and one more day on campus compared to option 1, but less waiting. |
| v012 | 1 | comparison | Less waiting a week, 4 days on campus, fits lunch break. |
| v012 | 2 | comparison | More waiting a week, 4 days on campus, fits lunch break. |
| v013 | 1 | reference | It has 2 h 51 min less on campus on its longest day and 0.6 fewer days a week with just one class. |
| v013 | 3 | reference | It has 2 h 42 min less waiting a week and 1 h 55 min less on campus on its longest day, but 0.8 more days on campus a week. |
| v014 | 1 | direction | Fewer days on campus and less waiting compared to option 2, but with Josh on Mon and Wed. |
| v015 | 1 | comparison | Fewer days on campus and less waiting compared to option 2, but with later classes. |
| v015 | 2 | comparison | More days on campus and later classes compared to option 1, but with less waiting. |
| v017 | 1 | comparison | Fewer days on campus and just one class per week, but more waiting. |
| v017 | 2 | comparison | Less waiting and shorter campus days, but more days on campus on the longest day. |
| v017 | 3 | comparison | Fewer days on campus, but longer days there. |
| v018 | 1 | comparison | Fewer days on campus, but more waiting time. |
