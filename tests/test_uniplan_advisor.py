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

import llm.parse as parse_module
from llm import explain as explainer
from uniplan import advisor, wording
from uniplan.advisor import (CANDIDATE_MAX, CANDIDATE_MIN, conditions_of, merge_conditions,
                             plan_from_sentence, read_sentence, select_candidates)
from uniplan.catalog import SnapshotCatalog
from uniplan.main import main
from uniplan.server import AppServer
from uniplan.store import ProfileStore

ROOT = Path(__file__).resolve().parent.parent
UNITS = ["ENGG2112", "AMME2301", "AMME2262", "CIVL3206"]
_runtime = parse_module.RUNTIME


def setUpModule():
    parse_module.RUNTIME = "linear"   # offline and deterministic: no call to the Ollama server


def tearDownModule():
    parse_module.RUNTIME = _runtime


def entry(cid, gap, days, outside):
    return {"candidate_id": cid, "features": {"gap_min": gap, "campus_days": days, "outside_min": outside}}


def base_profile(units=UNITS, **fields):
    return {"schema_version": 1, "year": 2026, "session_code": "S2C", "unit_codes": units,
            "unavailable_windows": [], **fields}


def covers_day(windows, weekday):
    """Some window blocks the whole day; a parser may end it at 1439 or (half-open) at 1440."""
    return any(w["weekday"] == weekday and w["start_min"] <= 0 and w["end_min"] >= 1439 for w in windows)


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

    def test_cares_keep_the_student_order_then_the_rest(self):
        profile = base_profile() | {"preferred_hours": {"start_min": 540, "end_min": 1080}}
        self.assertEqual(conditions_of(profile, ("gap", "campus_days", "outside_hours"), ["outside_hours", "gap"])["cares"],
                         ["outside_hours", "gap", "campus_days"])
        self.assertEqual(conditions_of(profile, ("gap", "campus_days"), ["outside_hours", "campus_days"])["cares"],
                         ["campus_days", "gap"])
        self.assertEqual(conditions_of(profile, ("gap", "campus_days"))["cares"], ["gap", "campus_days"])

    def test_page_is_told_when_parsing_falls_back(self):
        """A model runtime that does not answer falls back to the linear model, and the page says so."""
        import llm.parse as parsing
        from llm.parse import classify

        def unreachable(name):
            def label(text):
                raise OSError("connection refused")
            return label

        with mock.patch.object(parsing, "RUNTIME", "ollama-short:uniplan-parse-7b"), \
                mock.patch.object(parsing, "_down_since", None), mock.patch.object(classify, "by_name", unreachable):
            result = read_sentence("I can't do Fridays, and I hate long gaps")
        self.assertTrue(result["mode"]["simplified"])
        self.assertEqual([clause["label"] for clause in result["clauses"]], ["blocked_time", "prefer_less_waiting"])
        self.assertFalse(read_sentence("I can't do Fridays")["mode"]["simplified"])  # the linear runtime itself

    def test_merge_adds_windows_and_preferred_hours(self):
        merged = merge_conditions(base_profile(unavailable_windows=[{"weekday": 1, "start_min": 0, "end_min": 600}]), {
            "unavailable_windows": [{"weekday": 5, "start_min": 0, "end_min": 1439}], "max_days_per_week": 3,
            "preferred_hours": {"weekday": 1, "start_min": 600, "end_min": 1080}, "cares": ["gap"]})
        self.assertEqual([w["weekday"] for w in merged["unavailable_windows"]], [1, 5])
        self.assertEqual((merged["max_days_per_week"], merged["preferred_hours"]), (3, {"start_min": 600, "end_min": 1080}))
        self.assertNotIn("cares", merged)


