# Reason fact-check evaluation (qwen2.5:7b)

Reasons, the model prompt and the checker are in English (docs/DESIGN.md); the checks are the same ones the Chinese version made. Sentences: `llm/parse/data/test_claude.csv`, written by Claude (Opus 5.5), **not real student data**. Conditions are the file's hand-written answers (not `parse()` output); timetables come from the committed 2026 S2C snapshots. Model output was produced with temperature 0 and seed 0. The model sentences come from an earlier run against http://192.168.1.120:11434 and were checked again with the current rules, without calling the model.

| | |
| --- | --- |
| Sentences | 142 |
| Planned (feasible) | 106; not planned: {'no_feasible': 36} |
| Recommended timetables | 314; with a time clash or a broken hard condition: 0 |
| Template reasons passing the checker | 314/314 (100%) |
| Pick 1: main reason = the model's biggest difference from pick 2, template | 102/106 (96%) |
| — the reason shown (model rewrite if it passed, else template) | 98/106 (92%) |
| Model sentences returned | 311 (requests by status: {'partial': 41, 'rejected': 58, 'model': 7}) |
| Model sentences that passed and were shown | 76/311 (24%) |
| — pick 1 | 18/105 (17%) |
| — pick 2 | 23/105 (22%) |
| — pick 3 | 35/101 (35%) |
| Seconds per request (median, max) | 0.8, 3.3 |

Rejected, by first failed check: comparison 149, number 38, reference 20, direction 15, superlative 5, topic 3, weekday 3, length 2

The checker's rules were refined after spot-checking earlier runs on these same sentences, so this pass rate is in-sample and likely optimistic for new sentences.

Passing means every claim the checker can read (weekdays, clock times, amounts with units, best-of-picks and comparison words, topics it has no facts for) matched the timetable. Claims it cannot read are not verified, so the passed sentences below should be spot-checked by a person.

## Passed model sentences (first 20)

| id | pick | model sentence | template it rewrote |
| --- | --- | --- | --- |
| c001 | 2 | Less on campus on its longest day, less waiting, but more days on campus compared to option 1. | Compared with option 1, it has 2 h 42 min less waiting a week and 1 h 55 min less on campus on its longest day, but it has 0.8 more days on campus a week. On campus Tue, Wed and Thu each week. No classes on Fri. |
| c007 | 1 | Fewest days on campus, least waiting, and least early class time; 45 min lunch break fits. | First because, compared with option 2, it has 2 h 18 min less waiting a week and 30 min less early class time a week, but it has 0.9 more building changes a week. On campus Mon, Tue and Wed each week. No classes on Fri. A 45 min lunch break fits between 11:30 am and 2 pm on every class day. |
| c008 | 3 | Same as option 1 but with slightly more waiting time. | A backup to option 1: it has 37 min more waiting a week. On campus Mon, Tue, Wed and Thu each week. No classes on Fri. |
| c015 | 1 | Less waiting and fewer early classes, but more building changes a week compared to option 2. | First because, compared with option 2, it has 2 h 18 min less waiting a week and 30 min less early class time a week, but it has 0.9 more building changes a week. On campus Mon, Tue and Wed each week. No classes on Fri. |
| c015 | 2 | Fewer building changes but more waiting compared to option 1. | Compared with option 1, it has 0.9 fewer building changes a week, but it has 2 h 18 min more waiting a week. On campus Mon, Tue and Wed each week. No classes on Fri. |
| c015 | 3 | Less waiting and fewer building changes compared to option 1, but more days on campus. | Compared with option 1, it has 25 min less waiting a week and 0.9 fewer building changes a week, but it has 0.8 more days on campus a week. On campus Mon, Tue, Wed and Thu each week. No classes on Fri. |
| c017 | 2 | Less waiting and on campus time, but more days on campus compared to option 1. | Compared with option 1, it has 2 h 42 min less waiting a week and 1 h 55 min less on campus on its longest day, but it has 0.8 more days on campus a week. On campus Tue, Wed and Thu each week. No classes on Fri. |
| c017 | 3 | Less waiting and on campus time, but more days on campus compared to option 1. | Compared with option 1, it has 2 h 32 min less waiting a week and 55 min less on campus on its longest day, but it has 0.8 more days on campus a week. On campus Tue, Wed and Thu each week. No classes on Fri. |
| c018 | 3 | Less waiting and early/late classes, but more days on campus compared to option 1. | Compared with option 1, it has 3 h less waiting a week, but it has 1 more day on campus a week. On campus Mon, Tue and Wed each week. No classes on Fri. |
| c020 | 3 | Same number of days as option 1, but with 37 min more waiting each week. | A backup to option 1: it has 37 min more waiting a week. On campus Mon, Tue, Wed and Thu each week. No classes on Fri. |
| c025 | 3 | More days on campus on its longest day compared to option 1. | A backup to option 1: it has 2 h 51 min more on campus on its longest day. On campus Tue and Wed each week. No classes on Thu or Fri. |
| c026 | 3 | Less waiting time and early/late class times, but more days on campus compared to option 1. | Compared with option 1, it has 3 h less waiting a week, but it has 1 more day on campus a week. On campus Mon, Tue and Wed each week. No classes on Fri. |
| c027 | 1 | Fewer waiting hours and less class time outside 9 am to 6 pm compared with option 2. | First because, compared with option 2, it has 2 h 18 min less waiting a week and 30 min less class outside 9 am to 6 pm a week. On campus Mon, Tue and Wed each week. No classes on Fri. |
| c027 | 2 | More days with just one class compared with option 1. | A backup to option 1: it has 2 h 18 min more waiting a week. On campus Mon, Tue and Wed each week. No classes on Fri. |
| c027 | 3 | <option 3 has 1.5 more days a week with just one class compared with option 1.> | A backup to option 1: it has 1.5 more days a week with just one class. On campus Mon, Tue, Wed and Thu each week. No classes on Fri. |
| c029 | 2 | Less waiting and fewer days on campus compared to option 1, but more on its longest day. | Compared with option 1, it has 2 h 42 min less waiting a week and 1 h 55 min less on campus on its longest day, but it has 0.8 more days on campus a week. On campus Tue, Wed and Thu each week. No classes on Fri. |
| c029 | 3 | <some days more on campus compared to option 1, but no classes on Thu or Fri. | A backup to option 1: it has 2 h 51 min more on campus on its longest day. On campus Tue and Wed each week. No classes on Thu or Fri. |
| c031 | 3 | Busiest day has less class time, fewer building changes, but more days on campus compared to option 1. | Compared with option 1, it has 46 min less of class on its busiest day and 0.8 fewer building changes a week, but it has 0.8 more days on campus a week. On campus Mon, Tue, Wed and Thu each week. No classes on Fri. |
| c032 | 3 | Same fewest days on campus and least early or late class time, but 37 min more waiting compared to option 1. | A backup to option 1: it has 37 min more waiting a week. On campus Mon, Tue, Wed and Thu each week. No classes on Fri. |
| c035 | 1 | Fewest days on campus, least early or late class time compared with option 2, with a 30 min lunch break fitting daily. | First because, compared with option 2, it has 2 h 18 min less waiting a week and 30 min less early class time a week, but it has 0.9 more building changes a week. On campus Mon, Tue and Wed each week. No classes on Fri. A 30 min lunch break fits between 11:30 am and 2 pm on every class day. |

