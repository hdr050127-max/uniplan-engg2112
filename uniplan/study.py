"""Comparison sessions: serve sampled pairs, collect answers, return a learned ranking.

Sessions live in memory only. Answers are written to disk solely when the
student consented on the form that produced the study.
"""

from __future__ import annotations

import secrets
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from threading import Lock
from typing import Any, Callable

from .arrangement import attach_alternatives, candidate_from_ids
from .preference import (AXES, MODEL_SPEC, StudyDesign, design_study, evaluate_design,
                         interpret, pool_spread, rank_by_utility, vector, weight_prior)
from .ranking import EQUAL_WEIGHTS, dated_meetings, feature_key, top_profiles
from .schedule import ClassOption, eligible_options


CHOICES = {"left": "A", "right": "B", "tie": "tie"}


class StudyError(ValueError):
    """The comparison answers cannot be accepted."""


@dataclass
class StudySession:
    study_id: str
    design: StudyDesign
    pool: list[dict[str, Any]]
    options: dict[str, ClassOption]
    profile: dict[str, Any]
    teaching_weeks: tuple[date, ...]
    baseline_top: list[tuple[float, float, float]]
    consented: bool
    created: float
    answers: dict[int, str] = field(default_factory=dict)


def _candidate(entry: dict[str, Any], options: dict[str, ClassOption]) -> Candidate:
    return candidate_from_ids(entry["candidate_id"], entry["option_ids"], options)


def schedule_card(entry: dict[str, Any], options: dict[str, ClassOption]) -> dict[str, Any]:
    """What a student needs to judge a schedule: G/D/O and its weekly slots."""
    slots: Counter[tuple[int, int, int, str, str, bool]] = Counter()
    for meeting in _candidate(entry, options).meetings:
        slots[(meeting.date.isoweekday(), meeting.start_min, meeting.end_min,
               meeting.unit_code, meeting.group_id.rpartition("|")[2], meeting.is_online)] += 1
    return {
        "features": entry["features"],
        "slots": [{"weekday": weekday, "start_min": start, "end_min": end,
                   "unit_code": unit, "activity": activity, "online": online, "weeks": weeks}
                  for (weekday, start, end, unit, activity, online), weeks in sorted(slots.items())],
    }