FRIDAY = {"weekday": 5, "start_min": 0, "end_min": 1440}
ASKING = {  # what llm.parse.clarify may add; questions here are made up for the page's sake
    "clauses": [{"text": "我周五要打工", "label": "blocked_time", "fields": {"unavailable_windows": [FRIDAY]}},
                {"text": "最多来几天吧", "label": "max_days", "fields": {}}],
    "conditions": {"unavailable_windows": [FRIDAY]}, "unrecognised": [],
    "summary": "周五全天不上课；每周最多到校几天还没说。",
    "questions": [
        {"kind": "hard_or_soft", "clause_index": 0, "text": "Can't, or would rather not?",
         "options": [{"text": "Can't", "label": "blocked_time", "fields": {}},
                     {"text": "Would rather not", "label": "prefer_fewer_days", "fields": {"cares": ["campus_days"]}}]},
        {"kind": "missing_value", "clause_index": 1, "text": "How many days a week, at most?",
         "options": [{"text": "Leave as is", "label": "max_days", "fields": {}},
                     {"text": "3", "label": "max_days", "fields": {"max_days_per_week": 3}}]},
        {"kind": "low_confidence", "clause_index": 7, "text": "Which did you mean?", "options": []},
        {"kind": "offer", "clause_index": None, "text": "Lunch break?",
         "options": [{"text": "30 min between 11:30 am and 2 pm", "label": None,
                      "fields": {"lunch": {"start_min": 690, "end_min": 840, "minutes": 30}}}]},
    ],
}


