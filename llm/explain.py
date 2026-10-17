"""Block 4 (integration window): one plain-language reason per recommended timetable.

Placeholder: a sentence built from the numbers. The integration window may switch it to a
local Qwen call (llm.ollama.chat) and must keep this template as the fallback.
"""
from __future__ import annotations

from llm.contracts import Candidate, Conditions


def explain(student_text: str, conditions: Conditions, picks: list[Candidate]) -> list[str]:
    reasons = []
    for pick in picks:
        f = pick["features"]
        reasons.append(f"每周到校 {f['campus_days']:.1f} 天，课间空等 {f['gap_min'] / 60:.1f} 小时，"
                       f"偏好时段外的课 {f['outside_min']:.0f} 分钟。")
    return reasons
