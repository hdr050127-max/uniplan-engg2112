# 在 Windows 4090 上做 LoRA 微调

把千问 0.5B 和 1.5B 用**合成**短句微调成"短句 → 9 类"分类器，再导入 Windows 上的 Ollama。Mac 那边通过 Ollama 的 HTTP 接口直接调用和评估，不用把模型拷回来。

整个过程大约 30 分钟，大部分时间在下载模型（0.5B 约 1 GB，1.5B 约 3 GB）。

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
