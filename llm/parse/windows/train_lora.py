"""QLoRA fine-tuning of Qwen2.5-7B-Instruct on the UniPlan clause labels, on a CUDA GPU (the Windows 4090).

Self-contained: needs torch (CUDA), transformers, peft, bitsandbytes and accelerate, plus the
data/ folder next to this file. See README.md in this folder for every command.

    python train_lora.py                      # trains, keeps the best epoch, merges, writes out-7b/
    (then convert to GGUF and `ollama create uniplan-parse-7b`, see README.md)

Training data: clauses written by qwen2.5:7b for labels chosen in advance (synthetic) plus hard
clauses written by Claude; every label that a review round looked at is Claude's. None of it is
real student data. The best epoch is picked on the validation split; test_claude.csv is never used.
"""
from __future__ import annotations

import argparse
import json
import platform
import random
import time
from pathlib import Path

import peft
import torch
import transformers
from peft import LoraConfig, PeftModel, get_peft_model, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, get_cosine_schedule_with_warmup

HERE = Path(__file__).resolve().parent
SEED = 2112
# Same layout as Qwen2.5's own chat template (system, user, then the assistant's turn).
CHAT_TEMPLATE = '''{{- if .System }}<|im_start|>system
{{ .System }}<|im_end|>
{{ end }}{{- range .Messages }}{{- if ne .Role "system" }}<|im_start|>{{ .Role }}
{{ .Content }}<|im_end|>
{{ end }}{{- end }}<|im_start|>assistant
'''


def rows(path: Path) -> list[list[dict]]:
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line)["messages"] for line in handle if line.strip()]


def encode(tokenizer, messages: list[dict]) -> tuple[list[int], list[int]]:
    """Token ids and labels; only the answer (the label and the end token) is learnt."""
    prompt = tokenizer.apply_chat_template(messages[:-1], add_generation_prompt=True, tokenize=False)
    prompt_ids = tokenizer(prompt, add_special_tokens=False).input_ids
    answer_ids = tokenizer(messages[-1]["content"] + "<|im_end|>", add_special_tokens=False).input_ids
    return prompt_ids + answer_ids, [-100] * len(prompt_ids) + answer_ids


def batches(examples, size, pad_id):
    order = list(range(len(examples)))
    random.shuffle(order)
    for start in range(0, len(order), size):
        chunk = [examples[i] for i in order[start:start + size]]
        width = max(len(ids) for ids, _ in chunk)
        yield (torch.tensor([i + [pad_id] * (width - len(i)) for i, _ in chunk]),
               torch.tensor([l + [-100] * (width - len(l)) for _, l in chunk]),
               torch.tensor([[1] * len(i) + [0] * (width - len(i)) for i, _ in chunk]))


@torch.no_grad()
def accuracy(model, tokenizer, data: list[list[dict]], batch_size: int = 32) -> float:
    model.eval()
    tokenizer.padding_side = "left"
    right = 0
    for start in range(0, len(data), batch_size):
        chunk = data[start:start + batch_size]
        prompts = [tokenizer.apply_chat_template(m[:-1], add_generation_prompt=True, tokenize=False) for m in chunk]
        inputs = tokenizer(prompts, return_tensors="pt", padding=True, add_special_tokens=False).to(model.device)
        output = model.generate(**inputs, max_new_tokens=8, do_sample=False, use_cache=True,
                                pad_token_id=tokenizer.pad_token_id)
        for messages, ids in zip(chunk, output[:, inputs.input_ids.shape[1]:]):
            right += tokenizer.decode(ids, skip_special_tokens=True).strip() == messages[-1]["content"]
    tokenizer.padding_side = "right"
    model.train()
    return right / len(data)


