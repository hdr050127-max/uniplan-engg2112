# 需求解析：模型对比

生成于 2026-10-17 21:09，脚本 `python3 -m llm.parse.evaluate`。

- **验证集（val）**：278 个短句，来自 `train_round2.jsonl`。都不是真实学生数据：大部分由千问 7B 按类别生成，标签是生成时的类别，凡被 Claude 判过卷的改用 Claude 的标签；`train_round*` 里还有 Claude 写的难题（source = claude_train）。按生成请求划分，与训练集不重叠；另把 2–3 个短句拼成 103 句，测「切句 + 分类」整句全对率：整句找出的条件类别（不算 other）和原短句的类别完全一致才算对。
- **linear**：验证集上的数字来自只用训练集拟合的模型；测试集上用的是网页实际运行的模型（同样的超参数，在训练集 + 验证集上重新拟合，`output/linear_model.json`）。微调的 7B 只用训练集训练，按验证集选了第 2 轮，所以它的验证集数字略偏乐观。
- **示例（examples）**：`data/test_template.csv` 的 10 句格式示例，由 Claude 编写，**不是测试集**，只用来检查整条流程能跑通；数字仅供参考。
- **测试集（test）**：`exam/exam.csv`，304 句、461 个短句，一个全新的 Claude 子代理（只看过标注规则），另一个子代理独立复核，不是真实学生数据。只在最后评估时读，没有用来调参。

## 短句分类（验证集）

| 模型 | 准确率 | 宏平均 F1 | 整句全对率 | 每句耗时 (ms) | 模型大小 (MB) | 运行机器 | 备注 |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| keywords | 71.2% | 71.9% | 46.6% | 0.0 | – | arm64 Mac CPU |  |
| keywords + 护栏 | 71.2% | 71.9% | 46.6% | 0.0 | – | arm64 Mac CPU |  |
| linear-r1 | 88.8% | 88.0% | 59.2% | 0.0 | 1.17 | arm64 Mac CPU | TF-IDF char n-gram (1, 4), min_df 2, C=10; plain-Python scorer, trained on train only; round 1 (val: fitted on train only; test: the round-1 run-time model in output/round1/) |
| linear-r1 + 护栏 | 88.8% | 88.1% | 58.3% | 0.0 | 1.17 | arm64 Mac CPU | TF-IDF char n-gram (1, 4), min_df 2, C=10; plain-Python scorer, trained on train only; round 1 (val: fitted on train only; test: the round-1 run-time model in output/round1/) |
| ollama-short:uniplan-parse-7b | 95.0% | 95.1% | 78.6% | 272.3 | – | http://192.168.1.120:11434 |  |
| ollama-short:uniplan-parse-7b + 护栏 | 95.0% | 95.1% | 75.7% | 272.3 | – | http://192.168.1.120:11434 |  |
| ollama-short:uniplan-parse-7b-r2 | 95.3% | 95.3% | 76.7% | 293.5 | – | http://192.168.1.120:11434 |  |
| ollama-short:uniplan-parse-7b-r2 + 护栏 | 95.3% | 95.3% | 74.8% | 293.5 | – | http://192.168.1.120:11434 |  |
| ollama-v2:qwen2.5:7b | 90.3% | 89.8% | 64.1% | 185.4 | – | http://192.168.1.120:11434 |  |
| ollama-v2:qwen2.5:7b + 护栏 | 90.3% | 89.9% | 63.1% | 185.4 | – | http://192.168.1.120:11434 |  |
| ollama:qwen2.5:7b | 92.1% | 91.6% | 65.0% | 191.0 | – | http://192.168.1.120:11434 | no training, full prompt with rules, constrained to the 9 labels |
| ollama:qwen2.5:7b + 护栏 | 92.1% | 91.7% | 64.1% | 191.0 | – | http://192.168.1.120:11434 | no training, full prompt with rules, constrained to the 9 labels |

## 各类 F1（验证集）