class ClarifyTests(unittest.TestCase):
    def test_answers_are_prepared_for_the_page(self):
        with mock.patch.object(advisor, "parse", return_value=ASKING) as parsed:
            result = read_sentence("我周五要打工，最多来几天吧", {0: "prefer_fewer_days"})
        parsed.assert_called_once_with("我周五要打工，最多来几天吧", overrides={0: "prefer_fewer_days"})
        self.assertEqual(result["summary"], ASKING["summary"])
        self.assertEqual([q["kind"] for q in result["questions"]], ["hard_or_soft", "missing_value", "offer"])
        hard, missing, offer = result["questions"]
        self.assertEqual(hard["options"][1]["cares"], ["campus_days"])
        self.assertEqual(missing["options"][1]["profile_fields"], {"max_days_per_week": 3})
        self.assertEqual(offer["options"][0]["profile_fields"]["lunch"]["minutes"], 30)
        self.assertEqual(offer["options"][-1]["text"], "No")         # every offer can be declined
        with mock.patch.object(advisor, "parse", return_value=ASKING) as parsed:
            read_sentence("我周五要打工")
        parsed.assert_called_once_with("我周五要打工")                # no overrides: parse() as before

    def test_questions_are_the_parsers_and_each_option_carries_its_note(self):
        with mock.patch.object(advisor, "parse", return_value=ASKING):
            result = read_sentence("我周五要打工，最多来几天吧")
        hard, missing, offer = result["questions"]
        asked = [question for question in ASKING["questions"] if question["clause_index"] != 7]
        self.assertEqual([question["text"] for question in result["questions"]], [question["text"] for question in asked])
        self.assertEqual([o["text"] for o in hard["options"]], ["Can't", "Would rather not"])  # as llm.parse wrote them
        self.assertEqual([o["text"] for o in offer["options"]], ["30 min between 11:30 am and 2 pm", "No"])
        self.assertIn("Fri", result["clauses"][0]["note"])                    # llm.parse.clarify.describe_clause
        self.assertEqual(hard["options"][0]["note"], result["clauses"][0]["note"])
        self.assertIn("3", missing["options"][1]["note"])                      # the note once "3" is chosen
        self.assertNotIn("note", offer["options"][0])
        with mock.patch.object(advisor, "parse", return_value=ASKING), \
                mock.patch.object(advisor.wording, "clause_describer", return_value=None):
            result = read_sentence("我周五要打工，最多来几天吧")
        self.assertEqual([clause["note"] for clause in result["clauses"]],    # uniplan.wording stands in
                         ["Not available Fri", "A cap on days a week, but no number was given"])
        self.assertEqual(result["questions"][1]["options"][1]["note"], "At most 3 days on campus a week")

    def test_the_parsers_describer_writes_the_notes_when_it_works(self):
        describe = mock.Mock(side_effect=lambda clause: f"{clause['label']} read")
        with mock.patch.object(advisor, "parse", return_value=ASKING), \
                mock.patch.object(advisor.wording, "clause_describer", return_value=describe):
            result = read_sentence("我周五要打工，最多来几天吧")
        self.assertEqual([clause["note"] for clause in result["clauses"]], ["blocked_time read", "max_days read"])
        self.assertEqual(result["questions"][0]["options"][1]["note"], "prefer_fewer_days read")
        broken = mock.Mock(side_effect=KeyError("fields"))
        with mock.patch.object(advisor, "parse", return_value=ASKING), \
                mock.patch.object(advisor.wording, "clause_describer", return_value=broken):
            result = read_sentence("我周五要打工，最多来几天吧")
        self.assertEqual(result["clauses"][0]["note"], "Not available Fri")   # falls back to uniplan.wording

    def test_times_and_days_are_written_the_australian_way(self):
        self.assertEqual([wording.clock(m) for m in (540, 570, 720, 1110, 1440)],
                         ["9 am", "9:30 am", "12 pm", "6:30 pm", "midnight"])
        evenings = [{"weekday": day, "start_min": 1080, "end_min": 1439} for day in (2, 4)]
        self.assertEqual(wording.windows_text(evenings), "Tue and Thu after 6 pm")
        mornings = [{"weekday": day, "start_min": 0, "end_min": 600} for day in range(1, 6)]
        self.assertEqual(wording.windows_text(mornings + [{"weekday": 3, "start_min": 840, "end_min": 1080}]),
                         "weekdays before 10 am; Wed 2 pm to 6 pm")

    def test_without_questions_the_result_is_as_before(self):
        plain = {"clauses": ASKING["clauses"], "conditions": {}, "unrecognised": []}
        with mock.patch.object(advisor, "parse", return_value=plain):
            result = read_sentence("我周五要打工")
        self.assertEqual(result["questions"], [])
        self.assertNotIn("summary", result)


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
        self.assertTrue(covers_day(result["profile"]["unavailable_windows"], 5))
        self.assertIsNotNone(result["profile"]["lunch"])
        self.assertEqual(result["cares"], ["gap"])
        recommendation, items = self.check_recommendation(result)
        for cid in recommendation["menus"]["gap"]["picks"]:
            self.assertNotIn("5", items[cid]["pattern"])

    def test_word_order_sets_the_order_rank_receives(self):
        """cares[0] is the student's main concern (llm/contracts.py), so word order must reach rank()."""
        real_rank, runs = advisor.rank, []
        for text in ("I hate long gaps between classes, and I want as few days on campus as possible",
                     "I want as few days on campus as possible, and I hate long gaps between classes"):
            seen = []

            def spy(candidates, prefs):
                seen.append(list(prefs["cares"]))
                return real_rank(candidates, prefs)

            with mock.patch.object(advisor, "rank", side_effect=spy):
                result = plan_from_sentence(text, base_profile(), self.catalog, selected_groups=self.groups)
            runs.append((seen, result["ranking_result"]["recommendation"]["menus"]["gap,campus_days"]["cares"],
                         result["cares"]))
        (first_calls, first_menu, first_cares), (second_calls, second_menu, second_cares) = runs
        self.assertEqual((first_cares, second_cares), (["gap", "campus_days"], ["campus_days", "gap"]))
        self.assertEqual((first_menu, second_menu), (["gap", "campus_days"], ["campus_days", "gap"]))
        self.assertIn(["gap", "campus_days", "outside_hours"], first_calls)
        self.assertIn(["campus_days", "gap", "outside_hours"], second_calls)
        self.assertNotIn(["gap", "campus_days", "outside_hours"], second_calls)

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
            conditions = conditions_of(result["profile"], axes.split(","), menu["cares"])
            for index, reason in enumerate(menu["reasons"]):
                facts = explainer.facts_of(index, picks, conditions, recommendation["_candidates"][axes])
                self.assertIsNone(explainer.check_reason(reason, facts, explainer.allowed_for(facts), first=index == 0),
                                  (axes, reason))


