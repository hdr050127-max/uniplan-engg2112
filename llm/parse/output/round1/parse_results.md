# 需求解析：模型对比

生成于 2026-10-17 17:53，脚本 `python3 -m llm.parse.evaluate`。

- **验证集（val）**：279 个短句，来自 `train_round1.jsonl`。都不是真实学生数据：大部分由千问 7B 按类别生成，标签是生成时的类别，凡被 Claude 判过卷的改用 Claude 的标签；`train_round*` 里还有 Claude 写的难题（source = claude_train）。按生成请求划分，与训练集不重叠；另把 2–3 个短句拼成 103 句，测「切句 + 分类」整句全对率：整句找出的条件类别（不算 other）和原短句的类别完全一致才算对。
- **linear**：验证集上的数字来自只用训练集拟合的模型；测试集上用的是网页实际运行的模型（同样的超参数，在训练集 + 验证集上重新拟合，`output/linear_model.json`）。微调的 7B 只用训练集训练，按验证集选了第 2 轮，所以它的验证集数字略偏乐观。
- **示例（examples）**：`data/test_template.csv` 的 10 句格式示例，由 Claude 编写，**不是测试集**，只用来检查整条流程能跑通；数字仅供参考。
- **测试集（test）**：`data/test_claude.csv`，142 句英文，由 Claude（总控窗口）按用户要求撰写（见 `data/TEST_SOURCES.md`），不是真实学生数据；与训练数据的生成模型（千问）不是同一家。只在最后评估时读，没有用来调参。

## 短句分类（验证集）

| 模型 | 准确率 | 宏平均 F1 | 整句全对率 | 每句耗时 (ms) | 模型大小 (MB) | 运行机器 | 备注 |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| keywords | 71.7% | 72.3% | 45.6% | 0.0 | – | arm64 Mac CPU |  |
| linear | 89.2% | 88.4% | 53.4% | 0.0 | 1.17 | arm64 Mac CPU | TF-IDF char n-gram (1, 4), min_df 2, C=10; plain-Python scorer, trained on train only |
| ollama-short:uniplan-parse-7b | 95.7% | 95.8% | 76.7% | 272.4 | – | http://192.168.1.120:11434 |  |
| ollama:qwen2.5:7b | 92.8% | 92.4% | 64.1% | 191.0 | – | http://192.168.1.120:11434 | no training, full prompt with rules, constrained to the 9 labels |

## 各类 F1（验证集）

| 模型 | blocked_time | max_days | max_daily_hours | lunch | in_person_only | prefer_fewer_days | prefer_less_waiting | prefer_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| keywords | 0.65 | 0.88 | 0.75 | 0.98 | 0.97 | 0.48 | 0.57 | 0.75 | 0.49 |
| linear | 0.86 | 0.99 | 0.89 | 1.00 | 0.96 | 0.91 | 0.92 | 0.92 | 0.51 |
| ollama-short:uniplan-parse-7b | 0.92 | 1.00 | 0.95 | 1.00 | 1.00 | 0.96 | 0.97 | 0.98 | 0.84 |
| ollama:qwen2.5:7b | 0.94 | 0.97 | 0.98 | 0.96 | 0.93 | 0.94 | 0.96 | 0.90 | 0.73 |

## 整条流程：10 句示例（不是测试集）

短句分类用的是标注者切好的短句；其余各列是从原句开始跑完整条流程（切句 → 分类 → 取值 → 合并）的结果，各条件列是该条件整句完全正确的比例。

| 模型 | 短句分类准确率 | 宏平均 F1 | 切句全对 | 条件全对（整句） | 每句耗时 (ms) | 不可上课时段 | 天数上限 | 每天上课 | 每天在校 | 午饭 | 只要线下 | 舒服时段 | 在意项 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| keywords | 94.7% | 94.1% | 100.0% | 90.0% | 0.0 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 90.0% |
| linear | 94.7% | 96.8% | 100.0% | 90.0% | 0.1 | 90.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 90.0% | 100.0% |
| ollama-short:uniplan-parse-7b | 94.7% | 96.5% | 100.0% | 90.0% | 495.2 | 90.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| ollama:qwen2.5:7b | 100.0% | 100.0% | 100.0% | 100.0% | 367.5 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |

## 整条流程：测试集（Claude 撰写，142 句英文）

短句分类用的是标注者切好的短句；其余各列是从原句开始跑完整条流程（切句 → 分类 → 取值 → 合并）的结果，各条件列是该条件整句完全正确的比例。

| 模型 | 短句分类准确率 | 宏平均 F1 | 切句全对 | 条件全对（整句） | 每句耗时 (ms) | 不可上课时段 | 天数上限 | 每天上课 | 每天在校 | 午饭 | 只要线下 | 舒服时段 | 在意项 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| keywords | 74.7% | 71.8% | 66.9% | 57.7% | 0.1 | 81.0% | 95.8% | 95.8% | 100.0% | 96.5% | 97.9% | 97.9% | 85.2% |
| linear | 85.6% | 84.9% | 66.9% | 62.0% | 0.1 | 81.7% | 96.5% | 97.9% | 100.0% | 97.2% | 97.9% | 96.5% | 88.0% |
| ollama-short:uniplan-parse-7b | 87.9% | 89.8% | 66.9% | 66.9% | 389.0 | 79.6% | 95.8% | 99.3% | 100.0% | 97.9% | 100.0% | 93.0% | 85.9% |
| ollama:qwen2.5:7b | 84.5% | 82.4% | 66.9% | 63.4% | 296.5 | 82.4% | 96.5% | 99.3% | 100.0% | 97.2% | 98.6% | 95.1% | 84.5% |

