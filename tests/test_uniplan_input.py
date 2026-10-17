import csv
import json
import tempfile
import unittest
from pathlib import Path

from uniplan.catalog import SnapshotCatalog, load_unit_catalog, suggest_units
from uniplan.main import main
from uniplan.profile import prepare_student_profile
from uniplan.store import ProfileStore
from uniplan.timetable_data import load_timetable_data


ROOT = Path(__file__).resolve().parent.parent


def valid_input(**overrides):
    raw = {
        "year": 2026,
        "session_code": "s2c",
        "unit_codes": ["engg2112"],
        "unavailable_windows": [],
    }
    raw.update(overrides)
    return raw


class FakeCatalog:
    def assess(self, profile):
        return {"snapshot_id": "test"}, [], []

    def resolve_snapshot(self, ref):
        if ref != {"snapshot_id": "test"}:
            return None
        return {
            "snapshot_id": "test", "year": 2026, "session_code": "S2C",
            "unit_codes": ["ENGG2112"], "snapshot_time": "2026-09-24T11:00:00+10:00",
            "source_url": "https://example.edu",
            "rows": [{
                "meeting_id": "m1", "unit_code": "ENGG2112", "year": "2026",
                "session_code": "S2C", "group_id": "ENGG2112|Lecture",
                "option_id": "ENGG2112|Lecture|01", "activity_group": "Lecture",
                "class_code": "01", "date": "2026-08-04", "start_min": "540",
                "end_min": "600", "start_time": "09:00", "end_time": "10:00",
                "status": "available", "available_seats": "4", "building_code": "F07",
            }],
        }

    def verified_group_ids(self, profile, rows):
        return {"ENGG2112": ["ENGG2112|Lecture"]}


class ProfileTests(unittest.TestCase):
    def test_one_to_five_distinct_units_and_defaults(self):
        result = prepare_student_profile(valid_input(unit_codes=[
            "engg2112", "amme1362", "math1061", "phys1001", "info1110",
        ]), FakeCatalog())
        self.assertEqual(result["status"], "ready")
        self.assertEqual(len(result["profile"]["unit_codes"]), 5)
        self.assertEqual(result["profile"]["session_code"], "S2C")
        self.assertEqual(result["profile"]["preferred_hours"], {"start_min": 540, "end_min": 1080})
        self.assertEqual(result["profile"]["transition_min"], 0)
        self.assertAlmostEqual(sum(result["profile"]["weights"].values()), 1)
        six = prepare_student_profile(valid_input(unit_codes=[
            "ENGG2112", "AMME1362", "MATH1061", "PHYS1001", "INFO1110", "COMP2123",
        ]), FakeCatalog())
        self.assertEqual(six["status"], "invalid")
        self.assertIn("unit_count", {error["code"] for error in six["errors"]})
        self.assertEqual(prepare_student_profile(valid_input(unit_codes=[]), FakeCatalog())["status"], "invalid")

    def test_windows_merge_and_invalid_time_rejected(self):
        result = prepare_student_profile(valid_input(unavailable_windows=[
            {"weekday": 1, "start_min": 600, "end_min": 720},
            {"weekday": 1, "start_min": 540, "end_min": 600},
            {"weekday": 3, "start_min": 600, "end_min": 660},
        ]), FakeCatalog())
        self.assertEqual(result["profile"]["unavailable_windows"], [
            {"weekday": 1, "start_min": 540, "end_min": 720},
            {"weekday": 3, "start_min": 600, "end_min": 660},
        ])
        bad = prepare_student_profile(valid_input(unavailable_windows=[
            {"weekday": 1, "start_min": 1380, "end_min": 60},
        ]), FakeCatalog())
        self.assertEqual(bad["status"], "invalid")
        self.assertIn("time_range", {error["code"] for error in bad["errors"]})

    def test_priorities_normalize_and_unexpected_fields_are_rejected(self):
        result = prepare_student_profile(valid_input(weights={
            "gap": 2, "campus_days": 1, "outside_hours": 1,
        }), FakeCatalog())
        self.assertEqual(result["profile"]["weights"], {
            "gap": .5, "campus_days": .25, "outside_hours": .25,
        })
        bad = prepare_student_profile(valid_input(student_id="secret"), FakeCatalog())
        self.assertEqual(bad["status"], "invalid")
        self.assertIn("unknown_fields", {error["code"] for error in bad["errors"]})

    def test_main_calls_module_two_when_a_snapshot_exists(self):
        calls = []
        def module_two(profile, snapshot):
            calls.append((profile, snapshot))
            return "candidate-set"
        result = main(valid_input(), FakeCatalog(), module_two=module_two)
        self.assertEqual(result["module_two_result"], "candidate-set")
        self.assertEqual(len(calls), 1)
        class MissingCatalog:
            def assess(self, profile):
                return None, [{"code": "missing_timetable", "message": "missing"}], []
        blocked = main(valid_input(), MissingCatalog(), module_two=module_two)
        self.assertEqual(blocked["status"], "needs_data")
        self.assertEqual(len(calls), 1)
        class UnverifiedCatalog:
            def assess(self, profile):
                return {"snapshot_id": "test"}, [{"code": "requirements_unverified", "message": "pending"}], []
        unverified = main(valid_input(), UnverifiedCatalog(), module_two=module_two)
        self.assertEqual(unverified["status"], "needs_data")
        self.assertEqual(unverified["module_two_result"], "candidate-set")
        self.assertEqual(len(calls), 2)