| 模型 | blocked_time | max_days | max_daily_hours | lunch | in_person_only | prefer_fewer_days | prefer_less_waiting | prefer_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| keywords | 0.64 | 0.88 | 0.75 | 0.98 | 0.97 | 0.48 | 0.57 | 0.72 | 0.49 |
| keywords + 护栏 | 0.64 | 0.88 | 0.75 | 0.98 | 0.97 | 0.48 | 0.57 | 0.72 | 0.49 |
| linear-r1 | 0.85 | 0.99 | 0.89 | 1.00 | 0.96 | 0.91 | 0.92 | 0.89 | 0.51 |
| linear-r1 + 护栏 | 0.84 | 0.99 | 0.89 | 1.00 | 0.96 | 0.91 | 0.92 | 0.91 | 0.51 |
| ollama-short:uniplan-parse-7b | 0.89 | 1.00 | 0.95 | 1.00 | 1.00 | 0.96 | 0.97 | 0.95 | 0.84 |
| ollama-short:uniplan-parse-7b + 护栏 | 0.89 | 1.00 | 0.95 | 1.00 | 1.00 | 0.96 | 0.97 | 0.95 | 0.84 |
| ollama-short:uniplan-parse-7b-r2 | 0.94 | 1.00 | 0.95 | 1.00 | 0.98 | 0.97 | 0.94 | 0.95 | 0.85 |
| ollama-short:uniplan-parse-7b-r2 + 护栏 | 0.94 | 1.00 | 0.95 | 1.00 | 0.98 | 0.97 | 0.94 | 0.95 | 0.85 |
| ollama-v2:qwen2.5:7b | 0.87 | 0.96 | 1.00 | 0.96 | 0.92 | 0.93 | 0.95 | 0.85 | 0.65 |
| ollama-v2:qwen2.5:7b + 护栏 | 0.86 | 0.96 | 1.00 | 0.96 | 0.92 | 0.93 | 0.95 | 0.87 | 0.65 |
| ollama:qwen2.5:7b | 0.91 | 0.97 | 0.98 | 0.96 | 0.93 | 0.94 | 0.96 | 0.85 | 0.73 |
| ollama:qwen2.5:7b + 护栏 | 0.90 | 0.97 | 0.98 | 0.96 | 0.93 | 0.94 | 0.96 | 0.87 | 0.73 |

## 整条流程：10 句示例（不是测试集）

短句分类用的是标注者切好的短句；其余各列是从原句开始跑完整条流程（切句 → 分类 → 取值 → 合并）的结果，各条件列是该条件整句完全正确的比例。

| 模型 | 短句分类准确率 | 宏平均 F1 | 切句全对 | 条件全对（整句） | 每句耗时 (ms) | 不可上课时段 | 天数上限 | 每天上课 | 每天在校 | 午饭 | 只要线下 | 舒服时段 | 在意项 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| keywords | 94.7% | 94.1% | 100.0% | 90.0% | 0.0 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 90.0% |
| keywords + 护栏 | 94.7% | 94.1% | 100.0% | 90.0% | 0.0 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 90.0% |
| linear-r1 | 94.7% | 96.8% | 100.0% | 90.0% | 0.1 | 90.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 90.0% | 100.0% |
| linear-r1 + 护栏 | 94.7% | 96.8% | 100.0% | 90.0% | 0.1 | 90.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 90.0% | 100.0% |
| ollama-short:uniplan-parse-7b | 94.7% | 96.5% | 100.0% | 90.0% | 495.2 | 90.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| ollama-short:uniplan-parse-7b + 护栏 | 94.7% | 96.5% | 100.0% | 90.0% | 495.2 | 90.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| ollama-short:uniplan-parse-7b-r2 | 94.7% | 96.5% | 100.0% | 90.0% | 524.2 | 90.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| ollama-short:uniplan-parse-7b-r2 + 护栏 | 94.7% | 96.5% | 100.0% | 90.0% | 524.2 | 90.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| ollama-v2:qwen2.5:7b | 100.0% | 100.0% | 100.0% | 100.0% | 364.1 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| ollama-v2:qwen2.5:7b + 护栏 | 100.0% | 100.0% | 100.0% | 100.0% | 364.1 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| ollama:qwen2.5:7b | 100.0% | 100.0% | 100.0% | 100.0% | 367.5 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| ollama:qwen2.5:7b + 护栏 | 100.0% | 100.0% | 100.0% | 100.0% | 367.5 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |

## 整条流程：测试集 exam/exam.csv

短句分类用的是标注者切好的短句；其余各列是从原句开始跑完整条流程（切句 → 分类 → 取值 → 合并）的结果，各条件列是该条件整句完全正确的比例。