## 附：不训练的千问各尺寸（2026-10-16 在 Mac 上手工测的小样本，旧版提示词）

| 做法 | qwen2.5 0.5B | 1.5B | 3B | 7B |
| --- | ---: | ---: | ---: | ---: |
| 按短句分 9 类（20 个短句） | 12/20 | 16/20 | 14/20 | 19/20（约 5 秒/句） |
| 一次输出整套条件 JSON（4 句） | – | – | 1/4 | 1/4 |

样本很小，只说明两件事：小模型不训练不够准；让模型一次写出整套条件会漏项、凭空加偏好，所以改成「短句分类 + 规则提取」。

## 各类 F1（测试集，标注者切好的短句）

| 模型 | blocked_time | max_days | max_daily_hours | lunch | in_person_only | prefer_fewer_days | prefer_less_waiting | prefer_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| keywords | 0.87 | 0.86 | 0.72 | 0.91 | 0.84 | 0.53 | 0.55 | 0.76 | 0.42 |
| linear | 0.94 | 0.93 | 0.96 | 0.95 | 0.84 | 0.80 | 0.80 | 0.76 | 0.65 |
| ollama-short:uniplan-parse-7b | 0.86 | 0.87 | 1.00 | 1.00 | 1.00 | 0.76 | 0.92 | 0.74 | 0.92 |
| ollama:qwen2.5:7b | 0.94 | 0.89 | 0.92 | 0.95 | 0.91 | 0.70 | 0.73 | 0.76 | 0.62 |

## 混淆矩阵

行是正确类别，列是预测类别。

### keywords（验证集）

| gold \ predicted | blocked | max_days | max_hours | lunch | in_person | p_fewer_days | p_less_waiting | p_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocked | 35 | 0 | 1 | 0 | 0 | 0 | 0 | 1 | 0 |
| max_days | 5 | 33 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| max_hours | 0 | 4 | 15 | 0 | 1 | 0 | 0 | 0 | 0 |
| lunch | 0 | 0 | 0 | 24 | 0 | 0 | 0 | 0 | 0 |
| in_person | 0 | 0 | 0 | 0 | 28 | 0 | 0 | 0 | 0 |
| p_fewer_days | 10 | 0 | 0 | 0 | 0 | 11 | 0 | 0 | 13 |
| p_less_waiting | 9 | 0 | 2 | 0 | 0 | 1 | 15 | 4 | 6 |
| p_no_early_late | 3 | 0 | 0 | 1 | 0 | 0 | 0 | 21 | 5 |
| other | 9 | 0 | 2 | 0 | 1 | 0 | 1 | 0 | 18 |

### linear（验证集）

| gold \ predicted | blocked | max_days | max_hours | lunch | in_person | p_fewer_days | p_less_waiting | p_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocked | 36 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| max_days | 0 | 37 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| max_hours | 0 | 0 | 20 | 0 | 0 | 0 | 0 | 0 | 0 |
| lunch | 0 | 0 | 0 | 24 | 0 | 0 | 0 | 0 | 0 |
| in_person | 0 | 0 | 0 | 0 | 27 | 0 | 0 | 0 | 1 |
| p_fewer_days | 0 | 0 | 1 | 0 | 0 | 31 | 0 | 0 | 2 |
| p_less_waiting | 0 | 0 | 1 | 0 | 0 | 0 | 35 | 0 | 1 |
| p_no_early_late | 2 | 0 | 0 | 0 | 0 | 0 | 1 | 27 | 0 |
| other | 9 | 0 | 2 | 0 | 1 | 2 | 3 | 2 | 12 |

### ollama-short:uniplan-parse-7b（验证集）

| gold \ predicted | blocked | max_days | max_hours | lunch | in_person | p_fewer_days | p_less_waiting | p_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocked | 33 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 4 |
| max_days | 0 | 38 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| max_hours | 0 | 0 | 18 | 0 | 0 | 1 | 0 | 0 | 1 |
| lunch | 0 | 0 | 0 | 24 | 0 | 0 | 0 | 0 | 0 |
| in_person | 0 | 0 | 0 | 0 | 28 | 0 | 0 | 0 | 0 |
| p_fewer_days | 0 | 0 | 0 | 0 | 0 | 32 | 1 | 0 | 1 |
| p_less_waiting | 0 | 0 | 0 | 0 | 0 | 0 | 37 | 0 | 0 |
| p_no_early_late | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 30 | 0 |
| other | 2 | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 27 |

### ollama:qwen2.5:7b（验证集）

