import unittest
from datetime import date

from uniplan.locations import building_location
from uniplan.ranking import rank_schedules
from uniplan.schedule import Candidate, Meeting


class BuildingLocationTests(unittest.TestCase):
    def test_known_building_has_official_point_and_link(self):
        location = building_location("j07")
        self.assertEqual(location["name"], "Mechanical Engineering Building")
        self.assertTrue(-34 < location["latitude"] < -33)
        self.assertTrue(151 < location["longitude"] < 152)
        self.assertTrue(location["map_url"].startswith("https://maps.sydney.edu.au/?buildingId="))
        self.assertEqual(location["precision"], "building")

    def test_unknown_building_has_no_invented_coordinates(self):
        location = building_location("Z99")
        self.assertIsNone(location["latitude"])
        self.assertIsNone(location["longitude"])
        self.assertEqual(location["precision"], "unverified")
        self.assertEqual(location["map_url"], "https://maps.sydney.edu.au/?building=Z99")
        self.assertIsNone(building_location(""))

    def test_ranked_meeting_keeps_room_and_omits_online_map(self):
        day = date(2026, 8, 3)
        room = "J07.02.S213.Mechanical Engineering Building.Mechanical Eng Lecture Theatre S213"
        candidate = Candidate("one", ("a",), (
            Meeting(day, 540, 600, "J07", False, "a", location_raw=room),
            Meeting(day, 660, 720, "", True, "b", location_raw="Online"),
        ))
        profile = {
            "preferred_hours": {"start_min": 480, "end_min": 1080},
            "weights": {"gap": 1 / 3, "campus_days": 1 / 3, "outside_hours": 1 / 3},
        }
        meetings = rank_schedules([candidate], profile, (day,), limit=1)["top"][0]["meetings"]
        self.assertEqual(meetings[0]["location_raw"], room)
        self.assertEqual(meetings[0]["building_location"]["precision"], "building")
        self.assertIsNone(meetings[1]["building_location"])


if __name__ == "__main__":
    unittest.main()