class CatalogTests(unittest.TestCase):
    def test_engg2_suggests_code_and_name(self):
        units = load_unit_catalog(
            ROOT / "data/catalog/units_2026_csp.csv",
            (ROOT / "data/catalog/units_2026_cusp.csv",),
        )
        self.assertGreater(len(units), 6500)
        matches = suggest_units("engg2", units, {"ENGG2112"})
        self.assertEqual(matches[0]["unit_code"], "ENGG2112")
        self.assertTrue(any(x["unit_code"] == "ENGG2112" and
                            x["unit_name"] == "Multi-disciplinary Engineering" and
                            x["available_in_snapshot"] for x in matches))

    def test_existing_snapshot_is_blocked_until_requirements_are_verified(self):
        catalog = SnapshotCatalog(ROOT / "data/processed", ROOT / "data/requirements")
        result = prepare_student_profile(valid_input(), catalog)
        self.assertEqual(result["status"], "needs_data")
        self.assertIsNotNone(result["snapshot_ref"])
        self.assertIn("requirements_unverified", {x["code"] for x in result["blockers"]})
        pipeline_result = main(valid_input(), catalog)
        self.assertIn("timetable_data", pipeline_result["completed_modules"])
        self.assertEqual(pipeline_result["module_two_result"]["meeting_count"], 167)
        self.assertNotIn("ranking_result", pipeline_result)

    def test_module_two_reads_only_selected_units_from_local_snapshot(self):
        catalog = SnapshotCatalog(ROOT / "data/processed", ROOT / "data/requirements")
        profile_result = prepare_student_profile(valid_input(), catalog)
        data = load_timetable_data(profile_result["profile"], profile_result["snapshot_ref"], catalog)
        self.assertEqual({row["unit_code"] for row in data.meetings}, {"ENGG2112"})
        self.assertEqual(data.summary["meeting_count"], 167)
        self.assertEqual(data.summary["units"][0]["option_count"], 13)
        first_preview = data.summary["units"][0]["options_preview"][0]
        self.assertEqual(first_preview["building_code"], "F11")
        self.assertEqual(first_preview["building_location"]["precision"], "building")
        self.assertIn("Chemistry Lecture Theatre", first_preview["location_raw"])

    def test_verified_fixture_becomes_ready(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            processed = root / "processed"
            required = root / "requirements"
            processed.mkdir()
            required.mkdir()
            base = "timetable_meetings_2026_S2C_TEST1234_20260924"
            with (processed / f"{base}.csv").open("w", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=[
                    "meeting_id", "unit_code", "year", "session_code", "group_id",
                    "option_id", "activity_group", "class_code", "date", "start_min",
                    "end_min", "status", "building_code", "snapshot_time", "source_url",
                ])
                writer.writeheader()
                writer.writerow({"meeting_id": "one", "unit_code": "TEST1234", "year": 2026, "session_code": "S2C",
                                 "group_id": "TEST1234-S2C|Lecture", "option_id": "TEST1234-S2C|Lecture|01",
                                 "activity_group": "Lecture", "class_code": "01",
                                 "date": "2026-08-03", "start_min": "540", "end_min": "600", "status": "available",
                                 "building_code": "J07", "snapshot_time": "2026-09-24T11:00:00+10:00",
                                 "source_url": "https://example.edu"})
            (processed / f"{base}_report.json").write_text(json.dumps({
                "year": 2026, "session_code": "S2C", "units": {"TEST1234": {"status": "ok"}},
            }))
            requirements_file = required / "requirements_2026_S2C.json"
            requirements_file.write_text(json.dumps({
                "year": 2026, "session_code": "S2C", "verified_units": {
                    "TEST1234": {"group_ids": ["TEST1234-S2C|Lecture"],
                                 "source_url": "https://example.edu", "snapshot_time": "2026-09-24"},
                },
            }))
            result = prepare_student_profile(valid_input(unit_codes=["TEST1234"]), SnapshotCatalog(processed, required))
            self.assertEqual(result["status"], "ready")
            pipeline_result = main(valid_input(unit_codes=["TEST1234"]), SnapshotCatalog(processed, required))
            self.assertEqual(pipeline_result["status"], "ready")
            self.assertEqual(pipeline_result["ranking_result"]["feasible_count"], 1)
            self.assertEqual(pipeline_result["ranking_result"]["top"][0]["meetings"][0]["unit_code"], "TEST1234")
            self.assertEqual(pipeline_result["ranking_result"]["search"]["required_groups"], 1)
            requirements_file.unlink()
            selection = {"TEST1234": ["TEST1234-S2C|Lecture"]}
            trial = main(valid_input(unit_codes=["TEST1234"]),
                         SnapshotCatalog(processed, required), selected_groups=selection)
            self.assertEqual(trial["status"], "ready")
            self.assertEqual(trial["ranking_result"]["basis"], "student_selected")
            self.assertEqual(trial["ranking_result"]["feasible_count"], 1)
            invalid = main(valid_input(unit_codes=["TEST1234"]),
                           SnapshotCatalog(processed, required),
                           selected_groups={"TEST1234": ["OTHER|Lecture"]})
            self.assertEqual(invalid["status"], "needs_data")
            self.assertNotIn("ranking_result", invalid)
            self.assertIn("group_selection_invalid", {x["code"] for x in invalid["blockers"]})


class StorageTests(unittest.TestCase):
    def test_no_consent_creates_no_file_and_consent_can_be_withdrawn(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "private" / "profiles.sqlite3"
            store = ProfileStore(path)
            result = main(valid_input(), FakeCatalog(), store=store)
            self.assertFalse(result["saved"])
            self.assertFalse(path.exists())
            saved = main(valid_input(), FakeCatalog(), consent_to_save=True, store=store)
            self.assertTrue(saved["saved"])
            self.assertTrue(path.exists())
            self.assertTrue(store.withdraw(saved["profile"]["profile_id"]))
            self.assertFalse(store.withdraw(saved["profile"]["profile_id"]))


if __name__ == "__main__":
    unittest.main()
