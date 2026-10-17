# Clarifying questions, browser walkthrough, 2026-10-17

Clicked through in the preview browser at 1280×900 (one check at 375×812), after merging `7cc770b`
(`llm/parse/clarify.py`). Courses ENGG2112 + AMME2301, 2026 S2C. Parsing ran the real runtime
(`ollama-short:uniplan-parse-7b-r2` on the Windows GPU), ranking the trained model. The sentences were
written by Claude for this walkthrough (not from `test_claude.csv` or `test_claude_v2.csv`, and not from
real students). For each question a non-default answer was clicked, the conditions and the picks were
checked, then the default answer was clicked again and the first result came back exactly.

| Sentence | Question kind | Default answer | Non-default answer | Back to default |
| --- | --- | --- | --- | --- |
| A "I'd rather not have anything after 5 since my bus home leaves at 5:30" | `hard_or_soft` | 一定不能: weekdays after 17:00 blocked, no timetable fits | 最好不要: re-parsed as a preference, block gone, preferred hours 9:00–17:00, 3 picks | block back, no timetable fits |
| B "it'd be ideal to finish by 3:30 because I collect my daughter from school" | `low_confidence` (the two models disagree) | weekdays after 15:30 blocked, no timetable fits | 和排课无关: re-parsed as `other`, block gone, 3 picks | block back, no timetable fits |
| C "not too many days a week, and I hate waiting around between classes" | `low_confidence` + both offers (days cap, lunch) | 3 picks on days 23 / 234 / 235 | 最多 2 天 + lunch 11:30–14:00: 2 picks, both days 23, reasons mention lunch; 每周最多来几天 + 最多 3 天: same 3 timetables, gap-first order | same 3 picks in the same order |
| D "I need to keep my campus days to a minimum, there's a hard limit" | `missing_value` | no cap, 3 picks (23 / 234 / 23) | 最多 2 天 (no re-parse): 2 picks, both days 23; 不限天数，少去几天就行 (re-parse): new first pick | same 3 picks in the same order |

| Screenshot | What it shows |
| --- | --- |
| `A1_hard_or_soft_asked.jpg` | A: the question and its two answers |
| `A2_hard_no_feasible.jpg` | A, default: no timetable fits |
| `A3_soft_chosen.jpg`, `A4_soft_picks.jpg` | A, 最好不要: condition updated, 3 picks |
| `B1_low_confidence_asked.jpg` | B: "是指？" with the two readings |
| `B2_not_scheduling_chosen.jpg`, `B3_not_scheduling_picks.jpg` | B, 和排课无关: clause shown as "这句我们管不了", 3 picks |
| `B4_default_restored_no_feasible.jpg` | B, back to default: "避开 周一至周五 15:30 后", no timetable fits |
| `C1_three_questions_asked.jpg` | C: one disagreement question and two offers (3 = the limit) |
| `C2_offers_accepted.jpg`, `C3_offers_picks.jpg` | C, 最多 2 天 + lunch: filled into 更多设置 (marked as from the sentence), 2 picks |
| `C4_reparse_keeps_offer_answers.jpg` | C, answers kept across a re-parse (below) |
| `C5_mobile_summary_fixed.jpg` | C at 375 px: no sideways scrolling; "我理解为" shown once |
| `D1_missing_value_asked.jpg` | D: "每周最多来几天？" |
| `D2_two_days_chosen.jpg`, `D3_two_days_picks.jpg` | D, 最多 2 天: filled in without re-parsing, 2 picks |
| `D4_no_cap_reparse_no_reask.jpg` | D, 不限天数: re-parsed, offer not asked again (below) |

## Answered offers are not asked again after a re-parse

`parse()` does not know which offers the student already answered, so the page keeps the questions from
the first parse and ignores the ones a re-parse returns. Checked twice by watching `/api/parse`:

- C: answered 最多 3 天 and lunch, then changed the first question to 每周最多来几天. The re-parse
  (`overrides {"0": "max_days"}`) returned the lunch offer again; the page still showed the original three
  questions once each, with 3 days and lunch still selected and still filled in.
- D: chose 不限天数，少去几天就行. The re-parse (`overrides {"0": "prefer_fewer_days"}`) returned a new
  offer "要不要定一个每周最多来几天？", which the student had just answered; the page did not show it.

The other side of this: an offer that appears only after a re-parse (say a clause changed to "less
waiting" would now earn the lunch offer) is not shown either. The student can still set it in 更多设置.

## Found and fixed

- The summary from `clarify.py` starts with "我理解为：", under a heading that already says "我理解为".
  The page now drops the prefix when it shows the summary.

No console errors from these runs, and no request failed. With a 2-day cap only 2 picks are shown: the
other candidates were near-copies of those two, which the page does not show as separate picks.