| 模型 | 短句分类准确率 | 宏平均 F1 | 切句全对 | 条件全对（整句） | 每句耗时 (ms) | 不可上课时段 | 天数上限 | 每天上课 | 每天在校 | 午饭 | 只要线下 | 舒服时段 | 在意项 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| keywords | 84.8% | 85.1% | 76.3% | 71.1% | 0.1 | 85.9% | 97.4% | 96.4% | 98.7% | 97.7% | 99.7% | 99.0% | 87.2% |
| keywords + 护栏 | 84.8% | 85.1% | 76.3% | 71.1% | 0.1 | 85.9% | 97.4% | 96.4% | 98.7% | 97.7% | 99.7% | 99.0% | 87.2% |
| linear-r1 | 84.6% | 86.5% | 76.3% | 67.4% | 0.1 | 83.9% | 97.0% | 98.0% | 98.4% | 96.4% | 99.3% | 96.1% | 84.5% |
| linear-r1 + 护栏 | 85.0% | 86.7% | 76.3% | 68.1% | 0.1 | 84.5% | 97.0% | 98.0% | 98.4% | 96.4% | 99.3% | 96.7% | 85.2% |
| ollama-short:uniplan-parse-7b | 92.4% | 94.2% | 76.3% | 76.0% | 420.0 | 85.2% | 98.4% | 98.7% | 99.0% | 96.7% | 99.7% | 95.7% | 91.4% |
| ollama-short:uniplan-parse-7b + 护栏 | 95.0% | 95.8% | 76.3% | 79.6% | 420.0 | 88.8% | 98.4% | 98.7% | 99.0% | 96.7% | 99.7% | 98.7% | 94.7% |
| ollama-short:uniplan-parse-7b-r2 | 94.8% | 95.7% | 76.3% | 78.0% | 470.3 | 89.1% | 98.7% | 98.7% | 99.0% | 97.4% | 99.7% | 98.0% | 91.1% |
| ollama-short:uniplan-parse-7b-r2 + 护栏 | 95.7% | 96.3% | 76.3% | 79.3% | 470.3 | 90.1% | 98.7% | 98.7% | 99.0% | 97.4% | 99.7% | 98.7% | 92.4% |
| ollama-v2:qwen2.5:7b | 86.1% | 87.3% | 76.3% | 69.4% | 288.4 | 85.5% | 96.4% | 98.4% | 99.0% | 97.0% | 99.3% | 92.1% | 85.5% |
| ollama-v2:qwen2.5:7b + 护栏 | 89.2% | 89.2% | 76.3% | 72.7% | 288.4 | 89.1% | 96.4% | 98.4% | 99.0% | 97.0% | 99.3% | 96.4% | 89.5% |
| ollama:qwen2.5:7b | 85.0% | 87.2% | 76.3% | 67.8% | 291.8 | 83.2% | 96.4% | 98.4% | 99.0% | 97.0% | 99.7% | 91.1% | 84.2% |
| ollama:qwen2.5:7b + 护栏 | 88.5% | 89.2% | 76.3% | 71.7% | 291.8 | 88.2% | 96.4% | 98.4% | 99.0% | 97.0% | 99.7% | 96.4% | 89.1% |

## 附：不训练的千问各尺寸（2026-10-16 在 Mac 上手工测的小样本，旧版提示词）

| 做法 | qwen2.5 0.5B | 1.5B | 3B | 7B |
| --- | ---: | ---: | ---: | ---: |
| 按短句分 9 类（20 个短句） | 12/20 | 16/20 | 14/20 | 19/20（约 5 秒/句） |
| 一次输出整套条件 JSON（4 句） | – | – | 1/4 | 1/4 |

样本很小，只说明两件事：小模型不训练不够准；让模型一次写出整套条件会漏项、凭空加偏好，所以改成「短句分类 + 规则提取」。

## 各类 F1（测试集，标注者切好的短句）

| 模型 | blocked_time | max_days | max_daily_hours | lunch | in_person_only | prefer_fewer_days | prefer_less_waiting | prefer_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| keywords | 0.90 | 0.91 | 0.90 | 0.98 | 0.97 | 0.65 | 0.81 | 0.87 | 0.65 |
| keywords + 护栏 | 0.90 | 0.91 | 0.90 | 0.98 | 0.97 | 0.65 | 0.81 | 0.87 | 0.65 |
| linear-r1 | 0.87 | 0.92 | 0.96 | 0.93 | 0.92 | 0.87 | 0.88 | 0.73 | 0.71 |
| linear-r1 + 护栏 | 0.88 | 0.92 | 0.96 | 0.93 | 0.92 | 0.87 | 0.88 | 0.74 | 0.71 |
| ollama-short:uniplan-parse-7b | 0.91 | 0.92 | 0.97 | 0.98 | 1.00 | 0.98 | 0.97 | 0.81 | 0.93 |
| ollama-short:uniplan-parse-7b + 护栏 | 0.95 | 0.92 | 0.97 | 0.98 | 1.00 | 0.98 | 0.97 | 0.91 | 0.93 |
| ollama-short:uniplan-parse-7b-r2 | 0.96 | 0.97 | 0.97 | 0.98 | 1.00 | 0.98 | 0.97 | 0.86 | 0.92 |
| ollama-short:uniplan-parse-7b-r2 + 护栏 | 0.97 | 0.97 | 0.97 | 0.98 | 1.00 | 0.98 | 0.97 | 0.90 | 0.92 |
| ollama-v2:qwen2.5:7b | 0.89 | 0.87 | 0.92 | 0.98 | 0.93 | 0.91 | 0.88 | 0.69 | 0.77 |
| ollama-v2:qwen2.5:7b + 护栏 | 0.93 | 0.87 | 0.92 | 0.98 | 0.93 | 0.91 | 0.88 | 0.82 | 0.77 |
| ollama:qwen2.5:7b | 0.86 | 0.89 | 0.92 | 1.00 | 0.95 | 0.91 | 0.87 | 0.67 | 0.76 |
| ollama:qwen2.5:7b + 护栏 | 0.92 | 0.89 | 0.92 | 1.00 | 0.95 | 0.91 | 0.87 | 0.81 | 0.76 |

## 混淆矩阵

行是正确类别，列是预测类别。

### keywords（验证集）

