# Parsing final exam (2026-10-17)

Synthetic and AI-written. These are not real students.

- `exam.csv`: 304 English sentences, 461 clauses, the answer key. It was written by a fresh
  Claude subagent that saw only `data/README.md`, `labels.py` and `gold.py`. It did not see
  the training data, the test sets v1/v2, any predictions or any model error. It was asked for
  realistic, hard sentences (typos, slang, 2–4 requests per sentence, distracting numbers,
  negations, soft vs hard wording) and roughly the natural label mix. It dropped 93 candidate
  sentences whose answer the rules could not decide. `build_exam.py` rebuilds `exam.csv` exactly.
  The user asked for English only.
- `exam_second_annotator.csv`: a second fresh subagent labelled the same clauses (given only the
  sentences and the clause split, not the labels) under the same rules. Its tool log shows it never
  opened `exam.csv` or `build_exam.py`.

## Agreement
- Labels: 461/461.
- Fields: 458/461 as written; the 3 differences are notation only (`Mon,Wed-Fri` vs
  `Mon,Wed,Thu,Fri`), so the loaded conditions are identical for all 304 sentences.

This is not human inter-annotator agreement. Both annotators are the same model reading the same
rulebook, and the writer removed sentences the rules could not settle. The agreement shows that
the key follows the rules consistently. It does not show that real students' sentences are this
clear-cut.

## Frozen before scoring
- `exam.csv` SHA-256 195925d33cfb95fceff2bb36ec2fd5182ae50e8350dedb6d037f2ed0bd1b0f07
- system under test: git tag `exam-freeze` (33ffb54)
