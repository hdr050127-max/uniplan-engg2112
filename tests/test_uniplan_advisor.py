"""Sentence -> conditions -> candidates -> top 3 -> reasons, on the committed 2026 S2C snapshot."""
import json
import os
import tempfile
import threading
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from llm import explain as explainer
from uniplan import advisor
from uniplan.advisor import (CANDIDATE_MAX, CANDIDATE_MIN, conditions_of, merge_conditions,
                             plan_from_sentence, read_sentence, select_candidates)
from uniplan.catalog import SnapshotCatalog
from uniplan.main import main
from uniplan.server import AppServer
from uniplan.store import ProfileStore

ROOT = Path(__file__).resolve().parent.parent
UNITS = ["ENGG2112", "AMME2301", "AMME2262", "CIVL3206"]


def entry(cid, gap, days, outside):
    return {"candidate_id": cid, "features": {"gap_min": gap, "campus_days": days, "outside_min": outside}}


def base_profile(units=UNITS, **fields):
    return {"schema_version": 1, "year": 2026, "session_code": "S2C", "unit_codes": units,
            "unavailable_windows": [], **fields}


def default_groups(catalog, profile):
    data = main(profile, catalog)["module_two_result"]
    return {unit["unit_code"]: [group["group_id"] for group in unit["groups"] if group["default_selected"]]
            for unit in data["units"]}


class CandidateTests(unittest.TestCase):
    def test_small_front_is_topped_up_to_ten_without_near_copies(self):
        pool = [entry("best", 0, 2, 0)] + [entry(f"e{i:02d}", 60 * i, 2 + 0.3 * (i % 3), 40 * (i % 4))
                                           for i in range(1, 30)]
        pool.append(entry("copy", 5, 2.05, 10))  # practically the same as "best"
        chosen, from_front = select_candidates(pool, ("gap", "campus_days", "outside_hours"))
        ids = [item["candidate_id"] for item in chosen]
        self.assertEqual((len(chosen), from_front, ids[0]), (CANDIDATE_MIN, 1, "best"))
        self.assertNotIn("copy", ids)

    def test_small_pool_is_used_whole_and_large_front_is_capped(self):
        self.assertEqual(len(select_candidates([entry("a", 0, 2, 0), entry("b", 90, 3, 0)], ("gap",))[0]), 2)
        front = [entry(f"f{i:02d}", 40 * i, 5 - 0.15 * i, 0) for i in range(30)]
        chosen, _ = select_candidates(front, ("campus_days",))
        self.assertEqual(len(chosen), CANDIDATE_MAX)
        self.assertIn("f29", [item["candidate_id"] for item in chosen])  # the fewest days is always kept

    def test_ranker_answer_is_checked_and_failures_fall_back(self):
        candidates = [{"candidate_id": cid, "features": {}} for cid in ("a", "b", "c")]
        with mock.patch.object(advisor, "rank", return_value=[{"candidate_id": "zz", "score": 9},
                                                              {"candidate_id": "c", "score": 1}]):
            order, scores, source = advisor.rank_candidates(candidates, {})
        self.assertEqual((order, scores, source), (["c", "a", "b"], {"c": 1.0}, "llm.rank"))
        with mock.patch.object(advisor, "rank", side_effect=RuntimeError("model missing")):
            order, _, source = advisor.rank_candidates(candidates, {})
        self.assertEqual(order, ["a", "b", "c"])
        self.assertIn("RuntimeError", source)


class ConditionTests(unittest.TestCase):
    def test_parsed_fields_the_form_would_reject_are_dropped(self):
        broken = {"clauses": [{"text": "x", "label": "blocked_time", "fields": {"unavailable_windows": [
            {"weekday": 5, "start_min": 0, "end_min": 1439}, {"weekday": 9, "start_min": 600, "end_min": 500}],
            "max_daily_minutes": 5}}], "conditions": {}, "unrecognised": []}
        with mock.patch.object(advisor, "parse", return_value=broken):
            clause = read_sentence("x")["clauses"][0]
        self.assertEqual(clause["profile_fields"],
                         {"unavailable_windows": [{"weekday": 5, "start_min": 0, "end_min": 1439}]})
        self.assertEqual(len(clause["problems"]), 2)

    def test_merge_adds_windows_and_preferred_hours(self):
        merged = merge_conditions(base_profile(unavailable_windows=[{"weekday": 1, "start_min": 0, "end_min": 600}]), {
            "unavailable_windows": [{"weekday": 5, "start_min": 0, "end_min": 1439}], "max_days_per_week": 3,
            "preferred_hours": {"weekday": 1, "start_min": 600, "end_min": 1080}, "cares": ["gap"]})
        self.assertEqual([w["weekday"] for w in merged["unavailable_windows"]], [1, 5])
        self.assertEqual((merged["max_days_per_week"], merged["preferred_hours"]), (3, {"start_min": 600, "end_min": 1080}))
        self.assertNotIn("cares", merged)