| gold \ predicted | blocked | max_days | max_hours | lunch | in_person | p_fewer_days | p_less_waiting | p_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocked | 35 | 0 | 1 | 0 | 0 | 0 | 0 | 3 | 0 |
| max_days | 5 | 33 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| max_hours | 0 | 4 | 15 | 0 | 1 | 0 | 0 | 0 | 0 |
| lunch | 0 | 0 | 0 | 24 | 0 | 0 | 0 | 0 | 0 |
| in_person | 0 | 0 | 0 | 0 | 28 | 0 | 0 | 0 | 0 |
| p_fewer_days | 10 | 0 | 0 | 0 | 0 | 11 | 0 | 0 | 13 |
| p_less_waiting | 9 | 0 | 2 | 0 | 0 | 1 | 15 | 4 | 6 |
| p_no_early_late | 2 | 0 | 0 | 1 | 0 | 0 | 0 | 19 | 5 |
| other | 9 | 0 | 2 | 0 | 1 | 0 | 1 | 0 | 18 |

### keywords + 护栏（验证集）

| gold \ predicted | blocked | max_days | max_hours | lunch | in_person | p_fewer_days | p_less_waiting | p_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocked | 35 | 0 | 1 | 0 | 0 | 0 | 0 | 3 | 0 |
| max_days | 5 | 33 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| max_hours | 0 | 4 | 15 | 0 | 1 | 0 | 0 | 0 | 0 |
| lunch | 0 | 0 | 0 | 24 | 0 | 0 | 0 | 0 | 0 |
| in_person | 0 | 0 | 0 | 0 | 28 | 0 | 0 | 0 | 0 |
| p_fewer_days | 10 | 0 | 0 | 0 | 0 | 11 | 0 | 0 | 13 |
| p_less_waiting | 9 | 0 | 2 | 0 | 0 | 1 | 15 | 4 | 6 |
| p_no_early_late | 2 | 0 | 0 | 1 | 0 | 0 | 0 | 19 | 5 |
| other | 9 | 0 | 2 | 0 | 1 | 0 | 1 | 0 | 18 |

### linear-r1（验证集）

| gold \ predicted | blocked | max_days | max_hours | lunch | in_person | p_fewer_days | p_less_waiting | p_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocked | 36 | 0 | 1 | 0 | 0 | 0 | 0 | 2 | 0 |
| max_days | 0 | 37 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| max_hours | 0 | 0 | 20 | 0 | 0 | 0 | 0 | 0 | 0 |
| lunch | 0 | 0 | 0 | 24 | 0 | 0 | 0 | 0 | 0 |
| in_person | 0 | 0 | 0 | 0 | 27 | 0 | 0 | 0 | 1 |
| p_fewer_days | 0 | 0 | 1 | 0 | 0 | 31 | 0 | 0 | 2 |
| p_less_waiting | 0 | 0 | 1 | 0 | 0 | 0 | 35 | 0 | 1 |
| p_no_early_late | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 25 | 0 |
| other | 9 | 0 | 2 | 0 | 1 | 2 | 3 | 2 | 12 |

### linear-r1 + 护栏（验证集）

| gold \ predicted | blocked | max_days | max_hours | lunch | in_person | p_fewer_days | p_less_waiting | p_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocked | 36 | 0 | 1 | 0 | 0 | 0 | 0 | 2 | 0 |
| max_days | 0 | 37 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| max_hours | 0 | 0 | 20 | 0 | 0 | 0 | 0 | 0 | 0 |
| lunch | 0 | 0 | 0 | 24 | 0 | 0 | 0 | 0 | 0 |
| in_person | 0 | 0 | 0 | 0 | 27 | 0 | 0 | 0 | 1 |
| p_fewer_days | 0 | 0 | 1 | 0 | 0 | 31 | 0 | 0 | 2 |
| p_less_waiting | 0 | 0 | 1 | 0 | 0 | 0 | 35 | 0 | 1 |
| p_no_early_late | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 25 | 0 |
| other | 10 | 0 | 2 | 0 | 1 | 2 | 3 | 1 | 12 |

### ollama-short:uniplan-parse-7b（验证集）

| gold \ predicted | blocked | max_days | max_hours | lunch | in_person | p_fewer_days | p_less_waiting | p_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocked | 33 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 4 |
| max_days | 0 | 38 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| max_hours | 0 | 0 | 18 | 0 | 0 | 1 | 0 | 0 | 1 |
| lunch | 0 | 0 | 0 | 24 | 0 | 0 | 0 | 0 | 0 |
| in_person | 0 | 0 | 0 | 0 | 28 | 0 | 0 | 0 | 0 |
| p_fewer_days | 0 | 0 | 0 | 0 | 0 | 32 | 1 | 0 | 1 |
| p_less_waiting | 0 | 0 | 0 | 0 | 0 | 0 | 37 | 0 | 0 |
| p_no_early_late | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 27 | 0 |
| other | 2 | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 27 |

### ollama-short:uniplan-parse-7b + 护栏（验证集）

