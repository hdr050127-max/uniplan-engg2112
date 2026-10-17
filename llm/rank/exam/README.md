# 打分排序的期末考卷

这个文件夹放期末考卷。考卷由一个**新的子代理**出，只考一次。所有内容都是 AI 撰写的合成数据，不是真实学生。

## 流程

1. **出题者写画像**：`personas.json`，格式见下。
2. **生成题目**：`python3 -m llm.rank.exam prepare`
   - 程序给每个画像排出 8 份不同的课表，两两组成二选一题（每人 28 题）。
   - 输出 `questions.jsonl`，交给出题者作答。
   - 同时输出 `key.json`（哪份显示为红）和 `candidates.json`（课表和特征），出题者不需要看这两个文件。
3. **出题者作答**：`answers.jsonl`，每行一题：`{"pair_id": "x0001", "choice": "红"}`。
   - `choice` 只能是 `红`、`蓝` 或 `差不多`。
   - 每道题都要答。
4. **打分**：`python3 -m llm.gpu_lock -- python3 -m llm.rank.exam score --llm qwen2.5:14b`
   - 结果写到 `llm/rank/output/exam_report.json` 和 `exam_report.md`。
   - 打分只允许一次，再跑会被拒绝。
   - 不重训，也不调参。

## personas.json 的格式

```json
{"personas": [
  {"id": "x01",
   "text": "一句话说出学生的处境和在意的事",
   "units": ["ENGG2112", "AMME2301"],
   "conditions": {"unavailable_windows": [{"weekday": 5, "start_min": 0, "end_min": 1440}],
                  "preferred_hours": {"weekday": 0, "start_min": 600, "end_min": 1080},
                  "cares": ["gap", "campus_days"]}}
]}
```

**可选的课程**：ENGG2112、AMME2301、AMME2262、CIVL3206、AMME1362、MTRX1705、MTRX3700，每人 2–3 门。有些组合排不出课表（比如 ENGG2112 + MTRX1705），程序会跳过并报告原因。

**`conditions`** 用 `llm/contracts.py` 的 Conditions 格式，按需求解析的口径从句子里读出：
- `unavailable_windows`：说了具体时间或星期几、而且来不了（要上班、要接孩子、"最好周五不来"）。
- `max_days_per_week`、`max_daily_minutes`、`max_daily_span`、`lunch`、`in_person_only`：句子里给了明确的数字或要求。
- `preferred_hours`：有具体钟点的软偏好（"最好十点以后""四点前下课更好"）。没说的一端按 9:00 或 18:00 算。
- `cares`：在意哪些，按句子里说的重要性排序，第一个是最在意的。只能是：
  - `campus_days`：少来几天；
  - `gap`：少空等；
  - `outside_hours`：少早晚课。

## 作答的口径

把自己当成那位学生，看题目里的数字表和每周固定的课，选更适合他的一份。两份在他在意的地方真的分不出时，答 `差不多`。

为了独立，出题和作答时不要参考 `llm/rank/data/`、`llm/rank/output/` 里已有的画像、标签和答案。
