"""Top-level pipeline entry: call completed UniPlan modules in order."""

from __future__ import annotations

from typing import Any, Callable

from .arrangement import (arrange_timetables, validate_excluded, validate_group_selection,
                          validate_pins)
from .profile import prepare_student_profile
from .schedule import ScheduleDataError, SearchLimitError
from .store import ProfileStore
from .study import StudyRegistry
from .timetable_data import TimetableData, TimetableDataError, load_timetable_data


def main(
    raw_input: dict[str, Any], snapshot_catalog: Any, *,
    consent_to_save: bool = False,
    store: ProfileStore | None = None,
    module_two: Callable[[dict[str, Any], dict[str, Any]], Any] | None = None,
    selected_groups: dict[str, list[str]] | None = None,
    study_registry: StudyRegistry | None = None,
    participant: str | None = None,
    pins: Any = None,
    excluded: Any = None,
    student_text: str | None = None,
) -> dict[str, Any]:
    """Validate input, read a snapshot, then rank feasible schedules if ready.

    Form and CLI adapters both pass the same raw mapping. Validation never
    persists data. Module two reads the local dated meetings, even when
    unverified activity requirements still block automatic recommendation.
    Explicitly selected groups may be used for a clearly marked trial plan.
    With a study registry, a feasible ranking also returns pairwise
    comparisons for preference learning (module four). With ``student_text``
    (may be empty) a feasible ranking also carries the AI recommendation.
    """
    result = prepare_student_profile(raw_input, snapshot_catalog)
    result["saved"] = False
    result["completed_modules"] = ["student_input"]
    if result["status"] == "invalid":
        return result

    if result["snapshot_ref"] is not None:
        read_snapshot = module_two or (
            lambda profile, ref: load_timetable_data(profile, ref, snapshot_catalog)
        )
        try:
            timetable = read_snapshot(result["profile"], result["snapshot_ref"])
        except TimetableDataError as exc:
            result["status"] = "needs_data"
            result["blockers"].append({"code": "snapshot_invalid", "message": str(exc)})
        else:
            result["module_two_result"] = (
                timetable.summary if isinstance(timetable, TimetableData) else timetable
            )
            result["completed_modules"].append("timetable_data")
            requirements = None
            if selected_groups is not None and isinstance(timetable, TimetableData):
                try:
                    requirements = validate_group_selection(
                        timetable.meetings, result["profile"]["unit_codes"], selected_groups,
                    )
                except ScheduleDataError as exc:
                    result["status"] = "needs_data"
                    result["blockers"].append({"code": "group_selection_invalid", "message": str(exc)})
                else:
                    result["blockers"] = [item for item in result["blockers"] if item["code"] not in {
                        "requirements_unverified", "requirements_invalid", "requirements_mismatch",
                    }]
                    result["group_selection"] = {
                        "mode": "student_selected", "group_ids": requirements,
                    }
                    result["status"] = "needs_data" if result["blockers"] else "ready"
            if result["status"] == "ready" and isinstance(timetable, TimetableData):
                try:
                    if requirements is None:
                        requirements = snapshot_catalog.verified_group_ids(
                            result["profile"], timetable.meetings,
                        )
                    pinned = validate_pins(timetable.meetings, requirements, pins)
                    left_out = validate_excluded(timetable.meetings, requirements, excluded)
                    ranking = arrange_timetables(
                        timetable.meetings, requirements, result["profile"], pins=pinned,
                        excluded=left_out, student_text=student_text,
                    )
                    result["pinned"] = pinned
                    result["excluded"] = left_out
                except (ValueError, ScheduleDataError, SearchLimitError) as exc:
                    result["status"] = "needs_data"
                    result["blockers"].append({"code": "ranking_unavailable", "message": str(exc)})
                else:
                    pool, options = ranking.pop("_pool"), ranking.pop("_options")
                    ranking["basis"] = "student_selected" if selected_groups is not None else "verified"
                    result["ranking_result"] = ranking
                    if study_registry is not None and ranking["feasible_count"]:
                        result["study"] = study_registry.create(
                            profile=result["profile"], ranking=ranking, pool=pool,
                            options=options, consented=consent_to_save and store is not None,
                        )
                    result["completed_modules"].extend([
                        "class_option_extraction", "feasible_schedule_generation", "rule_ranking",
                    ])
                    if ranking["feasible_count"] == 0:
                        result["status"] = "no_feasible"
                        result["blockers"].append({
                            "code": "no_feasible",
                            "message": ranking["no_feasible_reason"],
                        })

    if consent_to_save and store is not None:
        result["participant_id"] = store.save(result["profile"], result["snapshot_ref"], participant)
        result["saved"] = True
    return result