| gold \ predicted | blocked | max_days | max_hours | lunch | in_person | p_fewer_days | p_less_waiting | p_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocked | 33 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 4 |
| max_days | 0 | 38 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| max_hours | 0 | 0 | 18 | 0 | 0 | 1 | 0 | 0 | 1 |
| lunch | 0 | 0 | 0 | 24 | 0 | 0 | 0 | 0 | 0 |
| in_person | 0 | 0 | 0 | 0 | 28 | 0 | 0 | 0 | 0 |
| p_fewer_days | 0 | 0 | 0 | 0 | 0 | 32 | 1 | 0 | 1 |
| p_less_waiting | 0 | 0 | 0 | 0 | 0 | 0 | 37 | 0 | 0 |
| p_no_early_late | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 27 | 0 |
| other | 2 | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 27 |

### ollama-short:uniplan-parse-7b-r2（验证集）

| gold \ predicted | blocked | max_days | max_hours | lunch | in_person | p_fewer_days | p_less_waiting | p_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocked | 37 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 |
| max_days | 0 | 38 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| max_hours | 0 | 0 | 19 | 0 | 0 | 0 | 1 | 0 | 0 |
| lunch | 0 | 0 | 0 | 24 | 0 | 0 | 0 | 0 | 0 |
| in_person | 0 | 0 | 0 | 0 | 28 | 0 | 0 | 0 | 0 |
| p_fewer_days | 0 | 0 | 0 | 0 | 0 | 32 | 2 | 0 | 0 |
| p_less_waiting | 0 | 0 | 0 | 0 | 0 | 0 | 37 | 0 | 0 |
| p_no_early_late | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 27 | 0 |
| other | 3 | 0 | 1 | 0 | 1 | 0 | 2 | 1 | 23 |

### ollama-short:uniplan-parse-7b-r2 + 护栏（验证集）

| gold \ predicted | blocked | max_days | max_hours | lunch | in_person | p_fewer_days | p_less_waiting | p_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocked | 37 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 |
| max_days | 0 | 38 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| max_hours | 0 | 0 | 19 | 0 | 0 | 0 | 1 | 0 | 0 |
| lunch | 0 | 0 | 0 | 24 | 0 | 0 | 0 | 0 | 0 |
| in_person | 0 | 0 | 0 | 0 | 28 | 0 | 0 | 0 | 0 |
| p_fewer_days | 0 | 0 | 0 | 0 | 0 | 32 | 2 | 0 | 0 |
| p_less_waiting | 0 | 0 | 0 | 0 | 0 | 0 | 37 | 0 | 0 |
| p_no_early_late | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 27 | 0 |
| other | 3 | 0 | 1 | 0 | 1 | 0 | 2 | 1 | 23 |

### ollama-v2:qwen2.5:7b（验证集）

| gold \ predicted | blocked | max_days | max_hours | lunch | in_person | p_fewer_days | p_less_waiting | p_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocked | 36 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 0 |
| max_days | 0 | 35 | 0 | 0 | 0 | 3 | 0 | 0 | 0 |
| max_hours | 0 | 0 | 20 | 0 | 0 | 0 | 0 | 0 | 0 |
| lunch | 0 | 0 | 0 | 24 | 0 | 0 | 0 | 0 | 0 |
| in_person | 1 | 0 | 0 | 0 | 27 | 0 | 0 | 0 | 0 |
| p_fewer_days | 0 | 0 | 0 | 0 | 0 | 34 | 0 | 0 | 0 |
| p_less_waiting | 0 | 0 | 0 | 0 | 0 | 0 | 37 | 0 | 0 |
| p_no_early_late | 1 | 0 | 0 | 2 | 0 | 0 | 1 | 23 | 0 |
| other | 6 | 0 | 0 | 0 | 4 | 2 | 3 | 1 | 15 |

### ollama-v2:qwen2.5:7b + 护栏（验证集）

| gold \ predicted | blocked | max_days | max_hours | lunch | in_person | p_fewer_days | p_less_waiting | p_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocked | 36 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 0 |
| max_days | 0 | 35 | 0 | 0 | 0 | 3 | 0 | 0 | 0 |
| max_hours | 0 | 0 | 20 | 0 | 0 | 0 | 0 | 0 | 0 |
| lunch | 0 | 0 | 0 | 24 | 0 | 0 | 0 | 0 | 0 |
| in_person | 1 | 0 | 0 | 0 | 27 | 0 | 0 | 0 | 0 |
| p_fewer_days | 0 | 0 | 0 | 0 | 0 | 34 | 0 | 0 | 0 |
| p_less_waiting | 0 | 0 | 0 | 0 | 0 | 0 | 37 | 0 | 0 |
| p_no_early_late | 1 | 0 | 0 | 2 | 0 | 0 | 1 | 23 | 0 |
| other | 7 | 0 | 0 | 0 | 4 | 2 | 3 | 0 | 15 |

### ollama:qwen2.5:7b（验证集）