class FactCheckTests(unittest.TestCase):
    """Model sentences that contradict the timetable are rejected."""

    def setUp(self):
        def pick(cid, gap, days_attended, outside, weekdays):
            meetings = [{"date": (date(2026, 8, 3) + timedelta(days=7 * week + day - 1)).isoformat(), "weekday": day,
                         "start_min": 600, "end_min": 720, "unit_code": "ENGG2112", "is_online": False,
                         "group_id": "ENGG2112|Lecture", "building_code": "J01",
                         "is_fixed_assessment": False} for week in range(4) for day in weekdays]
            return {"candidate_id": cid, "pattern": "".join(map(str, weekdays)), "meetings": meetings,
                    "features": {"gap_min": gap, "campus_days": days_attended, "outside_min": outside}}
        self.picks = [pick("a", 30, 2, 0, [2, 3]), pick("b", 300, 3, 60, [1, 2, 3])]
        conditions = {"cares": ["gap", "campus_days"], "preferred_hours": {"weekday": 1, "start_min": 540, "end_min": 1080}}
        self.facts = [explainer.facts_of(index, self.picks, conditions) for index in range(2)]
        # A fixed comparison of pick 2 with pick 1, as llm.rank.contributions would phrase it.
        self.facts[1]["versus"] = {"rival": 1, "strengths": [], "main": None,
                                   "costs": ["4 h 30 min more waiting a week", "1 more day on campus a week",
                                             "1 h more class outside 9 am to 6 pm a week"]}

    def check(self, text, index=0):
        facts = self.facts[index]
        return explainer.check_reason(text, facts, explainer.allowed_for(facts), first=index == 0)

    def test_true_sentences_pass(self):
        self.assertIsNone(self.check("Only on campus Tue and Wed each week, no classes on Fri, "
                                     "and almost no waiting between classes."))
        self.assertIsNone(self.check("The least waiting of these 2 options, and the earliest class is at 10 am."))
        self.assertIsNone(self.check("Compared with option 1, it has 4 h 30 min more waiting a week "
                                     "and one more day on campus a week.", index=1))
        self.assertIsNone(self.check("No classes before 10 am, and nothing after 12 pm."))
        self.assertIsNone(self.check("Only on campus Tue and Wed."))
        self.assertIsNone(self.check("No classes on Mon, Thu or Fri."))
        self.assertIsNone(self.check("No Friday classes."))                 # a day between "no" and "classes"
        self.assertEqual(explainer._mentioned_days("4 weekdays on campus"), set())  # a count, not Mon to Fri

    def test_sameness_and_more_need_the_numbers(self):
        facts = {**self.facts[1], "versus": {"rival": 1, "strengths": ["1 h less waiting a week"], "costs": [],
                                             "main": "gap_h"}}  # only the waiting differs
        allowed = explainer.allowed_for(facts)
        self.assertIsNone(explainer.check_reason(
            "Compared with option 1, it has 1 h less waiting a week, and the same early or late class time.",
            facts, allowed, False))
        self.assertEqual(explainer.check_reason("Compared with option 1, it has better early or late class times.",
                                                facts, allowed, False), "comparison")

    def test_false_sentences_are_rejected(self):
        cases = {  # text: (pick index, why)
            "No classes on Mon.": (1, "weekday"),
            "On campus 3 days a week.": (0, "number"),
            "The earliest class is at 8 am.": (0, "time"),
            "The least early or late class time of these 2 options.": (1, "superlative"),
            "4 h 30 min more waiting a week.": (1, "reference"),
            "Short waits, and more flexible.": (0, "comparison"),
            "Close to the cafeteria.": (0, "topic"),
            "More classes than option 1.": (1, "topic"),
            "All classes are within 9 am to 6 pm.": (1, "hours"),
            "Waiting time is very short.": (1, "direction"),
            "It suits you well.": (1, "opinion"),
            "You come in every day.": (0, "weekday"),
            "No classes before 11 am.": (0, "time"),
            "0 min of extracurricular activities.": (0, "topic"),
            "Compared with option 1, it has 4 h 30 min less waiting a week.": (1, "number"),  # it is more
            "Compared with option 1, it has 4 h 30 min more waiting a day.": (1, "number"),   # a weekly figure per day
            "This one finishes latest.": (0, "superlative"),
            "Compared with option 1, it has 4 h 30 min more waiting a week, and the same early or late class time.":
                (1, "comparison"),  # pick 2 has 60 more minutes
            "Only on campus Tue.": (0, "weekday"),  # leaves out Wednesday
            "A lunch break every day.": (0, "topic"),  # no lunch condition was set
            "Good for being on campus every day.": (0, "weekday"),
            "No early or late classes.": (1, "direction"),  # pick 2 has 60 minutes a week
            "No waiting between classes.": (0, "direction"),  # 30 minutes a week is not none
            "两天到校，课少。": (0, "length"),  # the page is in English
        }
        for text, (index, why) in cases.items():
            with self.subTest(text=text):
                self.assertEqual(self.check(text, index=index), why)

    def test_model_reasons_replace_template_only_when_they_pass(self):
        with mock.patch.object(explainer, "choose_model", return_value="fake"), \
                mock.patch.object(explainer, "gpu_busy", return_value=False), \
                mock.patch.object(explainer, "ask_model", return_value=[
                    "Tue and Wed on campus, with almost no waiting between classes.", "Waiting is short."]):
            result = explainer.explain_detailed("", {"cares": ["gap"]}, self.picks)
        self.assertEqual(result["by"], ["fake", "template"])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["rejected"][1]["why"], "direction")
        with mock.patch.object(explainer, "choose_model", return_value=None):
            self.assertEqual(explainer.explain_detailed("", {}, self.picks)["status"], "unavailable")

    def test_rewriting_is_off_unless_a_model_is_named(self):
        with mock.patch.dict(os.environ), \
                mock.patch.object(explainer.ollama, "available", side_effect=AssertionError("asked Ollama")):
            os.environ.pop("UNIPLAN_EXPLAIN_MODEL", None)
            self.assertFalse(explainer.rewriting_on())
            self.assertIsNone(explainer.choose_model())
            self.assertEqual(explainer.explain_detailed("", {"cares": ["gap"]}, self.picks)["status"], "unavailable")

    def test_templates_read_as_plain_english(self):
        reasons = explainer.explain("", {"cares": ["gap"]}, self.picks, model=None)
        self.assertTrue(reasons[0].startswith("Vs option 2: "), reasons[0])
        self.assertTrue(reasons[1].startswith("Vs option 1: ") or reasons[1] == "Close to option 1.", reasons[1])
        for reason in reasons:
            self.assertNotIn("On campus", reason)  # the days are in the title and the week view (DESIGN 10.2)
            self.assertNotRegex(reason, "[\u2013\u2014\u00b7]")  # no dashes or middle dots (docs/DESIGN.md)

    def test_a_closest_timetable_says_what_it_gives_up_first(self):
        picks = [{**pick, "watch": "Watch the recording of ENGG2112 Lecture",
                  "broken": "Breaks 2 limits: 4 classes on Tue and Wed before 11 am; No 30 min lunch break on Tue",
                  "breaks": [{"kind": "unavailable_windows"}, {"kind": "lunch"}]} for pick in self.picks]
        conditions = {"cares": ["gap"], "lunch": {"start_min": 690, "end_min": 840, "minutes": 30}}
        reasons = explainer.explain("", conditions, picks, model=None)
        self.assertTrue(reasons[0].startswith("Watch the recording of ENGG2112 Lecture. Breaks 2 limits: "), reasons[0])
        for index, reason in enumerate(reasons):
            facts = explainer.facts_of(index, picks, conditions)
            self.assertIsNone(explainer.check_reason(reason, facts, explainer.allowed_for(facts), first=index == 0), reason)
            self.assertNotIn("lunch break fits", " ".join(explainer.fact_lines(facts)))  # it is broken here


