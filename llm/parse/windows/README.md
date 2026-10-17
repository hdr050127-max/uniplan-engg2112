# 在 Windows 4090 上做 LoRA 微调

把千问 0.5B 和 1.5B 用**合成**短句微调成"短句 → 9 类"分类器，再导入 Windows 上的 Ollama。Mac 那边通过 Ollama 的 HTTP 接口直接调用和评估，不用把模型拷回来。

整个过程大约 30 分钟，大部分时间在下载模型（0.5B 约 1 GB，1.5B 约 3 GB）。开训时间由总控窗口安排，开训前 Windows 上的其他大模型任务要先停下。

## 数据和设置（写报告用）

- **训练数据是合成的**：`data/train.jsonl`（1,509 条）和 `data/valid.jsonl`（272 条）由千问 2.5 7B 按事先定好的类别生成（`python3 -m llm.parse.generate`，种子 2112），再经规则过滤去重，不是真实学生的数据。按生成请求划分训练/验证，两边没有同一请求里的近似句。
- **提示词**：短提示（`llm/parse/labels.py` 的 `SHORT_SYSTEM`），答案就是类别名。
- **超参数**：LoRA r=16、alpha=32、dropout 0.05，作用于全部注意力和 MLP 投影层；bf16；AdamW，学习率 2e-4，余弦衰减，5% 预热；batch 16；3 轮；只对答案部分算损失；随机种子 2112。
- **选轮**：每轮结束在合成验证集上算准确率，保留最好的一轮。测试集（`test_claude.csv`）不参与训练和选轮。
- **显存和时间（估计）**：0.5B 约 3–4 GB、几分钟；1.5B 约 6–8 GB、约 10 分钟。
- 实际用到的版本、显卡、每轮损失和验证准确率都记在 `out-*/train_log.json`。

## 1. 拷文件夹

把 Mac 上的 `llm/parse/windows` 整个文件夹拷到 Windows，例如 `D:\uniplan-lora`。里面应该有：

```
train_lora.py
README.md
data\train.jsonl
data\valid.jsonl
```

## 2. 装环境（只做一次）

在 PowerShell 里：

```powershell
cd D:\uniplan-lora
python -m venv .venv
.venv\Scripts\activate
pip install torch --index-url https://download.pytorch.org/whl/cu124
pip install transformers peft accelerate safetensors
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

最后一行应打印 `True` 和显卡名字。打印 `False` 说明装成了 CPU 版的 torch，换一个 `cu12x` 的地址重装。

## 3. 训练并导入 Ollama

```powershell
python train_lora.py --base Qwen/Qwen2.5-0.5B-Instruct --out out-0.5b
ollama create uniplan-parse-0.5b -f out-0.5b\Modelfile

python train_lora.py --base Qwen/Qwen2.5-1.5B-Instruct --out out-1.5b
ollama create uniplan-parse-1.5b -f out-1.5b\Modelfile
```

每训完一轮会打印 `val_accuracy`（合成验证集上的准确率），结束时保留最好的一轮。

如果 `ollama create` 报错说不支持这种模型结构，改走 GGUF：

```powershell
git clone https://github.com/ggml-org/llama.cpp
pip install -r llama.cpp\requirements\requirements-convert_hf_to_gguf.txt
python llama.cpp\convert_hf_to_gguf.py out-0.5b\merged --outfile out-0.5b\model.gguf --outtype q8_0
```

再把 `out-0.5b\Modelfile` 第一行改成 `FROM ./model.gguf`，重新 `ollama create`。

## 4. 告诉 Claude

把 `out-0.5b\train_log.json` 和 `out-1.5b\train_log.json` 拷回 Mac，放到 `llm/parse/output/`，分别改名为 `lora_train_log_0.5b.json`、`lora_train_log_1.5b.json`，然后在需求解析窗口说一声"微调好了"。Claude 会用 `python3 -m llm.ollama` 确认 Windows 上两个模型都在，再跑评估。

`out-*` 文件夹里的权重不用拷回来，也不进仓库。