| gold \ predicted | blocked | max_days | max_hours | lunch | in_person | p_fewer_days | p_less_waiting | p_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocked | 37 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 |
| max_days | 0 | 36 | 0 | 0 | 0 | 2 | 0 | 0 | 0 |
| max_hours | 0 | 0 | 20 | 0 | 0 | 0 | 0 | 0 | 0 |
| lunch | 0 | 0 | 0 | 24 | 0 | 0 | 0 | 0 | 0 |
| in_person | 1 | 0 | 0 | 0 | 27 | 0 | 0 | 0 | 0 |
| p_fewer_days | 0 | 0 | 0 | 0 | 0 | 34 | 0 | 0 | 0 |
| p_less_waiting | 0 | 0 | 0 | 0 | 0 | 0 | 37 | 0 | 0 |
| p_no_early_late | 0 | 0 | 1 | 2 | 0 | 0 | 1 | 23 | 0 |
| other | 4 | 0 | 0 | 0 | 3 | 2 | 2 | 2 | 18 |

### ollama:qwen2.5:7b + 护栏（验证集）

| gold \ predicted | blocked | max_days | max_hours | lunch | in_person | p_fewer_days | p_less_waiting | p_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocked | 37 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 |
| max_days | 0 | 36 | 0 | 0 | 0 | 2 | 0 | 0 | 0 |
| max_hours | 0 | 0 | 20 | 0 | 0 | 0 | 0 | 0 | 0 |
| lunch | 0 | 0 | 0 | 24 | 0 | 0 | 0 | 0 | 0 |
| in_person | 1 | 0 | 0 | 0 | 27 | 0 | 0 | 0 | 0 |
| p_fewer_days | 0 | 0 | 0 | 0 | 0 | 34 | 0 | 0 | 0 |
| p_less_waiting | 0 | 0 | 0 | 0 | 0 | 0 | 37 | 0 | 0 |
| p_no_early_late | 0 | 0 | 1 | 2 | 0 | 0 | 1 | 23 | 0 |
| other | 5 | 0 | 0 | 0 | 3 | 2 | 2 | 1 | 18 |

### keywords（测试集 exam/exam.csv）

| gold \ predicted | blocked | max_days | max_hours | lunch | in_person | p_fewer_days | p_less_waiting | p_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocked | 144 | 0 | 0 | 0 | 0 | 0 | 0 | 6 | 9 |
| max_days | 1 | 32 | 0 | 0 | 0 | 0 | 0 | 0 | 4 |
| max_hours | 0 | 1 | 33 | 0 | 0 | 0 | 0 | 0 | 2 |
| lunch | 0 | 0 | 0 | 30 | 0 | 0 | 0 | 0 | 1 |
| in_person | 0 | 0 | 0 | 0 | 19 | 0 | 0 | 0 | 1 |
| p_fewer_days | 3 | 0 | 1 | 0 | 0 | 13 | 0 | 0 | 10 |
| p_less_waiting | 0 | 0 | 3 | 0 | 0 | 0 | 25 | 0 | 3 |
| p_no_early_late | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 45 | 2 |
| other | 12 | 0 | 0 | 0 | 0 | 0 | 6 | 5 | 50 |

### keywords + 护栏（测试集 exam/exam.csv）

| gold \ predicted | blocked | max_days | max_hours | lunch | in_person | p_fewer_days | p_less_waiting | p_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocked | 144 | 0 | 0 | 0 | 0 | 0 | 0 | 6 | 9 |
| max_days | 1 | 32 | 0 | 0 | 0 | 0 | 0 | 0 | 4 |
| max_hours | 0 | 1 | 33 | 0 | 0 | 0 | 0 | 0 | 2 |
| lunch | 0 | 0 | 0 | 30 | 0 | 0 | 0 | 0 | 1 |
| in_person | 0 | 0 | 0 | 0 | 19 | 0 | 0 | 0 | 1 |
| p_fewer_days | 3 | 0 | 1 | 0 | 0 | 13 | 0 | 0 | 10 |
| p_less_waiting | 0 | 0 | 3 | 0 | 0 | 0 | 25 | 0 | 3 |
| p_no_early_late | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 45 | 2 |
| other | 12 | 0 | 0 | 0 | 0 | 0 | 6 | 5 | 50 |

### linear-r1（测试集 exam/exam.csv）

| gold \ predicted | blocked | max_days | max_hours | lunch | in_person | p_fewer_days | p_less_waiting | p_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocked | 136 | 0 | 0 | 1 | 0 | 1 | 1 | 6 | 14 |
| max_days | 1 | 34 | 0 | 0 | 0 | 0 | 0 | 0 | 2 |
| max_hours | 0 | 2 | 34 | 0 | 0 | 0 | 0 | 0 | 0 |
| lunch | 2 | 0 | 0 | 28 | 0 | 0 | 0 | 0 | 1 |
| in_person | 0 | 0 | 0 | 0 | 18 | 0 | 0 | 0 | 2 |
| p_fewer_days | 3 | 0 | 0 | 0 | 0 | 23 | 1 | 0 | 0 |
| p_less_waiting | 0 | 0 | 0 | 0 | 0 | 0 | 29 | 1 | 1 |
| p_no_early_late | 5 | 1 | 0 | 0 | 0 | 0 | 1 | 33 | 7 |
| other | 7 | 0 | 1 | 0 | 1 | 2 | 3 | 4 | 55 |

