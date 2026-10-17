"""One heavy job per GPU at a time: batch LLM calls, LoRA training.

Every worktree on this Mac shares the same lock files, so a second job waits instead
of fighting the first for GPU memory. There is one lock per machine:

    python3 -m llm.gpu_lock -- python3 -m llm.rank.label --pairs 1500     # whichever machine
                                                                          # llm/ollama.py uses
    python3 -m llm.gpu_lock --target mac -- <mlx training command>        # this Mac's GPU
    python3 -m llm.gpu_lock --status                                      # who holds what
"""
from __future__ import annotations

import fcntl
import subprocess
import sys
import time
from contextlib import contextmanager
from urllib.parse import urlparse

LOCKS = {"mac": "/tmp/uniplan-gpu.lock", "windows": "/tmp/uniplan-gpu-windows.lock"}


def target_of_ollama() -> str:
    """Batch LLM jobs lock the machine that llm/ollama.py actually talks to."""
    from llm.ollama import base_url
    return "mac" if urlparse(base_url()).hostname in ("127.0.0.1", "localhost") else "windows"


@contextmanager
def gpu_lock(label: str = "", target: str = "mac"):
    with open(LOCKS[target], "a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.seek(0)
            print(f"{target} GPU busy ({handle.read().strip() or 'another job'}); waiting...",
                  file=sys.stderr, flush=True)
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


def status() -> None:
    for target, path in LOCKS.items():
        try:
            with open(path, "a+") as handle:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(handle, fcntl.LOCK_UN)
                    print(f"{target}: free")
                except BlockingIOError:
                    handle.seek(0)
                    print(f"{target}: busy - {handle.read().strip()}")
        except OSError as error:
            print(f"{target}: {error}")


def main(argv: list[str]) -> int:
    if argv[:1] == ["--status"]:
        status()
        return 0
    if "--" not in argv:
        print("usage: python3 -m llm.gpu_lock [--target mac|windows] -- <command...>", file=sys.stderr)
        return 2
    options, command = argv[:argv.index("--")], argv[argv.index("--") + 1:]
    target = options[options.index("--target") + 1] if "--target" in options else target_of_ollama()
    if target not in LOCKS:
        print(f"unknown target {target!r}; use one of {', '.join(LOCKS)}", file=sys.stderr)
        return 2
    with gpu_lock(" ".join(command)[:80], target):
        return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