## Rejected model sentences (first 30)

| id | pick | why | model sentence |
| --- | --- | --- | --- |
| c001 | 1 | comparison | Fewer days on campus and just one class per week, but more waiting. |
| c001 | 3 | comparison | More days on campus on its longest day compared to option 1, but the same number of days on campus. |
| c002 | 1 | number | Fewer days on campus and just one class day, but more waiting. |
| c002 | 2 | number | Less waiting, but more days on campus and one more class day. |
| c002 | 3 | comparison | Less waiting overall, but more days on campus. |
| c005 | 1 | comparison | Fewer days on campus, no classes on Thu and Fri, but longer days. |
| c005 | 2 | comparison | More days on campus, no Fri classes, but shorter days. |
| c005 | 3 | comparison | More days on campus, longer days, and classes until 7 pm. |
| c006 | 1 | comparison | Fewer days on campus and just one class per week, but more waiting time. |
| c006 | 2 | comparison | Less waiting time, but more days on campus and one more class per week. |
| c006 | 3 | comparison | Less waiting time, but more days on campus each week. |
| c007 | 2 | comparison | More days on campus, more waiting, and more early class time; 45 min lunch break fits. |
| c007 | 3 | comparison | More days on campus, less waiting, but more class time; 45 min lunch break fits. |
| c008 | 1 | comparison | Fewer early or late classes and less waiting time compared with option 2. |
| c008 | 2 | comparison | Same as option 1 but with an extra day of classes, more waiting, and more class time outside 9 am to 6 pm. |
| c009 | 1 | comparison | Ends earlier on Wednesdays, with less waiting and no early classes. |
| c009 | 2 | comparison | Starts later on Wednesdays, ends later on Tuesdays, with more waiting and early classes. |
| c009 | 3 | comparison | Starts later on Wednesdays, ends earlier on Fridays, with more waiting and early classes. |
| c010 | 1 | comparison | Fewer days on campus and no classes on Tue and Fri, but more waiting each week. |
| c010 | 2 | comparison | Less waiting each week, but more days on campus and no classes on Fri. |
| c010 | 3 | comparison | Less waiting each week, but more days on campus and no classes on Fri. |
| c013 | 1 | comparison | Fewer days on campus and no classes on Thu or Fri, but more waiting each week. |
| c013 | 2 | comparison | Less waiting and no early classes, but more days on campus and classes end later. |
| c013 | 3 | comparison | Less waiting and fewer days on campus, but more days on campus and classes end later. |
| c014 | 1 | direction | Fewer days on campus and less waiting compared to option 2, but more days on campus and more waiting compared to option 1. |
| c014 | 2 | direction | Less waiting compared to option 1, but more days on campus and more waiting compared to option 2. |
| c014 | 3 | number | Less waiting compared to option 1 and 2, but more days on campus compared to option 1. |
| c017 | 1 | comparison | Fewer days on campus and no early or late classes, but more waiting each week. |
| c018 | 1 | comparison | Fewer days on campus and fewer early or late classes, but more waiting each week. |
| c018 | 2 | comparison | Less waiting each week, but more days on campus and more early or late classes. |