def main() -> None:
    parser = argparse.ArgumentParser(description="QLoRA fine-tune Qwen2.5-7B on the UniPlan clause labels.")
    parser.add_argument("--base", default="Qwen/Qwen2.5-7B-Instruct")
    parser.add_argument("--out", default="out-7b")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--rank", type=int, default=16)
    args = parser.parse_args()

    random.seed(SEED)
    torch.manual_seed(SEED)
    out = HERE / args.out
    out.mkdir(parents=True, exist_ok=True)
    assert torch.cuda.is_available(), "no CUDA GPU found; install the CUDA build of torch (see README.md)"

    tokenizer = AutoTokenizer.from_pretrained(args.base)
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
                               bnb_4bit_compute_dtype=torch.bfloat16)
    model = AutoModelForCausalLM.from_pretrained(args.base, quantization_config=quant, device_map={"": 0},
                                                 torch_dtype=torch.bfloat16)
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    model.config.use_cache = False
    model = get_peft_model(model, LoraConfig(
        r=args.rank, lora_alpha=2 * args.rank, lora_dropout=0.05, task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]))
    model.print_trainable_parameters()

    train, valid = rows(HERE / "data" / "train.jsonl"), rows(HERE / "data" / "valid.jsonl")
    examples = [encode(tokenizer, messages) for messages in train]
    steps = args.epochs * -(-len(examples) // args.batch)
    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=args.lr)
    schedule = get_cosine_schedule_with_warmup(optimizer, int(0.05 * steps), steps)

    log = {"base": args.base, "method": "QLoRA (4-bit NF4 base, bf16 compute, LoRA adapters)", "seed": SEED,
           "settings": vars(args), "gpu": torch.cuda.get_device_name(0), "python": platform.python_version(),
           "torch": torch.__version__, "transformers": transformers.__version__, "peft": peft.__version__,
           "train_examples": len(train), "valid_examples": len(valid), "epochs": [],
           "data": "synthetic clauses (qwen2.5:7b) + Claude-written hard clauses; labels checked by Claude "
                   "where reviewed; not real student data"}
    best = -1.0
    started = time.time()
    torch.cuda.reset_peak_memory_stats()
    model.train()
    for epoch in range(1, args.epochs + 1):
        losses = []
        for ids, labels, mask in batches(examples, args.batch, tokenizer.pad_token_id):
            loss = model(input_ids=ids.cuda(), attention_mask=mask.cuda(), labels=labels.cuda()).loss
            loss.backward()
            optimizer.step()
            schedule.step()
            optimizer.zero_grad()
            losses.append(loss.item())
        val = accuracy(model, tokenizer, valid)
        log["epochs"].append({"epoch": epoch, "train_loss": round(sum(losses) / len(losses), 4),
                              "val_accuracy": round(val, 4), "minutes": round((time.time() - started) / 60, 1)})
        print(log["epochs"][-1], flush=True)
        if val > best:
            best = val
            model.save_pretrained(out / "adapter")
            log["best_epoch"] = epoch
    log["best_val_accuracy"] = round(best, 4)
    log["peak_gpu_memory_gb"] = round(torch.cuda.max_memory_allocated() / 1e9, 1)
    log["training_minutes"] = round((time.time() - started) / 60, 1)
    (out / "train_log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")

    # Merge the best adapter into the full-precision base on the CPU (about 16 GB of RAM), for GGUF export.
    del model
    torch.cuda.empty_cache()
    base = AutoModelForCausalLM.from_pretrained(args.base, torch_dtype=torch.bfloat16, low_cpu_mem_usage=True)
    merged = PeftModel.from_pretrained(base, out / "adapter").merge_and_unload()
    merged.save_pretrained(out / "merged", safe_serialization=True)
    tokenizer.save_pretrained(out / "merged")
    system = rows(HERE / "data" / "valid.jsonl")[0][0]["content"]
    (out / "Modelfile").write_text(
        f'FROM ./model-f16.gguf\nTEMPLATE """{CHAT_TEMPLATE}"""\nSYSTEM """{system}"""\n'
        "PARAMETER stop <|im_end|>\nPARAMETER temperature 0\n", encoding="utf-8")
    print(f"done: best val accuracy {best:.3f} (epoch {log['best_epoch']}), "
          f"peak GPU memory {log['peak_gpu_memory_gb']} GB; next: convert to GGUF (README.md step 4)")


if __name__ == "__main__":
    main()