class EndToEndTests(unittest.TestCase):
    """From a sentence to three timetables: zero conflicts and every hard condition holds."""

    @classmethod
    def setUpClass(cls):
        cls.catalog = SnapshotCatalog(ROOT / "data/processed", ROOT / "data/requirements")
        cls.groups = default_groups(cls.catalog, base_profile())

    def check_recommendation(self, result):
        self.assertEqual(result["status"], "ready", result["blockers"])
        ranking = result["ranking_result"]
        recommendation, items = ranking["recommendation"], ranking["shortlist"]["items"]
        self.assertEqual(len(recommendation["menus"]), 7)
        for axes, menu in recommendation["menus"].items():
            self.assertTrue(min(CANDIDATE_MIN, ranking["distinct_profile_count"]) <= len(menu["candidates"]) <= CANDIDATE_MAX)
            self.assertTrue(1 <= len(menu["picks"]) <= 3)
            for a, b in zip(menu["picks"], menu["picks"][1:]):  # never two near-copies
                self.assertFalse(advisor.similar(items[a], items[b], advisor.CARES))
            self.assertEqual(len(menu["reasons"]), len(menu["picks"]))
            for cid in menu["picks"]:
                self.assertIn(cid, menu["candidates"])
                self.assertEqual(advisor.hard_violations(items[cid]["meetings"], result["profile"]), [], (axes, cid))
                for variant in items[cid]["variants"]:
                    self.assertEqual(advisor.hard_violations(items[variant["candidate_id"]]["meetings"], result["profile"]), [])
        return recommendation, items

    def test_sentence_to_three_valid_timetables(self):
        text = "我周五要打工，要留出午饭时间，而且不想课之间等太久"
        result = plan_from_sentence(text, base_profile(), self.catalog, selected_groups=self.groups)
        self.assertIn({"weekday": 5, "start_min": 0, "end_min": 1439}, result["profile"]["unavailable_windows"])
        self.assertIsNotNone(result["profile"]["lunch"])
        self.assertEqual(result["cares"], ["gap"])
        recommendation, items = self.check_recommendation(result)
        for cid in recommendation["menus"]["gap"]["picks"]:
            self.assertNotIn("5", items[cid]["pattern"])

    def test_explicit_limits_hold_on_every_pick(self):
        conditions = {"max_days_per_week": 4, "max_daily_minutes": 360,
                      "preferred_hours": {"weekday": 1, "start_min": 600, "end_min": 1080}, "cares": ["campus_days"]}
        profile = merge_conditions(base_profile(units=["ENGG2112", "AMME2301"]), conditions)
        groups = default_groups(self.catalog, base_profile(units=["ENGG2112", "AMME2301"]))
        result = main(profile, self.catalog, selected_groups=groups, student_text="每周最多来 4 天，每天最多 6 小时")
        self.assertEqual(result["profile"]["preferred_hours"], {"start_min": 600, "end_min": 1080})
        recommendation, items = self.check_recommendation(result)
        # Early/late minutes count against the student's own 10:00–18:00, not the default 9–18.
        for cid in recommendation["menus"]["campus_days"]["picks"]:
            outside = sum(max(0, 600 - m["start_min"]) + max(0, m["end_min"] - 1080)
                          for m in items[cid]["meetings"] if m["end_min"] > m["start_min"])
            weeks = result["ranking_result"]["teaching_week_count"]
            self.assertAlmostEqual(items[cid]["features"]["outside_min"], outside / weeks, places=6)

    def test_template_reasons_pass_their_own_fact_check(self):
        result = plan_from_sentence("想少去学校，午饭要有时间", base_profile(units=["ENGG2112", "AMME2301"]),
                                    self.catalog, selected_groups=default_groups(
                                        self.catalog, base_profile(units=["ENGG2112", "AMME2301"])))
        recommendation, items = self.check_recommendation(result)
        for axes, menu in recommendation["menus"].items():
            picks = [items[cid] for cid in menu["picks"]]
            conditions = conditions_of(result["profile"], axes.split(","))
            for index, reason in enumerate(menu["reasons"]):
                facts = explainer.facts_of(index, picks, conditions)
                allowed = explainer.allowed_values([f"{facts['count']} 份", *explainer.fact_lines(facts)])
                self.assertIsNone(explainer.check_reason(reason, facts, allowed, first=index == 0), (axes, reason))