| gold \ predicted | blocked | max_days | max_hours | lunch | in_person | p_fewer_days | p_less_waiting | p_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocked | 37 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| max_days | 0 | 36 | 0 | 0 | 0 | 2 | 0 | 0 | 0 |
| max_hours | 0 | 0 | 20 | 0 | 0 | 0 | 0 | 0 | 0 |
| lunch | 0 | 0 | 0 | 24 | 0 | 0 | 0 | 0 | 0 |
| in_person | 1 | 0 | 0 | 0 | 27 | 0 | 0 | 0 | 0 |
| p_fewer_days | 0 | 0 | 0 | 0 | 0 | 34 | 0 | 0 | 0 |
| p_less_waiting | 0 | 0 | 0 | 0 | 0 | 0 | 37 | 0 | 0 |
| p_no_early_late | 0 | 0 | 1 | 2 | 0 | 0 | 1 | 26 | 0 |
| other | 4 | 0 | 0 | 0 | 3 | 2 | 2 | 2 | 18 |

### keywords（测试集）

| gold \ predicted | blocked | max_days | max_hours | lunch | in_person | p_fewer_days | p_less_waiting | p_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocked | 57 | 0 | 1 | 1 | 0 | 0 | 0 | 1 | 4 |
| max_days | 0 | 12 | 0 | 0 | 0 | 1 | 0 | 0 | 2 |
| max_hours | 0 | 1 | 9 | 0 | 0 | 0 | 0 | 0 | 1 |
| lunch | 0 | 0 | 0 | 10 | 0 | 0 | 0 | 0 | 0 |
| in_person | 0 | 0 | 0 | 0 | 8 | 0 | 0 | 0 | 2 |
| p_fewer_days | 2 | 0 | 1 | 0 | 0 | 4 | 0 | 0 | 3 |
| p_less_waiting | 2 | 0 | 2 | 0 | 0 | 0 | 6 | 0 | 1 |
| p_no_early_late | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 13 | 2 |
| other | 5 | 0 | 1 | 0 | 1 | 0 | 5 | 3 | 11 |

### linear（测试集）

| gold \ predicted | blocked | max_days | max_hours | lunch | in_person | p_fewer_days | p_less_waiting | p_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocked | 58 | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 4 |
| max_days | 0 | 14 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| max_hours | 0 | 0 | 11 | 0 | 0 | 0 | 0 | 0 | 0 |
| lunch | 0 | 0 | 0 | 10 | 0 | 0 | 0 | 0 | 0 |
| in_person | 0 | 0 | 0 | 0 | 8 | 0 | 0 | 0 | 2 |
| p_fewer_days | 0 | 0 | 0 | 0 | 0 | 8 | 1 | 0 | 1 |
| p_less_waiting | 0 | 0 | 1 | 0 | 0 | 0 | 10 | 0 | 0 |
| p_no_early_late | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 13 | 2 |
| other | 1 | 1 | 0 | 0 | 1 | 1 | 2 | 3 | 17 |

### ollama-short:uniplan-parse-7b（测试集）

| gold \ predicted | blocked | max_days | max_hours | lunch | in_person | p_fewer_days | p_less_waiting | p_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocked | 50 | 3 | 0 | 0 | 0 | 1 | 0 | 9 | 1 |
| max_days | 0 | 14 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| max_hours | 0 | 0 | 11 | 0 | 0 | 0 | 0 | 0 | 0 |
| lunch | 0 | 0 | 0 | 10 | 0 | 0 | 0 | 0 | 0 |
| in_person | 0 | 0 | 0 | 0 | 10 | 0 | 0 | 0 | 0 |
| p_fewer_days | 1 | 0 | 0 | 0 | 0 | 8 | 1 | 0 | 0 |
| p_less_waiting | 0 | 0 | 0 | 0 | 0 | 0 | 11 | 0 | 0 |
| p_no_early_late | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 16 | 0 |
| other | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 1 | 23 |

### ollama:qwen2.5:7b（测试集）

| gold \ predicted | blocked | max_days | max_hours | lunch | in_person | p_fewer_days | p_less_waiting | p_no_early_late | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocked | 59 | 0 | 1 | 0 | 0 | 0 | 0 | 3 | 1 |
| max_days | 1 | 12 | 0 | 0 | 0 | 2 | 0 | 0 | 0 |
| max_hours | 0 | 0 | 11 | 0 | 0 | 0 | 0 | 0 | 0 |
| lunch | 0 | 0 | 0 | 10 | 0 | 0 | 0 | 0 | 0 |
| in_person | 0 | 0 | 0 | 0 | 10 | 0 | 0 | 0 | 0 |
| p_fewer_days | 0 | 0 | 0 | 0 | 0 | 7 | 1 | 0 | 2 |
| p_less_waiting | 0 | 0 | 0 | 0 | 0 | 0 | 11 | 0 | 0 |
| p_no_early_late | 1 | 0 | 1 | 1 | 0 | 0 | 0 | 14 | 0 |
| other | 0 | 0 | 0 | 0 | 2 | 1 | 7 | 3 | 13 |
