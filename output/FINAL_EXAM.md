# Final exam results (2026-10-17, scored once)

The system under test is git tag `exam-freeze` (33ffb54). Nothing was trained or tuned after the
exams were written. Exams, answers and personas are synthetic and AI-written (fresh Claude
subagents); there are no real students. Details and hashes are in `llm/parse/exam/PROVENANCE.md`
and `llm/rank/exam/PROVENANCE.md`.

## 1. Parsing: 304 new English sentences, 461 clauses (`llm/parse/output/exam/`)

| method | clause accuracy | sentences with every condition right |
| --- | ---: | ---: |
| keyword rules | 84.8% | 71.1% |
| TF-IDF + logistic regression (offline fallback, linear-r1) | 84.6% | 67.4% |
| Qwen 7B, no training, prompt v1 / v2 | 85.0% / 86.1% | 67.8% / 69.4% |
| Qwen 7B QLoRA round 1 | 92.4% | 76.0% |
| **Qwen 7B QLoRA round 2 (run time)** | **94.8%** | **78.0%** |

- Splitting (rules) was exactly right on 76.3% of sentences, the same for every method. Splitting
  and value reading, not the classifier, now limit the sentence score.
- Round 2 beats round 1 on unseen sentences (+2.4 points), so its gains on v2 were not over-fitting.
- The rule guard was left off because the validation set did not support it. On this exam it would
  have added about 1 point for round 2. That is recorded here, not acted on.
- Two independent annotators agreed on 461/461 labels. They are the same model reading the same
  rules, so this is not human agreement.

## 2. Asking back (`llm/parse/output/exam/clarify_results.md`, rules frozen before the exam)

With the round-2 model at run time: 24 of 461 clauses were wrong.
- Questions were asked about 16.7% of clauses.
- They covered 21 of the 24 wrong clauses (87.5%).
- For 18 of the 24 (75%), the right answer was one of the options. If students pick it, clause
  accuracy would go from 94.8% to about 98.7%.
- On average a sentence got 0.61 questions (0.32 clarifying, 0.30 offers); 49% of sentences got at
  least one.

Offline (linear model) it caught 57.7% of 71 wrong clauses.

## 3. Whole pipeline (`output/pipeline/…_exam.md`, `output/explain/…_exam.md`)

- 78% of sentences parsed to exactly the hand-written conditions.
- In 16 of 196 plannable sentences (8%), a recommended timetable broke a hand-written hard
  condition (v1 4%, v2 2%).
  - In 8 of these, a clarifying question offered the fix: they were "hates 8ams"-type hard/soft
    misreads, plus "only Tue and Thu" and a hedged named day.
  - The other 8 come from splitting or value reading, not from the label: "no classes before 10 no
    classes after 4 no classes on friday" without commas, "every second Tuesday", "7 max" after
    "10 hour days", and a few daily limits read as the wrong field.
- First pick the same as when planning from the hand-written conditions: 93%. Sentence to
  recommendation: 0.58 s median.
- Reasons: the template passed the fact-check 571/571. The Qwen 7B rewrite passed and was shown for
  67% (out-of-sample). The main reason matched the ranker's largest contribution for 86%.

## 4. Ranking: 20 new personas, 540 pairs (`llm/rank/output/exam_report.md`)

| method | pairwise accuracy (95% CI) | top-3 hit (ceiling 0.93) |
| --- | ---: | ---: |
| random | 50% | 0.38 |
| Qwen 14B judging each pair directly | 65.6% (59.3–71.9) | — |
| Qwen 14B picking the top 3 directly | — | 0.59 |
| cares-only rule (old placeholder) | 71.3% (63.9–79.0) | 0.53 |
| equal weights | 78.1% (72.8–83.2) | 0.68 |
| **trained logistic regression (run time)** | **83.3% (75.6–90.2)** | **0.79** |

- Two independent answerers agreed on 82% of the pairs where both picked a side. That is roughly
  the ceiling for this exam, and the trained model is at it.
- The answerers' first choice was in the model's top 3 for 97% of personas.
- The trained model takes under 1 ms per student. Qwen 14B takes 2 s per call and is less accurate.