class RegistryTests(unittest.TestCase):
    def test_simultaneous_requests_for_one_menu_ask_the_model_once(self):
        registry = advisor.ExplainRegistry()
        token = registry.add("", base_profile() | {"preferred_hours": {"start_min": 540, "end_min": 1080}},
                             {"menus": {"gap": {"picks": ["a"]}}}, {"a": {"candidate_id": "a"}})
        calls = []

        def slow(*args, **kwargs):
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

    def test_parse_takes_the_students_answers(self):
        with mock.patch.object(advisor, "parse", return_value=ASKING) as parsed:
            status, result = self.post("/api/parse", {"text": "我周五要打工，最多来几天吧",
                                                      "overrides": {"0": "prefer_fewer_days"}})
        self.assertEqual(status, 200)
        parsed.assert_called_once_with("我周五要打工，最多来几天吧", overrides={0: "prefer_fewer_days"})
        self.assertEqual(len(result["questions"]), 3)
        self.assertEqual(self.post("/api/parse", {"text": "x", "overrides": {"0": "nonsense"}})[0], 400)
        self.assertEqual(self.post("/api/parse", {"text": "x", "overrides": {"first": "lunch"}})[0], 400)

    def test_parse_prepare_and_explain(self):
        status, parsed = self.post("/api/parse", {"text": "我周五要打工，不想课之间等太久"})
        self.assertEqual(status, 200)
        windows = [w for clause in parsed["clauses"] for w in clause["profile_fields"].get("unavailable_windows", [])]
        self.assertTrue(covers_day(windows, 5))
        self.assertIn("gap", [care for clause in parsed["clauses"] for care in clause["cares"]])
        self.assertEqual(self.post("/api/parse", {"text": "   "})[0], 400)

        profile = {"year": 2026, "session_code": "S2C", "unit_codes": ["CIVL3206", "ENGG2112"],
                   "unavailable_windows": windows}
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
        self.assertEqual(self.post("/api/prepare", {"profile": profile, "cares": ["gap", "gap"]})[0], 400)
        _, ordered = self.post("/api/prepare", {"profile": profile, "save": False, "required_groups": groups,
                                                "student_text": "", "cares": ["outside_hours", "gap"]})
        self.assertEqual(ordered["ranking_result"]["recommendation"]["menus"]["gap,campus_days,outside_hours"]["cares"],
                         ["outside_hours", "gap", "campus_days"])

        self.assertNotIn("explain_token", recommendation)  # templates only unless a model is named
        with mock.patch.dict(os.environ, {"UNIPLAN_EXPLAIN_MODEL": "qwen2.5:7b"}), \
                mock.patch.object(explainer, "choose_model", return_value=None):
            _, named = self.post("/api/prepare", {"profile": profile, "save": False, "required_groups": groups,
                                                  "student_text": "我周五要打工，不想课之间等太久"})
            rewritten = named["ranking_result"]["recommendation"]
            status, reasons = self.post("/api/explain", {"token": rewritten["explain_token"], "axes": "gap"})
        self.assertEqual(status, 200)
        self.assertEqual((reasons["status"], reasons["reasons"]), ("unavailable", rewritten["menus"]["gap"]["reasons"]))
        self.assertEqual(self.post("/api/explain", {"token": "nope", "axes": "gap"})[0], 404)

        menu = recommendation["menus"]["gap,campus_days,outside_hours"]
        rows = [[items[cid]["features"][key] for key in ("gap_min", "campus_days", "outside_min")] for cid in menu["picks"]]
        accepted = self.post("/api/accept", {"profile_id": result["profile"]["profile_id"], "method": "recommended",
                                             "rank": 1, "candidate_id": menu["picks"][0], "menu": rows, "chosen": 0,
                                             "axes": ["gap", "campus_days", "outside_hours"]})
        self.assertEqual(accepted, (200, {"recorded": False}))  # nothing saved without consent


if __name__ == "__main__":
    unittest.main()
