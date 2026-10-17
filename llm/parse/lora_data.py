"""Write the LoRA training data into llm/parse/windows/data/ for train_lora.py.

    python3 -m llm.parse.lora_data

Chat format with the short prompt; the answer is the label. Built from the SYNTHETIC
clauses (train and val splits only), so it is synthetic too.
"""
from __future__ import annotations

import json
from pathlib import Path

from llm.parse.evaluate import synthetic
from llm.parse.labels import short_messages

DATA = Path(__file__).resolve().parent / "windows" / "data"


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    for split, name in (("train", "train"), ("val", "valid")):
        rows = synthetic(split)
        with open(DATA / f"{name}.jsonl", "w", encoding="utf-8") as handle:
            for row in rows:
                chat = short_messages(row["text"]) + [{"role": "assistant", "content": row["label"]}]
                handle.write(json.dumps({"messages": chat}, ensure_ascii=False) + "\n")
        print(f"{name}: {len(rows)} synthetic clauses")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
