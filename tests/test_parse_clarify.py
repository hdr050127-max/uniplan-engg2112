"""Restating and asking back (llm/parse/clarify.py). Runs offline: labels and opinions are given."""
import unittest

from llm.parse import clarify, parse
from llm.parse.extract import fields, merge


def result_of(*clauses):
    """A parse result from (text, label) pairs, read with the real rules."""
    built = [{"text": text, "label": label, "fields": fields(label, text)} for text, label in clauses]
    return {"clauses": built, "conditions": merge(built),
            "unrecognised": [c["text"] for c in built if c["label"] == "other"]}


def agreeing(text):
    return {"blocked_time": 0.9, "other": 0.1}


def kinds(found):
    return [q["kind"] for q in found]


class SummaryTests(unittest.TestCase):
    def test_restates_conditions_and_unrecognised(self):
        result = result_of(("我周二和周四晚上在餐厅打工", "blocked_time"), ("每天上课不超过5小时", "max_daily_hours"),
                           ("不想上太早的课", "prefer_no_early_late"), ("想和室友同一个 tutorial", "other"))
        self.assertEqual(clarify.summary(result),
                         "我理解为：周二、周四 18:00 以后不能上课；每天最多上 5 小时课；尽量少早晚课；"
                         "“想和室友同一个 tutorial”这句排课管不了。")

    def test_whole_days_every_day_and_nothing_read(self):
        result = result_of(("周五要打工", "blocked_time"), ("十点前没法上课", "blocked_time"))
        self.assertEqual(clarify.summary(result), "我理解为：周一到周四 10:00 以前不能上课；周五全天不能上课。")
        self.assertEqual(clarify.summary(result_of(("每天早上送孩子", "blocked_time"))), "我理解为：每天 10:00 以前不能上课。")
        self.assertEqual(clarify.summary(result_of(("hello there", "other"))), "我没读出排课要求。“hello there”这句排课管不了。")