### linear-r1 + 护栏（测试集 exam/exam.csv）

| gold \ predicted | blocked | max_days | max_hours | lunch | in_person | p_fewer_days | p_less_waiting | p_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocked | 138 | 0 | 0 | 1 | 0 | 1 | 1 | 4 | 14 |
| max_days | 1 | 34 | 0 | 0 | 0 | 0 | 0 | 0 | 2 |
| max_hours | 0 | 2 | 34 | 0 | 0 | 0 | 0 | 0 | 0 |
| lunch | 2 | 0 | 0 | 28 | 0 | 0 | 0 | 0 | 1 |
| in_person | 0 | 0 | 0 | 0 | 18 | 0 | 0 | 0 | 2 |
| p_fewer_days | 3 | 0 | 0 | 0 | 0 | 23 | 1 | 0 | 0 |
| p_less_waiting | 0 | 0 | 0 | 0 | 0 | 0 | 29 | 1 | 1 |
| p_no_early_late | 5 | 1 | 0 | 0 | 0 | 0 | 1 | 33 | 7 |
| other | 7 | 0 | 1 | 0 | 1 | 2 | 3 | 4 | 55 |

### ollama-short:uniplan-parse-7b（测试集 exam/exam.csv）

| gold \ predicted | blocked | max_days | max_hours | lunch | in_person | p_fewer_days | p_less_waiting | p_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocked | 134 | 4 | 0 | 1 | 0 | 0 | 0 | 17 | 3 |
| max_days | 0 | 37 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| max_hours | 0 | 1 | 35 | 0 | 0 | 0 | 0 | 0 | 0 |
| lunch | 0 | 0 | 0 | 31 | 0 | 0 | 0 | 0 | 0 |
| in_person | 0 | 0 | 0 | 0 | 20 | 0 | 0 | 0 | 0 |
| p_fewer_days | 0 | 0 | 0 | 0 | 0 | 27 | 0 | 0 | 0 |
| p_less_waiting | 0 | 0 | 0 | 0 | 0 | 1 | 30 | 0 | 0 |
| p_no_early_late | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 45 | 1 |
| other | 2 | 0 | 1 | 0 | 0 | 0 | 1 | 2 | 67 |

### ollama-short:uniplan-parse-7b + 护栏（测试集 exam/exam.csv）

| gold \ predicted | blocked | max_days | max_hours | lunch | in_person | p_fewer_days | p_less_waiting | p_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocked | 146 | 4 | 0 | 1 | 0 | 0 | 0 | 5 | 3 |
| max_days | 0 | 37 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| max_hours | 0 | 1 | 35 | 0 | 0 | 0 | 0 | 0 | 0 |
| lunch | 0 | 0 | 0 | 31 | 0 | 0 | 0 | 0 | 0 |
| in_person | 0 | 0 | 0 | 0 | 20 | 0 | 0 | 0 | 0 |
| p_fewer_days | 0 | 0 | 0 | 0 | 0 | 27 | 0 | 0 | 0 |
| p_less_waiting | 0 | 0 | 0 | 0 | 0 | 1 | 30 | 0 | 0 |
| p_no_early_late | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 45 | 1 |
| other | 2 | 0 | 1 | 0 | 0 | 0 | 1 | 2 | 67 |

### ollama-short:uniplan-parse-7b-r2（测试集 exam/exam.csv）

| gold \ predicted | blocked | max_days | max_hours | lunch | in_person | p_fewer_days | p_less_waiting | p_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocked | 149 | 1 | 0 | 1 | 0 | 1 | 0 | 7 | 0 |
| max_days | 0 | 37 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| max_hours | 0 | 0 | 36 | 0 | 0 | 0 | 0 | 0 | 0 |
| lunch | 0 | 0 | 0 | 31 | 0 | 0 | 0 | 0 | 0 |
| in_person | 0 | 0 | 0 | 0 | 20 | 0 | 0 | 0 | 0 |
| p_fewer_days | 0 | 0 | 0 | 0 | 0 | 27 | 0 | 0 | 0 |
| p_less_waiting | 0 | 0 | 1 | 0 | 0 | 0 | 30 | 0 | 0 |
| p_no_early_late | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 45 | 0 |
| other | 3 | 0 | 1 | 0 | 0 | 0 | 1 | 6 | 62 |

### ollama-short:uniplan-parse-7b-r2 + 护栏（测试集 exam/exam.csv）

| gold \ predicted | blocked | max_days | max_hours | lunch | in_person | p_fewer_days | p_less_waiting | p_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocked | 153 | 1 | 0 | 1 | 0 | 1 | 0 | 3 | 0 |
| max_days | 0 | 37 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| max_hours | 0 | 0 | 36 | 0 | 0 | 0 | 0 | 0 | 0 |
| lunch | 0 | 0 | 0 | 31 | 0 | 0 | 0 | 0 | 0 |
| in_person | 0 | 0 | 0 | 0 | 20 | 0 | 0 | 0 | 0 |
| p_fewer_days | 0 | 0 | 0 | 0 | 0 | 27 | 0 | 0 | 0 |
| p_less_waiting | 0 | 0 | 1 | 0 | 0 | 0 | 30 | 0 | 0 |
| p_no_early_late | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 45 | 0 |
| other | 4 | 0 | 1 | 0 | 0 | 0 | 1 | 5 | 62 |