class FactCheckTests(unittest.TestCase):
    """Model sentences that contradict the timetable are rejected."""

    def setUp(self):
        def pick(cid, gap, days_attended, outside, weekdays):
            meetings = [{"date": (date(2026, 8, 3) + timedelta(days=7 * week + day - 1)).isoformat(), "weekday": day,
                         "start_min": 600, "end_min": 720, "unit_code": "ENGG2112", "is_online": False,
                         "is_fixed_assessment": False} for week in range(4) for day in weekdays]
            return {"candidate_id": cid, "pattern": "".join(map(str, weekdays)), "meetings": meetings,
                    "features": {"gap_min": gap, "campus_days": days_attended, "outside_min": outside}}
        self.picks = [pick("a", 30, 2, 0, [2, 3]), pick("b", 300, 3, 60, [1, 2, 3])]
        conditions = {"cares": ["gap", "campus_days"], "preferred_hours": {"weekday": 1, "start_min": 540, "end_min": 1080}}
        self.facts = [explainer.facts_of(index, self.picks, conditions) for index in range(2)]

    def check(self, text, index=0):
        facts = self.facts[index]
        allowed = explainer.allowed_values([f"{facts['count']} 份", *explainer.fact_lines(facts)])
        return explainer.check_reason(text, facts, allowed, first=index == 0)

    def test_true_sentences_pass(self):
        self.assertIsNone(self.check("每周只要周二、周三到校，周五没课，课之间基本不用等。"))
        self.assertIsNone(self.check("这 2 份里空等最少，最早 10:00 上课。"))
        self.assertIsNone(self.check("比第 1 份每周多等 4.5 小时，多到校 1.0 天。", index=1))

    def test_false_sentences_are_rejected(self):
        cases = {  # text: (pick index, why)
            "周一没课。": (1, "weekday"),
            "每周到校 3 天。": (0, "number"),
            "最早 8:00 上课。": (0, "time"),
            "这 2 份里早晚课最少。": (1, "superlative"),
            "每周多等 4.5 小时。": (1, "reference"),
            "空等时间短，更灵活。": (0, "comparison"),
            "离食堂很近。": (0, "topic"),
            "多上半天课。": (1, "topic"),
            "课都在 9:00–18:00 之内。": (1, "hours"),
            "空等时间很短。": (1, "direction"),
            "很适合你。": (1, "opinion"),
        }
        for text, (index, why) in cases.items():
            with self.subTest(text=text):
                self.assertEqual(self.check(text, index=index), why)

    def test_model_reasons_replace_template_only_when_they_pass(self):
        with mock.patch.object(explainer, "choose_model", return_value="fake"), \
                mock.patch.object(explainer, "gpu_busy", return_value=False), \
                mock.patch.object(explainer, "ask_model", return_value=["周二、周三到校，课之间基本不用等。", "空等很短。"]):
            result = explainer.explain_detailed("", {"cares": ["gap"]}, self.picks)
        self.assertEqual(result["by"], ["fake", "template"])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["rejected"][1]["why"], "direction")
        with mock.patch.object(explainer, "choose_model", return_value=None):
            self.assertEqual(explainer.explain_detailed("", {}, self.picks)["status"], "unavailable")