class QuestionTests(unittest.TestCase):
    def test_disagreement_needs_a_confident_second_opinion(self):
        result = result_of(("周四晚上没问题", "blocked_time"))
        sure = clarify.questions(result, [True], lambda t: {"other": 0.8, "blocked_time": 0.2})
        unsure = clarify.questions(result_of(("周四晚上有空", "blocked_time")), [True],
                                   lambda t: {"other": 0.28, "blocked_time": 0.27, "lunch": 0.2})
        self.assertEqual(kinds(sure), ["low_confidence"])
        self.assertEqual([o["label"] for o in sure[0]["options"]], ["blocked_time", "other"])
        self.assertNotIn("low_confidence", kinds(unsure))

    def test_linear_run_time_asks_when_its_top_two_are_close(self):
        close = clarify.questions(result_of(("x", "max_days")), [False], lambda t: {"max_days": 0.45, "other": 0.4})
        clear = clarify.questions(result_of(("x", "max_days")), [False], lambda t: {"max_days": 0.8, "other": 0.1})
        self.assertEqual([o["label"] for o in close[0]["options"]], ["max_days", "other"])
        self.assertFalse([q for q in clear if q["kind"] == "low_confidence"])

    def test_rule_checks_ask_without_a_second_opinion(self):
        fine = clarify.questions(result_of(("Early morning classes are fine", "prefer_no_early_late")), [True], None)
        except_day = clarify.questions(result_of(("I'm fine with any day except Friday", "other")), [True], None)
        count = clarify.questions(result_of(("four campus days or fewer, if you can", "prefer_fewer_days")), [True], None)
        self.assertEqual([o["label"] for o in fine[0]["options"]], ["prefer_no_early_late", "other"])
        self.assertEqual([o["label"] for o in except_day[0]["options"]], ["other", "blocked_time"])
        self.assertEqual([o["label"] for o in count[0]["options"]], ["prefer_fewer_days", "max_days"])

    def test_hard_or_soft_options_carry_their_fields(self):
        found = clarify.questions(result_of(("ideally done by 4, I pick up my son", "blocked_time")), [True], agreeing)
        self.assertEqual(kinds(found), ["hard_or_soft"])
        hard, soft = found[0]["options"]
        self.assertEqual((hard["label"], soft["label"]), ("blocked_time", "prefer_no_early_late"))
        self.assertEqual(hard["fields"]["unavailable_windows"][0], {"weekday": 1, "start_min": 960, "end_min": 1440})
        self.assertEqual(soft["fields"]["preferred_hours"]["end_min"], 960)
        for text, label in (("please no classes before 9", "prefer_no_early_late"),        # unhedged clock: rule 4
                            ("ideally no 8ams", "blocked_time"),                             # hedged clock: rule 5
                            ("早上课真的不想上", "prefer_no_early_late"),                      # part of day + request
                            ("no 8ams would be nice", "prefer_no_early_late")):              # soft phrase
            self.assertIn("hard_or_soft", kinds(clarify.questions(result_of((text, label)), [True], agreeing)), text)
        self.assertEqual(clarify.questions(result_of(("I hate mornings", "prefer_no_early_late")), [True], None), [])

    def test_missing_values(self):
        days = clarify.questions(result_of(("少来几天，一周最多来几天", "max_days")), [True], None)
        self.assertEqual(days[0]["kind"], "missing_value")
        self.assertEqual(days[0]["options"][0], {"text": "先这样，我在句子里补上", "label": "max_days", "fields": {}})
        self.assertIn({"max_days_per_week": 3}, [o["fields"] for o in days[0]["options"]])
        work = clarify.questions(result_of(("我要打工", "blocked_time")), [True], agreeing)
        self.assertEqual([o["label"] for o in work[0]["options"]], ["blocked_time", "other"])

    def test_offers_follow_what_the_student_cares_about(self):
        found = clarify.questions(result_of(("课尽量排在一起", "prefer_fewer_days"), ("不想等太久", "prefer_less_waiting")),
                                  [True, True], None)
        self.assertEqual([q["text"] for q in found], ["要不要定一个每周最多来几天？", "要不要留出午饭时间？"])
        self.assertTrue(all(q["clause_index"] is None and q["options"][0]["text"].startswith("不用") for q in found))
        online = clarify.questions(result_of(("online classes are fine", "other")), [True], None)
        self.assertEqual(online, [])

    def test_at_most_three_and_confirmed_clauses_are_not_asked_again(self):
        result = result_of(("我要打工", "blocked_time"), ("一周最多来几天", "max_days"),
                           ("每天最多上几小时", "max_daily_hours"), ("课尽量排在一起", "prefer_fewer_days"))
        self.assertEqual(len(clarify.questions(result, [True] * 4, None)), clarify.MAX_QUESTIONS)
        self.assertNotIn(0, [q["clause_index"] for q in clarify.questions(result, [True] * 4, None, confirmed={0})])


class ParseTests(unittest.TestCase):
    def test_parse_restates_asks_and_applies_answers(self):
        label = lambda text: "blocked_time" if "4" in text else "prefer_less_waiting"     # noqa: E731
        first = parse("ideally done by 4, I pick up my son. I hate long gaps", label)
        self.assertTrue(first["summary"].startswith("我理解为："))
        question = next(q for q in first["questions"] if q["kind"] == "hard_or_soft")
        soft = question["options"][1]
        again = parse("ideally done by 4, I pick up my son. I hate long gaps", label,
                      overrides={question["clause_index"]: soft["label"]})
        self.assertEqual(again["clauses"][0]["label"], "prefer_no_early_late")
        self.assertEqual(again["conditions"]["preferred_hours"]["end_min"], 960)
        self.assertNotIn(0, [q["clause_index"] for q in again["questions"]])

    def test_empty_input_stays_bare(self):
        self.assertEqual(parse("", lambda text: "other"), {"clauses": [], "conditions": {}, "unrecognised": []})


if __name__ == "__main__":
    unittest.main()
