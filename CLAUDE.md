# UniPlan（ENGG2112 "AI for Good" 小组项目）

和用户用中文交流，语言要简单。期末报告 2026-11-01 截止，个人问答 2026-11-06。

## 做的是什么
帮学生排课表的网页。学生选课并用一句话说出自己的情况，系统排出所有不冲突的课表，挑出最适合他的 3 份并说明理由。

```
一句话 --① 解析--> 条件 --② 排课--> 10–20 份候选 --③ 打分排序--> 前 3 份 --④ 解释--> 理由
```
- ① 需求解析（机器学习 B）：`llm/parse/`
- ② 排课：确定的算法（回溯搜索 + 帕累托筛选），复用 `uniplan/schedule.py` 的 `FastSearch` 和 `uniplan/arrangement.py`。课表冲突只由程序判断，绝不交给大模型
- ③ 打分排序（机器学习 A，主线）：`llm/rank/`
- ④ 解释：`llm/explain.py`
- 各块之间的接口：`llm/contracts.py`

## 谁改什么（每个窗口只改自己的部分）
| 窗口 | 负责 | 只能改 |
| --- | --- | --- |
| 总控 | 接口、审查、合并 | `llm/contracts.py`、`CLAUDE.md`、`tests/test_contracts.py` |
| 需求解析 | ① | `llm/parse/`、`tests/test_parse*.py` |
| 打分排序 | ③ | `llm/rank/`、`tests/test_rank*.py` |
| 系统集成 | ②④和网页 | `uniplan/`、`llm/explain.py`、`main.py`、`tests/` 里与 uniplan 相关的测试 |

接口要改时，先在总控窗口里提出，不要自己改 `llm/contracts.py`。

## 规则
- 每个窗口在自己的工作树和分支上工作。做完一段就跑测试再提交：`python3 -m unittest discover -s tests`，`tests/test_contracts.py` 必须一直通过。
- 只用 Python 标准库写 `uniplan/`。`llm/` 里需要的额外包装在 `/Users/handongrui/Desktop/ENGG2112/.venv-llm`（已有 `mlx-lm`）；要装新包先问用户。
- 本地模型通过 Ollama 调用，统一用 `llm/ollama.py`。已下载：`qwen2.5:0.5b`、`1.5b`、`3b`、`7b`。服务地址由环境变量 `UNIPLAN_OLLAMA_URL` 决定，默认本机，也可以指向局域网里的另一台电脑。
- **算力分工**：用户另有一台 Windows 笔记本（RTX 4090 Laptop，16GB 显存），在局域网里跑 Ollama，专门承担大模型批量推理（7B/14B 打标签、批量评估）。地址由总控窗口写在 `~/.config/uniplan/ollama_url`，`llm/ollama.py` 会自动读取；连不上时自动退回本机并打印提示，这时要告诉用户。`python3 -m llm.ollama` 可以查看当前用的是哪台机器、有哪些模型。大活一律通过 `llm/ollama.py` 调用，不要自己写死 127.0.0.1。
- **GPU 排队**：每台机器的 GPU 同一时间只跑一个大活。凡是批量调用大模型（超过 20 次请求）都要套锁：`python3 -m llm.gpu_lock -- <命令>`，它会自动锁住 `llm/ollama.py` 当前使用的那台机器。Mac 上的 MLX 训练用 `--target mac`。`python3 -m llm.gpu_lock --status` 可以查看谁在用。
- **Windows 上的 LoRA 训练和换模型测速由总控排时间**：要用之前先告诉总控，总控会先让各窗口暂停。
- **一次只用一个模型**：同一批任务里不要在 7B 和 14B 之间交替调用（两个模型同时常驻会占满 16GB 显存）。并发最多 2 路。
- **运行时只用标准库**：网页实际调用的 `parse()`、`rank()`、`explain()` 只能依赖 Python 标准库和 Ollama 的 HTTP 接口（比如逻辑回归权重存成 JSON，用纯 Python 计算；微调后的模型导入 Ollama 再调用）。训练和评估脚本可以用 `.venv-llm` 或 `/usr/local/bin/python3`（自带 scikit-learn 1.6.1）里的包。
- 数据要诚实：大模型生成的标签和句子必须在代码、输出和报告里注明是合成的，不能说成真实学生的数据。
- 没有组员参与，也没有真人数据（用户 2026-10-17 定）。测试和核对都用和千问不同的模型来做，以保持独立：
  需求解析的测试集是 `llm/parse/data/test_claude.csv`，由 Claude 撰写，已定稿；打分排序的核对题由总控窗口（Claude）作为第二位标注者来答。
  报告里必须写明这些都是 AI 产出，不是真实学生。测试集训练前定好，之后不改，不能用来调参。
- 要用到大模型的结果都可复现：写成脚本，固定随机种子，输出存到各自的 `output/` 里。
- 课程资料在 `ENGG2112 课程资料 Course Materials/`（不进仓库）。作业要求见其中 `04 作业与评估 Assessments/06 期末报告 Final Report.html`。
