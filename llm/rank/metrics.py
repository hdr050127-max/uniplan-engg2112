"""Scoring a ranking against the teacher's round robin (standard library only)."""
from __future__ import annotations


def teacher_order(rows: list[dict], ids: list[str]) -> dict[str, float]:
    """Copeland points from the round robin: a win is 1, a tie or a flip is 1/2 each."""
    points = {i: 0.0 for i in ids}
    for r in rows:
        if r["a_id"] not in points or r["b_id"] not in points:
            continue
        if r["label"] in ("A", "B"):
            points[r["a_id"] if r["label"] == "A" else r["b_id"]] += 1
        else:
            points[r["a_id"]] += 0.5
            points[r["b_id"]] += 0.5
    return points


def membership(points: dict[str, float], k: int = 3) -> dict[str, float]:
    """Share of a top-k place each candidate holds; ties at the cut share the remaining places."""
    ordered = sorted(points.values(), reverse=True)
    cut = ordered[k - 1] if len(ordered) >= k else min(ordered)
    above = [i for i, v in points.items() if v > cut]
    at = [i for i, v in points.items() if v == cut]
    share = (k - len(above)) / len(at) if at else 0.0
    return {i: 1.0 if v > cut else share if v == cut else 0.0 for i, v in points.items()}
