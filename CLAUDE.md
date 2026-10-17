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
- 这台 Mac 只有一块 GPU、16GB 内存。凡是大活（7B 批量打标签、LoRA 微调）都要套上锁，排队执行：`python3 -m llm.gpu_lock -- <命令>`。
- 数据要诚实：大模型生成的标签和句子必须在代码、输出和报告里注明是合成的，不能说成真实学生的数据。测试集由组员亲手写，训练之前定好，之后不改。
- 要用到大模型的结果都可复现：写成脚本，固定随机种子，输出存到各自的 `output/` 里。
- 课程资料在 `ENGG2112 课程资料 Course Materials/`（不进仓库）。作业要求见其中 `04 作业与评估 Assessments/06 期末报告 Final Report.html`。
