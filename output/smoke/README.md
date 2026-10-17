# Web smoke test, 2026-10-17

Clicked through in the preview browser at 1280×900. Sentences were made up for this test (not from
`test_claude.csv`). "Online" is the normal server (Ollama on the Windows GPU); "offline" is a second
server started with `UNIPLAN_OLLAMA_URL=http://192.0.2.1:11434` in its own environment only.
Parsing ran the linear model, ranking the trained model (`llm/rank/model.json`).

| Screenshot | What it shows |
| --- | --- |
| `01_zh_understood.jpg` | 「我周二和周四晚上在餐厅打工，每天最多上5小时课，最好别太早，还有我想和室友上同一个tutorial」: 5 hours a day and fewer early/late classes understood; the work shift and the roommate clause shown as "这句我们管不了" |
| `02_zh_corrected.jpg` | Confirmation step used to fix it: Tue and Thu 18:00–23:30 added by hand, 5 hours changed to 6 |
| `03_zh_picks_online.jpg` | 3 picks and reasons (online, Qwen 7B rewrite) |
| `04_en_understood.jpg` | "I can't do Wednesdays because of my internship, at most 3 days on campus please, and I need a proper lunch break. Also my favourite lecturer is Dr Smith": Wednesday, 3 days and lunch understood; Dr Smith shown as "这句我们管不了"; lunch then changed from 30 to 45 minutes |
| `05_en_no_feasible.jpg` | No timetable fits; the page offers two single changes |
| `06_en_picks_online.jpg` | After "AMME2301 Lecture2 不去": 3 picks, reasons mention the 2 exams on Wednesday |
| `07_offline_en_understood.jpg` | Offline: parsing unaffected (it does not use Ollama) |
| `08_offline_picks_simplified.jpg` | Offline: picks as usual; reasons by this Mac's Qwen 3B, footnote in orange: "大模型服务器暂时不在线（简化模式）…" |

## Time from clicking 生成课表 (or a suggested fix) to the picks on screen

| | Picks shown | Qwen reasons arrive (in place, afterwards) |
| --- | --- | --- |
| Online, Chinese, 2 courses | 0.19 s | 4.8 s (7B on Windows) |
| Online, English after the fix | 0.19 s | 2.2 s (7B on Windows) |
| Offline, Chinese | 0.19 s | 10.1 s (about 3 s to give up on Windows, then 3B on this Mac) |
| Offline, English after the fix | 0.21 s | 6.6 s (3B on this Mac) |

No console errors in either tab. The offline server logs
`[llm.ollama] http://192.0.2.1:11434 is not answering; using this machine instead`.

## Found and fixed

- The fallback footnote was light grey at the bottom of the list; in simplified mode it is now orange.
- A value from the sentence that is not a preset (e.g. "5 时") was appended after "8 时"; it now sits in order.
- "Other" clauses now read "这句我们管不了，排课时不会考虑".
- The page now says "简化模式" when parsing falls back (a model runtime that does not answer) or the reasons do
  (model server not answering, or no model). Parsing currently runs the linear model, which never calls
  Ollama, so that case is covered by a unit test rather than this click-through.

## For the parsing window

「我周二和周四晚上在餐厅打工」 was labelled `other`, so the Tuesday/Thursday evening shift was lost until the
student added it by hand on the confirmation step.