class RegistryTests(unittest.TestCase):
    def test_simultaneous_requests_for_one_menu_ask_the_model_once(self):
        registry = advisor.ExplainRegistry()
        token = registry.add("", base_profile() | {"preferred_hours": {"start_min": 540, "end_min": 1080}},
                             {"menus": {"gap": {"picks": ["a"]}}}, {"a": {"candidate_id": "a"}})
        calls = []

        def slow(*args):
            calls.append(args)
            threading.Event().wait(0.2)  # long enough for the other requests to arrive
            return {"reasons": ["x"], "status": "model"}

        with mock.patch.object(advisor, "explain_detailed", side_effect=slow):
            results = []
            workers = [threading.Thread(target=lambda: results.append(registry.explain(token, "gap"))) for _ in range(3)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join()
        self.assertEqual(len(calls), 1)
        self.assertEqual(results, [{"reasons": ["x"], "status": "model"}] * 3)
        self.assertIsNone(registry.explain(token, "campus_days"))
        self.assertIsNone(registry.explain("missing", "gap"))


class ServerTests(unittest.TestCase):
    class Fetcher:
        def ensure(self, profile, catalog):
            return {"status": "cached", "message": "local"}

    def setUp(self):
        self.server = AppServer(("127.0.0.1", 0), root=ROOT)
        self.private = tempfile.TemporaryDirectory()
        self.server.store = ProfileStore(Path(self.private.name) / "profiles.sqlite3")
        self.server.fetcher = self.Fetcher()
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.env = mock.patch.dict(os.environ, {"UNIPLAN_EXPLAIN_MODEL": ""})  # never call Ollama from tests
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=2)
        self.private.cleanup()

    def post(self, path, payload):
        request = Request(self.base + path, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        try:
            with urlopen(request) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    def test_parse_prepare_and_explain(self):
        status, parsed = self.post("/api/parse", {"text": "我周五要打工，不想课之间等太久"})
        self.assertEqual(status, 200)
        self.assertEqual(parsed["clauses"][0]["profile_fields"]["unavailable_windows"][0]["weekday"], 5)
        self.assertEqual(parsed["clauses"][1]["cares"], ["gap"])
        self.assertEqual(self.post("/api/parse", {"text": "   "})[0], 400)

        profile = {"year": 2026, "session_code": "S2C", "unit_codes": ["CIVL3206", "ENGG2112"],
                   "unavailable_windows": parsed["clauses"][0]["profile_fields"]["unavailable_windows"]}
        _, first = self.post("/api/prepare", {"profile": profile, "save": False})
        groups = {unit["unit_code"]: [g["group_id"] for g in unit["groups"] if g["default_selected"]]
                  for unit in first["module_two_result"]["units"]}
        self.assertNotIn("recommendation", first.get("ranking_result") or {})
        status, result = self.post("/api/prepare", {"profile": profile, "save": False, "required_groups": groups,
                                                    "student_text": "我周五要打工，不想课之间等太久"})
        self.assertEqual(status, 200)
        recommendation = result["ranking_result"]["recommendation"]
        items = result["ranking_result"]["shortlist"]["items"]
        self.assertTrue(all(cid in items for menu in recommendation["menus"].values() for cid in menu["picks"]))
        self.assertEqual(self.post("/api/prepare", {"profile": profile, "student_text": "x" * 501})[0], 400)

        status, reasons = self.post("/api/explain", {"token": recommendation["explain_token"], "axes": "gap"})
        self.assertEqual(status, 200)
        self.assertEqual((reasons["status"], reasons["reasons"]), ("unavailable", recommendation["menus"]["gap"]["reasons"]))
        self.assertEqual(self.post("/api/explain", {"token": "nope", "axes": "gap"})[0], 404)

        menu = recommendation["menus"]["gap,campus_days,outside_hours"]
        rows = [[items[cid]["features"][key] for key in ("gap_min", "campus_days", "outside_min")] for cid in menu["picks"]]
        accepted = self.post("/api/accept", {"profile_id": result["profile"]["profile_id"], "method": "recommended",
                                             "rank": 1, "candidate_id": menu["picks"][0], "menu": rows, "chosen": 0,
                                             "axes": ["gap", "campus_days", "outside_hours"]})
        self.assertEqual(accepted, (200, {"recorded": False}))  # nothing saved without consent


if __name__ == "__main__":
    unittest.main()
