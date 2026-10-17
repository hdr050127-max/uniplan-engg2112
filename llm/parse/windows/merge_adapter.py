"""Merge an already trained adapter into the base model and write the Modelfile, without training again.

Use it when train_lora.py finished training (out-7b/adapter and out-7b/train_log.json exist) but ran
out of memory while merging. Close large programs first: the merge needs about 16 GB of RAM.

    python merge_adapter.py
"""
from __future__ import annotations

import argparse

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

from train_lora import CHAT_TEMPLATE, HERE, rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge out-7b/adapter into the base model.")
    parser.add_argument("--base", default="Qwen/Qwen2.5-7B-Instruct")
    parser.add_argument("--out", default="out-7b")
    args = parser.parse_args()
    out = HERE / args.out
    base = AutoModelForCausalLM.from_pretrained(args.base, dtype=torch.bfloat16)
    merged = PeftModel.from_pretrained(base, out / "adapter").merge_and_unload()
    merged.save_pretrained(out / "merged", safe_serialization=True)
    AutoTokenizer.from_pretrained(args.base).save_pretrained(out / "merged")
    system = rows(HERE / "data" / "valid.jsonl")[0][0]["content"]
    (out / "Modelfile").write_text(
        f'FROM ./model-f16.gguf\nTEMPLATE """{CHAT_TEMPLATE}"""\nSYSTEM """{system}"""\n'
        "PARAMETER stop <|im_end|>\nPARAMETER temperature 0\n", encoding="utf-8")
    print(f"merged into {out / 'merged'}; next: convert to GGUF (README.md step 4)")


if __name__ == "__main__":
    main()
