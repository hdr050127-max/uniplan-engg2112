import unittest

from timetable_scraper import (
    building_code, clean_subjects, normalise_codes, robots_text_allows_requests,
)


class TimetableCleanerTests(unittest.TestCase):
    def test_expands_exact_dates_and_uses_date_specific_location(self):
        offering = "TEST1234-S2C-ND-CC"
        option = f"{offering}|Tutorial|01"
        subjects = {
            offering: {
                "callista_code": "TEST1234",
                "semester": "S2C",
                "activities": {
                    option: {
                        "activity_group_code": "Tutorial",
                        "activity_code": "01",
                        "activity_type": "Tutorial",
                        "start_time": "09:30",
                        "duration": "90",
                        "day_of_week": "Mon",
                        "activitiesDays": ["3/8/2026", "17/8/2026"],
                        "location": "J07.02.S220.Mechanical Engineering",
                        "selectable": "available",
                        "availability": -1,
                    }
                },
            }
        }
        locations = {
            offering: {
                option: [{
                    "description": "F07.03.351.Carslaw Building",
                    "activityDays": ["17/8/2026"],
                }]
            }
        }
        rows, warnings = clean_subjects(
            subjects, locations, code="TEST1234", year=2026,
            session="S2C", snapshot_time="2026-09-24T12:00:00+10:00"
        )
        self.assertEqual([r["date"] for r in rows], ["2026-08-03", "2026-08-17"])
        self.assertEqual([r["building_code"] for r in rows], ["J07", "F07"])
        self.assertEqual(rows[0]["start_min"], 570)
        self.assertEqual(rows[0]["end_min"], 660)
        self.assertEqual(rows[0]["option_id"], rows[1]["option_id"])
        self.assertEqual(rows[0]["available_seats"], "")
        self.assertEqual(warnings, [])

    def test_ids_and_ambiguous_buildings(self):
        self.assertEqual(normalise_codes([" engg2112,AMME1362 ", "ENGG2112"]),
                         ["ENGG2112", "AMME1362"])
        self.assertEqual(building_code("F07.01.100.Room, J07.02.200.Room"), "")
        self.assertEqual(building_code("F07.01.100.Room, F07.02.200.Room"), "F07")

    def test_one_line_robots_disallow_is_respected(self):
        self.assertFalse(robots_text_allows_requests("User-agent: * Disallow: /"))


if __name__ == "__main__":
    unittest.main()