class StudyRegistry:
    def __init__(self, *, ttl_seconds: float = 7200, capacity: int = 256,
                 clock: Callable[[], float] = time.monotonic,
                 seed_source: Callable[[], int] = lambda: secrets.randbits(32)):
        self.ttl_seconds = ttl_seconds
        self.capacity = capacity
        self.clock = clock
        self.seed_source = seed_source
        self._sessions: dict[str, StudySession] = {}
        self._lock = Lock()

    def _evict(self) -> None:
        now = self.clock()
        for study_id in [key for key, item in self._sessions.items()
                         if now - item.created > self.ttl_seconds]:
            del self._sessions[study_id]
        while len(self._sessions) >= self.capacity:
            del self._sessions[min(self._sessions, key=lambda key: self._sessions[key].created)]

    def create(self, *, profile: dict[str, Any], ranking: dict[str, Any],
               pool: list[dict[str, Any]], options: dict[str, ClassOption],
               consented: bool) -> dict[str, Any]:
        """Design a comparison study, or say why the rule baseline must be used."""
        design = design_study(pool, self.seed_source())
        if design is None:
            return {"available": False,
                    "reason": f"只有 {len(pool)} 种不同特征的可行课表，少于比较所需的 5 种；请直接参考规则排序。"}
        session = StudySession(
            study_id=secrets.token_hex(16), design=design, pool=pool, options=options,
            profile=profile,
            teaching_weeks=tuple(date.fromisoformat(week) for week in ranking["teaching_weeks"]),
            baseline_top=top_profiles(pool, profile["weights"]),
            consented=consented, created=self.clock(),
        )
        with self._lock:
            self._evict()
            self._sessions[session.study_id] = session
        return {
            "available": True,
            "study_id": session.study_id,
            "complete_design": design.complete,
            "schedules": [schedule_card(entry, options) for entry in design.schedules],
            "pairs": [{"pair_id": pair.pair_id, "left": pair.left, "right": pair.right}
                      for pair in design.pairs],
        }

    def get(self, study_id: str) -> StudySession | None:
        with self._lock:
            session = self._sessions.get(study_id)
            if session and self.clock() - session.created > self.ttl_seconds:
                del self._sessions[study_id]
                return None
            return session

    def submit(self, study_id: str, raw_answers: Any) -> tuple[StudySession, dict[str, Any]]:
        session = self.get(study_id)
        if session is None:
            raise StudyError("比较会话已过期，请重新生成课表后再比较。")
        design = session.design
        if not isinstance(raw_answers, list) or len(raw_answers) != len(design.pairs):
            raise StudyError("请完成全部比较后再提交。")
        answers: dict[int, str] = {}
        for item in raw_answers:
            if (not isinstance(item, dict) or not isinstance(item.get("pair_id"), int) or
                    isinstance(item.get("pair_id"), bool) or item.get("choice") not in CHOICES or
                    not 0 <= item["pair_id"] < len(design.pairs) or item["pair_id"] in answers):
                raise StudyError("比较答案格式无效。")
            answers[item["pair_id"]] = CHOICES[item["choice"]]
        session.answers = answers
        return session, self._result(session)

    def _result(self, session: StudySession) -> dict[str, Any]:
        report = evaluate_design(
            session.design, session.answers, session.profile["weights"],
            scale=pool_spread(session.pool), c=MODEL_SPEC["c"],
            prior=weight_prior(EQUAL_WEIGHTS, MODEL_SPEC["prior_strength"]),
        )
        result: dict[str, Any] = {"evaluation": {k: v for k, v in report.items() if k != "beta"}}
        if report["status"] != "learned":
            result["status"] = "insufficient"
            result["message"] = (f"非“差不多”的训练比较少于 {report['required_train_responses']} 组，"
                                 "无法可靠学习偏好；请参考规则排序。")
            return result
        beta = report["beta"]
        meaning = interpret(beta)
        result["model"] = {"coefficients": dict(zip(AXES, beta)), "spec": MODEL_SPEC, **meaning}
        if not meaning["informative"]:
            result["status"] = "insufficient"
            result["message"] = "你的选择没有显示一致的取舍方向；请参考规则排序。"
            return result
        result["status"] = "learned"
        top = rank_by_utility(session.pool, beta)
        eligible = dict(eligible_options(
            [(group_id, tuple(option for option in session.options.values()
                              if option.group_id == group_id))
             for group_id in sorted({option.group_id for option in session.options.values()})],
            session.profile,
        ))
        items = []
        for rank, entry in enumerate(top, start=1):
            x = vector(entry["features"])
            item = {
                "rank": rank,
                "candidate_id": entry["candidate_id"],
                "option_ids": list(entry["option_ids"]),
                "features": entry["features"],
                "utility": entry["utility"],
                "contributions": {axis: coef * value for axis, coef, value in zip(AXES, beta, x)},
                "equivalent_count": entry["count"],
                "meetings": dated_meetings(_candidate(entry, session.options), session.profile),
            }
            attach_alternatives(item, eligible, session.options, session.profile,
                                session.teaching_weeks)
            items.append(item)
        result["top"] = items
        learned_keys = {feature_key(entry["features"]) for entry in top}
        result["baseline_overlap"] = len(learned_keys & set(session.baseline_top))
        return result

    @staticmethod
    def answer_rows(session: StudySession) -> list[dict[str, Any]]:
        """The proposal's `choices` records, for consented storage only."""
        rows = []
        for pair in session.design.pairs:
            if pair.pair_id not in session.answers:
                continue
            left, right = session.design.schedules[pair.left], session.design.schedules[pair.right]
            rows.append({
                "pair_index": pair.pair_id, "split": pair.split,
                "candidate_a": left["candidate_id"], "candidate_b": right["candidate_id"],
                "x_a": list(left["x"]), "x_b": list(right["x"]),
                "choice": session.answers[pair.pair_id],
            })
        return rows
