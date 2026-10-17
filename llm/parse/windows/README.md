# 在 Windows 4090 上微调千问 7B（QLoRA）

把 Qwen2.5-7B-Instruct 微调成"短句 → 9 类"分类器，转成 GGUF，导入 Windows 上的 Ollama，模型名 `uniplan-parse-7b`。Mac 通过 Ollama 的 HTTP 接口调用和评估，不用把模型拷回来。

**开训时间由总控窗口安排。** 开训前 Windows 上的其他大模型任务要停下，并先卸载 Ollama 里常驻的 7B（第 3 步第一行）。

## 数据和设置（写报告用）

- **训练数据**：`data/train.jsonl` 和 `data/valid.jsonl`。来源有两种，都不是真实学生的数据：
  - 千问 2.5 7B 按事先定好的类别生成的合成短句（`python3 -m llm.parse.generate`，种子 2112），按生成请求划分训练和验证；
  - Claude 写的边界难题（`llm/parse/data/train_claude.csv`），按句子编号固定种子分 85/15。
  - 标签：每一轮判卷里 Claude 看过的短句用 Claude 的标签，没看过的沿用生成时的类别。每轮的数量和改动数记在 `llm/parse/output/review_round<N>_stats.json`。
  - 测试集 `test_claude.csv` 不参与训练和选轮；题目池里和测试句字符相似度 ≥ 0.85 的短句已删掉。
- **方法**：QLoRA。底模 4 位 NF4（双重量化），计算用 bf16；LoRA r=16、alpha=32、dropout 0.05，作用于全部注意力和 MLP 投影层；梯度检查点。
- **超参数**：AdamW，学习率 2e-4，余弦衰减，5% 预热；batch 16；3 轮；只对答案部分算损失；随机种子 2112。提示词是 `llm/parse/labels.py` 的 `SHORT_SYSTEM`，答案就是类别名。
- **选轮**：每轮结束在验证集上算准确率，保留最好的一轮。
- **显存和时长（估计）**：训练峰值约 9–11 GB；训练约 15–25 分钟；首次下载底模约 15 GB；合并和转 GGUF 约 15 分钟，合并时要约 16 GB 内存（见第 3 步）。实际的峰值显存、每轮损失、验证准确率和用时都记在 `out-7b/train_log.json`。
- **硬盘**：底模 15 GB + 合并后 15 GB + GGUF 15 GB，约 45 GB；导入 Ollama 后后两个可以删。

## 1. 拷文件夹

把 Mac 上的 `llm/parse/windows` 整个拷到 Windows。压缩包自带 `windows` 这一层，解压到 `D:\uniplan-lora` 后，工作目录是 `D:\uniplan-lora\windows`，里面应有 `train_lora.py`、`merge_adapter.py`、`README.md`、`data\train.jsonl`、`data\valid.jsonl`。下面的命令都在这个目录里运行。

## 2. 环境（已装好，2026-10-17）

训练环境 `.venv`：torch 2.6.0+cu124、transformers 5.20.1、peft 0.21.2、bitsandbytes 0.50.2。从零装的话：

```powershell
cd D:\uniplan-lora\windows
python -m venv .venv
.venv\Scripts\activate
pip install torch --index-url https://download.pytorch.org/whl/cu124
pip install transformers peft accelerate bitsandbytes safetensors
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

最后一行应打印 `True` 和显卡名字。打印 `False` 说明装成了 CPU 版的 torch，换一个 `cu12x` 的地址重装。

底模放在 `D:\hf-cache`。每次打开新的 PowerShell 都要先设好，训练和合并都靠它找到底模：

```powershell
$env:HF_HOME = "D:\hf-cache"
```

想先把底模下好（约 15 GB），可以用新版的 `hf` 命令（旧名 `huggingface-cli` 已改名）：

```powershell
hf download Qwen/Qwen2.5-7B-Instruct
```

## 3. 训练

```powershell
cd D:\uniplan-lora\windows
.venv\Scripts\activate
$env:HF_HOME = "D:\hf-cache"
curl.exe http://127.0.0.1:11434/api/generate -d '{\"model\": \"qwen2.5:7b\", \"keep_alive\": 0}'
python train_lora.py
```

`curl.exe` 那行让 Ollama 卸载常驻的 7B，空出显存。训练时每轮打印一次 `val_accuracy`，训完先存好 `out-7b\adapter` 和 `out-7b\train_log.json`，再在 CPU 上合并，生成 `out-7b\merged` 和 `out-7b\Modelfile`。

**合并要约 16 GB 内存，这台机器平时只空闲 8–11 GB。** 开训前先关掉浏览器、游戏、IDE 等占内存的大程序。如果训练跑完了、合并时内存不够报错，适配器已经存好，不用重训：关掉程序后运行

```powershell
python merge_adapter.py
```

## 4. 转成 GGUF 并导入 Ollama

llama.cpp 的转换依赖写死了 CPU 版 torch，装进训练用的 `.venv` 会把 CUDA 版换掉，所以要单独建一个 `.venv-convert`（只做一次）：

```powershell
git clone --depth 1 https://github.com/ggml-org/llama.cpp
python -m venv .venv-convert
.venv-convert\Scripts\python.exe -m pip install -r llama.cpp\requirements\requirements-convert_hf_to_gguf.txt
```

然后转换、导入、试一句：

```powershell
.venv-convert\Scripts\python.exe llama.cpp\convert_hf_to_gguf.py out-7b\merged --outfile out-7b\model-f16.gguf --outtype f16
cd out-7b
ollama create uniplan-parse-7b -f Modelfile --quantize q4_K_M
ollama run uniplan-parse-7b "I can't do Fridays, I work"
```

最后一行应只回答一个类别名（这句应是 `blocked_time`）。量化成 q4_K_M 后大小和原来的 `qwen2.5:7b` 一样，约 4.7 GB。确认能用后，`out-7b\merged` 和 `out-7b\model-f16.gguf` 可以删掉。

## 5. 告诉 Claude

把 `out-7b\train_log.json` 拷回 Mac，放到 `llm/parse/output/lora_train_log_7b.json`，然后在需求解析窗口说一声"微调好了"。Claude 会用 `python3 -m llm.ollama` 确认 Windows 上有 `uniplan-parse-7b`，再跑评估。