### ollama-v2:qwen2.5:7b（测试集 exam/exam.csv）

| gold \ predicted | blocked | max_days | max_hours | lunch | in_person | p_fewer_days | p_less_waiting | p_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocked | 137 | 2 | 2 | 0 | 0 | 0 | 0 | 15 | 3 |
| max_days | 3 | 31 | 0 | 0 | 0 | 3 | 0 | 0 | 0 |
| max_hours | 0 | 0 | 36 | 0 | 0 | 0 | 0 | 0 | 0 |
| lunch | 0 | 0 | 0 | 31 | 0 | 0 | 0 | 0 | 0 |
| in_person | 0 | 0 | 0 | 0 | 20 | 0 | 0 | 0 | 0 |
| p_fewer_days | 1 | 0 | 0 | 0 | 0 | 26 | 0 | 0 | 0 |
| p_less_waiting | 0 | 0 | 0 | 1 | 0 | 0 | 30 | 0 | 0 |
| p_no_early_late | 2 | 1 | 3 | 0 | 0 | 0 | 1 | 36 | 4 |
| other | 6 | 0 | 1 | 0 | 3 | 1 | 6 | 6 | 50 |

### ollama-v2:qwen2.5:7b + 护栏（测试集 exam/exam.csv）

| gold \ predicted | blocked | max_days | max_hours | lunch | in_person | p_fewer_days | p_less_waiting | p_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocked | 151 | 2 | 2 | 0 | 0 | 0 | 0 | 1 | 3 |
| max_days | 3 | 31 | 0 | 0 | 0 | 3 | 0 | 0 | 0 |
| max_hours | 0 | 0 | 36 | 0 | 0 | 0 | 0 | 0 | 0 |
| lunch | 0 | 0 | 0 | 31 | 0 | 0 | 0 | 0 | 0 |
| in_person | 0 | 0 | 0 | 0 | 20 | 0 | 0 | 0 | 0 |
| p_fewer_days | 1 | 0 | 0 | 0 | 0 | 26 | 0 | 0 | 0 |
| p_less_waiting | 0 | 0 | 0 | 1 | 0 | 0 | 30 | 0 | 0 |
| p_no_early_late | 2 | 1 | 3 | 0 | 0 | 0 | 1 | 36 | 4 |
| other | 8 | 0 | 1 | 0 | 3 | 1 | 6 | 4 | 50 |

### ollama:qwen2.5:7b（测试集 exam/exam.csv）

| gold \ predicted | blocked | max_days | max_hours | lunch | in_person | p_fewer_days | p_less_waiting | p_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocked | 130 | 2 | 4 | 0 | 0 | 0 | 0 | 19 | 4 |
| max_days | 3 | 32 | 0 | 0 | 0 | 2 | 0 | 0 | 0 |
| max_hours | 0 | 0 | 36 | 0 | 0 | 0 | 0 | 0 | 0 |
| lunch | 0 | 0 | 0 | 31 | 0 | 0 | 0 | 0 | 0 |
| in_person | 0 | 0 | 0 | 0 | 20 | 0 | 0 | 0 | 0 |
| p_fewer_days | 1 | 0 | 0 | 0 | 0 | 26 | 0 | 0 | 0 |
| p_less_waiting | 0 | 0 | 0 | 0 | 0 | 1 | 30 | 0 | 0 |
| p_no_early_late | 2 | 1 | 1 | 0 | 0 | 0 | 1 | 36 | 6 |
| other | 6 | 0 | 1 | 0 | 2 | 1 | 7 | 5 | 51 |

### ollama:qwen2.5:7b + 护栏（测试集 exam/exam.csv）

| gold \ predicted | blocked | max_days | max_hours | lunch | in_person | p_fewer_days | p_less_waiting | p_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocked | 146 | 2 | 4 | 0 | 0 | 0 | 0 | 3 | 4 |
| max_days | 3 | 32 | 0 | 0 | 0 | 2 | 0 | 0 | 0 |
| max_hours | 0 | 0 | 36 | 0 | 0 | 0 | 0 | 0 | 0 |
| lunch | 0 | 0 | 0 | 31 | 0 | 0 | 0 | 0 | 0 |
| in_person | 0 | 0 | 0 | 0 | 20 | 0 | 0 | 0 | 0 |
| p_fewer_days | 1 | 0 | 0 | 0 | 0 | 26 | 0 | 0 | 0 |
| p_less_waiting | 0 | 0 | 0 | 0 | 0 | 1 | 30 | 0 | 0 |
| p_no_early_late | 2 | 1 | 1 | 0 | 0 | 0 | 1 | 36 | 6 |
| other | 8 | 0 | 1 | 0 | 2 | 1 | 7 | 3 | 51 |
