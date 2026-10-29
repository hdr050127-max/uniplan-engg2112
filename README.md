# UniPlan

A student describes their week in one sentence. UniPlan reads it into scheduling conditions, asks the student to confirm them, finds every clash-free timetable for their units, and recommends three with a short reason for each.

ENGG2112 (University of Sydney), Semester 2 2026, final project. The report is built from `report/latex/`.

> **All evaluation data is synthetic.** Every test sentence, student persona, preference label and final exam in this repository was written by AI models (Qwen2.5 and Claude). No real student took part. The class timetable itself is a real public snapshot of the 2026 Semester 2 University of Sydney timetable (24–25 September 2026).

## Run it

Python 3 (tested with 3.12). The web application uses only the standard library, so there is nothing to install.

```bash
python3 main.py
```

Then open <http://127.0.0.1:8766/>. Use `--port` to change the port.

The sentence parser normally calls a fine-tuned Qwen2.5-7B model through [Ollama](https://ollama.com). **You do not need it to run the app:** if no Ollama server answers within 15 s, the parser falls back to the TF-IDF + logistic regression model in `llm/parse/output/linear_model.json`, and the page asks the student to check each condition. To use your own Ollama server, set `UNIPLAN_OLLAMA_URL` (default `http://127.0.0.1:11434`). `python3 -m llm.ollama` shows which server and models are in use.

Run the tests (they pass without Ollama):

```bash
python3 -m unittest discover -s tests
```

## Final models

| Stage | Deployed model | File |
| --- | --- | --- |
| Parse the sentence | Qwen2.5-7B fine-tuned with QLoRA, round 2, served by Ollama as `uniplan-parse-7b-r2` | Training: `llm/parse/windows/train_lora.py` (see `llm/parse/windows/README.md`). The 7B weights are not in the repository because of their size. |
| Parse (offline fallback) | TF-IDF character n-grams + logistic regression (round 1) | `llm/parse/output/linear_model.json` |
| Build valid timetables | Exact backtracking search, no learning | `uniplan/schedule.py`, `uniplan/arrangement.py` |
| Rank the candidates | Pairwise logistic regression with student terms (round 1, 60 training personas) | `llm/rank/model.json` |
| Write the reasons | Templates from the ranker's per-feature contributions, with a fact check | `llm/explain.py` |

Every other model we compared (keyword rules, untrained Qwen2.5-7B, QLoRA round 1, random forest, small neural network, Qwen2.5-14B judging directly, the round-2 ranker that was not shipped) is kept with its scripts and outputs under `llm/parse/` and `llm/rank/`.

## Reproduce the report

| What | Command | Output |
| --- | --- | --- |
| Every number and table in the report | `python3 report/scripts/make_numbers.py` | `report/latex/generated/` |
| Feasible-timetable counts and timing | `python3 report/scripts/count_timetables.py` | `report/data/timetable_counts.json` |
| Parsing exam confidence intervals | `python3 report/scripts/parse_exam_ci.py` | `report/data/parse_exam_ci.json` |
| Ranking exam paired interval | `python3 report/scripts/rank_exam_paired.py` | `report/data/rank_exam_paired.json` |
| The PDF | `cd report/latex && tectonic -X compile main.tex` | `report/latex/main.pdf` |

None of these call a language model; they read the stored results. The PDF needs [Tectonic](https://tectonic-typesetting.github.io) and, for the Chinese quotations in Appendix A, the macOS font Hiragino Sans GB.

Re-running the experiments themselves needs Ollama with Qwen2.5-7B and 14B and, for fine-tuning, a CUDA GPU; the commands are in `llm/parse/evaluate.py`, `llm/rank/output/RESULTS.md` and `scripts/evaluate_*.py`. The final exams were frozen before scoring: their SHA-256 hashes and commits are in `llm/parse/exam/PROVENANCE.md` and `llm/rank/exam/PROVENANCE.md`.

## Repository map

| Path | Contents |
| --- | --- |
| `main.py`, `uniplan/` | Web application, data loading and the scheduler |
| `llm/contracts.py` | The interfaces between the four stages |
| `llm/parse/` | Sentence parsing: data generation, training, evaluation, clarifying questions, final exam |
| `llm/rank/` | Ranking: personas, teacher labels, training, evaluation, final exam |
| `llm/explain.py` | Reasons and their fact check |
| `data/` | Public timetable snapshot, building locations, unit catalogue |
| `output/` | Pipeline, reason and final-exam results |
| `tests/` | Unit and end-to-end tests |
| `report/` | Report source, number generator and derived data |
| `docs/DESIGN.md` | Web page design brief |

Some working notes (`RESEARCH_NOTES.md`, `RANKING_PLAN.md`, `README_uniplan.md` and most result summaries) are in Chinese.

## Use of AI

The system uses Qwen2.5-7B and 14B as described above. The code, experiments and report were developed with the help of Claude Code (Anthropic) under the author's direction; Appendix A of the report lists how, with selected prompts and the checks we applied.
