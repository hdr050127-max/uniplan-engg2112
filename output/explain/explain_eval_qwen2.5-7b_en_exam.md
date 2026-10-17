# Reason fact-check evaluation (qwen2.5:7b)

Reasons, the model prompt and the checker are in English (docs/DESIGN.md); the checks are the same ones the Chinese version made. Sentences: `llm/parse/exam/exam.csv`, written by Claude (Opus 5.5), **not real student data**. Conditions are the file's hand-written answers (not `parse()` output); timetables come from the committed 2026 S2C snapshots. Model output was produced with temperature 0 and seed 0.

| | |
| --- | --- |
| Sentences | 304 |
| Planned (feasible) | 194; not planned: {'no_feasible': 110} |
| Recommended timetables | 571; with a time clash or a broken hard condition: 0 |
| Template reasons passing the checker | 571/571 (100%) |
| Pick 1: main reason = the model's biggest difference from pick 2, template | 185/192 (96%) |
| — the reason shown (model rewrite if it passed, else template) | 175/192 (91%) |
| Model sentences returned | 570 (requests by status: {'partial': 93, 'rejected': 81, 'model': 20}) |
| Model sentences that passed and were shown | 194/570 (34%) |
| — pick 1 | 37/194 (19%) |
| — pick 2 | 74/192 (39%) |
| — pick 3 | 83/184 (45%) |
| Seconds per request (median, max) | 0.8, 1.6 |

Rejected, by first failed check: comparison 212, number 71, direction 48, reference 28, topic 8, length 3, superlative 3, time 2, weekday 1

These sentences were never used to write or tune the checker: this pass rate is out-of-sample.

Passing means every claim the checker can read (weekdays, clock times, amounts with units, best-of-picks and comparison words, topics it has no facts for) matched the timetable. Claims it cannot read are not verified, so the passed sentences below should be spot-checked by a person.

## Passed model sentences (first 20)

| id | pick | model sentence | template it rewrote |
| --- | --- | --- | --- |
| e002 | 2 | Less waiting each week, but more days on campus compared to option 1. | Compared with option 1, it has 2 h 53 min less waiting a week, but it has 0.9 more days on campus a week. On campus Mon, Wed and Thu each week. No classes on Tue or Fri. |
| e002 | 3 | Less waiting overall, but more days on campus each week compared to option 1. | Compared with option 1, it has 3 h less waiting a week, but it has 1 more day on campus a week. On campus Mon, Tue and Wed each week. No classes on Fri. |
| e004 | 2 | 55 min more waiting a week compared to option 1. | A backup to option 1: it has 55 min more waiting a week. On campus Mon, Tue, Wed, Thu and Fri each week. |
| e005 | 2 | Less waiting, 1 h 55 min less on its longest day compared with option 1, and a 45 min lunch break between 12 pm and 2 pm every day. | Compared with option 1, it has 2 h 42 min less waiting a week and 1 h 55 min less on campus on its longest day, but it has 0.8 more days on campus a week. On campus Tue, Wed and Thu each week. No classes on Fri. A 45 min lunch break fits between 12 pm and 2 pm on every class day. |
| e008 | 3 | More days on campus each week compared to option 1. | Compared with option 1, it has 0.8 fewer building changes a week, but it has 0.9 more days on campus a week. On campus Mon, Tue, Wed, Thu and Fri each week. |
| e013 | 2 | More days on campus compared to Option 1, but less waiting and the same number of days as Option 1. | Compared with option 1, it has 2 h 42 min less waiting a week and 1 h 55 min less on campus on its longest day, but it has 0.8 more days on campus a week. On campus Tue, Wed and Thu each week. No classes on Fri. |
| e013 | 3 | Same number of days as Option 1 but more on its longest day. | A backup to option 1: it has 2 h 51 min more on campus on its longest day. On campus Tue and Wed each week. No classes on Thu or Fri. |
| e017 | 1 | Fewer days on campus and less waiting time compared to option 2. | First because, compared with option 2, it has 3 h 14 min less on campus on its longest day and 2 h 23 min less waiting a week. On campus Tue, Wed and Thu each week. No classes on Fri. |
| e018 | 3 | Less waiting and early or late class time compared to Option 1, but more days on campus. | Compared with option 1, it has 3 h less waiting a week, but it has 1 more day on campus a week. On campus Mon, Tue and Wed each week. No classes on Fri. |
| e019 | 1 | Less waiting and fewer early classes compared with option 2, but more building changes. | First because, compared with option 2, it has 2 h 18 min less waiting a week and 30 min less early class time a week, but it has 0.9 more building changes a week. On campus Mon, Tue and Wed each week. No classes on Fri. |
| e019 | 2 | Fewer building changes but more waiting compared with option 1. | Compared with option 1, it has 0.9 fewer building changes a week, but it has 2 h 18 min more waiting a week. On campus Mon, Tue and Wed each week. No classes on Fri. |
| e019 | 3 | Less waiting than option 1, but more days on campus and later finish time. | Compared with option 1, it has 25 min less waiting a week and 0.9 fewer building changes a week, but it has 0.8 more days on campus a week. On campus Mon, Tue, Wed and Thu each week. No classes on Fri. |
| e020 | 2 | 37 minutes more waiting a week compared to option 1. On campus Mon, Tue, Wed and Thu each week, no classes on Fri. | A backup to option 1: it has 37 min more waiting a week. On campus Mon, Tue, Wed and Thu each week. No classes on Fri. |
| e020 | 3 | 0.9 more days on campus a week compared to option 1. On campus Mon, Tue, Wed, Thu and Fri each week. | Compared with option 1, it has 0.8 fewer building changes a week, but it has 0.9 more days on campus a week. On campus Mon, Tue, Wed, Thu and Fri each week. |
| e022 | 2 | Less waiting time, but more days with just one class compared with option 1. | Compared with option 1, it has 3 h less waiting a week, but it has 2 more days a week with just one class. On campus Mon, Tue and Wed each week. No classes on Fri. |
| e022 | 3 | Less waiting time, but more days with just one class compared with option 1. | Compared with option 1, it has 3 h less waiting a week, but it has 2 more days a week with just one class. On campus Mon, Tue and Wed each week. No classes on Fri. |
| e025 | 2 | Less waiting and on campus time compared to Option 1, but more days on campus. | Compared with option 1, it has 2 h 42 min less waiting a week and 1 h 55 min less on campus on its longest day, but it has 0.8 more days on campus a week. On campus Tue, Wed and Thu each week. No classes on Fri. |
| e025 | 3 | Less waiting and on campus time compared to Option 1, but more days on campus. | Compared with option 1, it has 2 h 32 min less waiting a week and 55 min less on campus on its longest day, but it has 0.8 more days on campus a week. On campus Tue, Wed and Thu each week. No classes on Fri. |
| e028 | 3 | More days on campus compared to option 1, with similar waiting time. | A backup to option 1: it has 0.9 more days on campus a week. On campus Mon, Tue, Wed, Thu and Fri each week. |
| e031 | 2 | Fewer building changes but more waiting compared with option 1. | Compared with option 1, it has 0.9 fewer building changes a week, but it has 2 h 18 min more waiting a week. On campus Mon, Tue and Wed each week. No classes on Fri. |

