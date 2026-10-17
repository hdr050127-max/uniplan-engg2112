"""One heavy GPU job at a time on this Mac (7B labelling, LoRA training).

Every worktree shares the same lock file, so a second job waits instead of
fighting for the 16 GB of memory:

    python3 -m llm.gpu_lock -- python3 -m llm.rank.label --pairs 1500
"""
from __future__ import annotations

import fcntl
import subprocess
import sys
import time
from contextlib import contextmanager

LOCK_PATH = "/tmp/uniplan-gpu.lock"


@contextmanager
def gpu_lock(label: str = ""):
    with open(LOCK_PATH, "a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.seek(0)
            print(f"GPU busy ({handle.read().strip() or 'another job'}); waiting...", file=sys.stderr, flush=True)
            fcntl.flock(handle, fcntl.LOCK_EX)
        handle.seek(0)
        handle.truncate()
        handle.write(f"{label} since {time.strftime('%H:%M')}")
        handle.flush()
        try:
            yield
        finally:
            handle.seek(0)
            handle.truncate()
            fcntl.flock(handle, fcntl.LOCK_UN)


def main(argv: list[str]) -> int:
    if "--" not in argv:
        print("usage: python3 -m llm.gpu_lock -- <command...>", file=sys.stderr)
        return 2
    command = argv[argv.index("--") + 1:]
    with gpu_lock(" ".join(command)[:80]):
        return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
