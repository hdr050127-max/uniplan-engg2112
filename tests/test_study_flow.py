import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from uniplan.preference import vector
from uniplan.server import AppServer
from uniplan.store import ProfileStore
from uniplan.study import StudyRegistry


ROOT = Path(__file__).resolve().parent.parent
UNITS = ["CIVL3206", "ENGG2112"]


class StaleFetcher:
    def ensure(self, profile, catalog):
        return {"status": "stale_cache", "message": "cache is old"}


class StudyFlowTests(unittest.TestCase):
    """Stale local data still gives a marked trial plan; comparisons return a learned ranking."""

    def setUp(self):
        self.server = AppServer(("127.0.0.1", 0), root=ROOT)
        # Never touch the real consented-data store from tests.
        self.private = tempfile.TemporaryDirectory()
        self.server.store = ProfileStore(Path(self.private.name) / "private/profiles.sqlite3")
        self.server.fetcher = StaleFetcher()
        self.server.studies = StudyRegistry(seed_source=lambda: 1234)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=2)
        self.private.cleanup()

    def post(self, path, payload):
        request = Request(self.base + path, data=json.dumps(payload).encode(),
                          headers={"Content-Type": "application/json"})
        try:
            with urlopen(request) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    def test_stale_snapshot_to_learned_ranking(self):
        profile = {"year": 2026, "session_code": "S2C", "unit_codes": UNITS,
                   "unavailable_windows": [], "transition_min": 0}
        status, first = self.post("/api/prepare", {"profile": profile, "save": False})
        self.assertEqual(status, 200)
        self.assertEqual(first["warnings"][0]["code"], "stale_snapshot")
        self.assertFalse(any(item["code"].startswith("auto_fetch") for item in first["blockers"]))
        self.assertIsNotNone(first["module_two_result"]["snapshot_age_days"])
        groups = {unit["unit_code"]: [group["group_id"] for group in unit["groups"]
                                      if group["default_selected"]]
                  for unit in first["module_two_result"]["units"]}
        status, planned = self.post("/api/prepare", {"profile": profile, "save": False,
                                                      "required_groups": groups})
        self.assertEqual(status, 200)
        ranking = planned["ranking_result"]
        self.assertGreater(ranking["feasible_count"], 0)
        self.assertNotIn("_pool", ranking)
        self.assertNotIn("_options", ranking)
        study = planned["study"]
        self.assertTrue(study["available"])
        self.assertNotIn("split", json.dumps(study))

        def choice(pair):
            left = vector(study["schedules"][pair["left"]]["features"])
            right = vector(study["schedules"][pair["right"]]["features"])
            return "left" if left[1] < right[1] else "right" if right[1] < left[1] else "tie"

        answers = [{"pair_id": pair["pair_id"], "choice": choice(pair)} for pair in study["pairs"]]
        status, bad = self.post("/api/study", {"study_id": study["study_id"], "answers": answers[:-1]})
        self.assertEqual(status, 422)
        status, learned = self.post("/api/study", {"study_id": study["study_id"], "answers": answers,
                                                    "elapsed_ms": 90_000})
        self.assertEqual(status, 200)
        self.assertFalse(learned["saved"])
        self.assertEqual(learned["status"], "learned")
        self.assertFalse(learned["evaluation"]["complete_design"])
        self.assertEqual(len(learned["top"]), min(3, ranking["distinct_profile_count"]))
        self.assertIn("meetings", learned["top"][0])
        self.assertEqual(learned["model"]["spec"]["prior"], "equal_weights")
        # This student only minimised campus days, so D carries the most weight.
        shares = {axis["axis"]: axis["share"] for axis in learned["model"]["axes"]}
        self.assertEqual(max(shares, key=shares.get), "campus_days")
        status, missing = self.post("/api/study", {"study_id": "0" * 32, "answers": answers})
        self.assertEqual(status, 422)
        status, accepted = self.post("/api/accept", {
            "profile_id": planned["profile"]["profile_id"], "method": "baseline", "rank": 1,
            "candidate_id": ranking["top"][0]["candidate_id"], "elapsed_ms": 1000})
        self.assertEqual((status, accepted), (200, {"recorded": False}))
        status, _ = self.post("/api/accept", {"profile_id": "x", "method": "other", "rank": 9,
                                               "candidate_id": "c"})
        self.assertEqual(status, 400)

    def test_consented_study_is_stored_and_withdrawn_together(self):
        profile = {"year": 2026, "session_code": "S2C", "unit_codes": UNITS,
                   "unavailable_windows": []}
        _, first = self.post("/api/prepare", {"profile": profile, "save": False})
        groups = {unit["unit_code"]: [group["group_id"] for group in unit["groups"]
                                      if group["default_selected"]]
                  for unit in first["module_two_result"]["units"]}
        _, planned = self.post("/api/prepare", {"profile": profile, "save": True,
                                                 "required_groups": groups})
        self.assertTrue(planned["saved"])
        study = planned["study"]
        answers = [{"pair_id": pair["pair_id"], "choice": "left"} for pair in study["pairs"]]
        status, learned = self.post("/api/study", {"study_id": study["study_id"],
                                                    "answers": answers, "elapsed_ms": 5000})
        self.assertEqual(status, 200)
        self.assertTrue(learned["saved"])
        rows = self.server.store.load_choices()
        self.assertEqual(len(rows), len(study["pairs"]))
        self.assertEqual({row["split"] for row in rows}, {"train", "test"})
        self.assertEqual(len(rows[0]["fit_scale"]), 3)
        code = planned["profile"]["profile_id"]
        _, accepted = self.post("/api/accept", {"profile_id": code, "method": "learned",
                                                 "rank": 1, "candidate_id": "abc",
                                                 "elapsed_ms": 60000})
        self.assertTrue(accepted["recorded"])
        menu_ids = planned["ranking_result"]["shortlist"]["menus"]["gap,campus_days,outside_hours"]
        items = planned["ranking_result"]["shortlist"]["items"]
        menu = [[items[cid]["features"]["gap_min"], items[cid]["features"]["campus_days"],
                 items[cid]["features"]["outside_min"]] for cid in menu_ids]
        choice = {"profile_id": code, "method": "shortlist", "rank": 1, "candidate_id": menu_ids[0],
                  "menu": menu, "chosen": 0, "axes": ["gap", "campus_days", "outside_hours"]}
        _, recorded = self.post("/api/accept", choice)
        self.assertTrue(recorded["recorded"])
        for broken in ({"chosen": len(menu)}, {"axes": ["gap", "gap"]}, {"menu": [[1, 2]]},
                       {"menu": [["x", 1, 2]]}, {"rank": 13}):
            status, _ = self.post("/api/accept", {**choice, **broken})
            self.assertEqual(status, 400, broken)
        outcomes = self.server.store.load_outcomes()
        self.assertEqual([item["event"] for item in outcomes],
                         ["study_completed", "accepted", "accepted"])
        self.assertEqual(outcomes[-1]["detail"]["menu"], menu)
        request = Request(f"{self.base}/api/profiles/{code}", method="DELETE")
        with urlopen(request) as response:
            self.assertTrue(json.load(response)["removed"])
        self.assertEqual(self.server.store.load_choices(), [])
        self.assertEqual(self.server.store.load_outcomes(), [])


if __name__ == "__main__":
    unittest.main()