## Rejected model sentences (first 30)

| id | pick | why | model sentence |
| --- | --- | --- | --- |
| e002 | 1 | number | Fewer days on campus and just one class day, but more waiting each week. |
| e003 | 1 | comparison | Fewer days on campus and less early class time, but more building changes a week. |
| e003 | 2 | comparison | Fewer building changes, but more waiting time a week. |
| e003 | 3 | comparison | Less waiting time, but more days on campus and later finish time. |
| e004 | 1 | number | Less waiting by 55 min a week compared to option 2. |
| e004 | 3 | reference | 0.5 fewer days with just one class, but 4 h 5 min more waiting a week. |
| e005 | 1 | comparison | Fewer days on campus, no classes on Thu or Fri, and a 45 min lunch break between 12 pm and 2 pm every day. |
| e005 | 3 | direction | More on campus on its longest day compared with option 1, but still fewer days on campus and a 45 min lunch break between 12 pm and 2 pm every day. |
| e008 | 1 | number | Less waiting by 37 minutes a week compared to option 2. |
| e008 | 2 | number | More waiting by 37 minutes a week compared to option 1. |
| e013 | 1 | direction | Fewer days on campus and less waiting compared to Option 2, but more on its longest day. |
| e016 | 1 | comparison | Fewer early or late classes and less waiting time compared to option 2. |
| e016 | 2 | number | Fewest days on campus and least early or late class time, but 37 minutes more waiting per week compared to option 1. |
| e017 | 2 | weekday | More on campus each day compared to option 1. |
| e017 | 3 | number | Less waiting time and one more day on campus compared to option 1, but more class time outside 9 am to 6 pm. |
| e018 | 1 | direction | Fewer days on campus and less waiting compared to Option 2, but more days on campus and more waiting. |
| e018 | 2 | comparison | Less waiting compared to Option 1, but more days on campus and more early or late class time. |
| e020 | 1 | number | Less waiting by 37 minutes a week compared to option 2. On campus Mon, Tue, Wed and Thu each week, no classes on Fri. |
| e021 | 1 | comparison | Fewer days on campus and no early or late classes, but more waiting. |
| e021 | 2 | comparison | Less waiting and no early or late classes, but more days on campus. |
| e021 | 3 | comparison | Fewer days on campus and less waiting, but more building changes and classes outside preferred hours. |
| e022 | 1 | comparison | Fewer days on campus, but more waiting time compared with option 2. |
| e023 | 1 | comparison | Fewest days on campus, least waiting, and least early class time compared to other options. 30 min lunch break fits well. |
| e023 | 2 | number | More days on campus, 2 h 18 min more waiting a week, and 30 min more early class time compared to option 1. |
| e023 | 3 | number | More days on campus, 1 h 2 min more on longest day, but least waiting overall. 30 min lunch break fits well. |
| e024 | 1 | reference | Fewer early or late classes, 4 h 14 min less waiting a week and 1 h less class outside 10 am to 6 pm a week. |
| e024 | 2 | reference | Fewer early or late classes, but 4 h 14 min more waiting a week. |
| e024 | 3 | reference | A backup: 32 min more waiting a week. |
| e025 | 1 | direction | Fewer days on campus and less waiting compared to Option 2, but more days on campus. |
| e026 | 1 | number | Starts 1.5 hours later than option 3, with fewer early classes. |
