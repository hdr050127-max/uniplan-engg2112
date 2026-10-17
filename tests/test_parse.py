"""Rules of the parsing block: splitting, number reading, the test-set format."""
import unittest
from pathlib import Path

from llm.parse import parse
from llm.parse.extract import fields
from llm.parse.gold import load, read_block, write_block
from llm.parse.keywords import keyword_label
from llm.parse.split import split_clauses
from llm.parse.text import normalize

TEMPLATE = Path(__file__).resolve().parents[1] / "llm" / "parse" / "data" / "test_template.csv"


def block(label, text):
    return write_block(fields(label, text).get("unavailable_windows", []))


class SplitTests(unittest.TestCase):
    def test_cuts_at_punctuation_and_joining_words(self):
        self.assertEqual(split_clauses("我周五要打工，每天早上送孩子，而且不想课之间等太久"),
                         ["我周五要打工", "每天早上送孩子", "不想课之间等太久"])
        self.assertEqual(split_clauses("I hate 8ams but I want lunch"), ["I hate 8ams", "I want lunch"])

    def test_keeps_lists_of_days_and_times_together(self):
        self.assertEqual(split_clauses("I work Mon, Wed and Fri, and I hate gaps"),
                         ["I work Mon, Wed and Fri", "I hate gaps"])
        self.assertEqual(split_clauses("between 12 and 2 I need lunch"), ["between 12 and 2 I need lunch"])
        self.assertEqual(split_clauses("我周一要打工，周三也是"), ["我周一要打工，周三也是"])

    def test_glues_reasons_and_back_references(self):
        self.assertEqual(split_clauses("因为要送孩子，早上九点半以前不行"), ["因为要送孩子，早上九点半以前不行"])
        self.assertEqual(split_clauses("我周五打工，所以那天不行"), ["我周五打工，所以那天不行"])
        self.assertEqual(split_clauses("最好十点以后上课，如果可以的话"), ["最好十点以后上课，如果可以的话"])

    def test_and_only_cuts_before_a_new_clause(self):
        for text in ("I work Monday, Wednesday and Friday", "no more than six hours of lectures and tuts a day",
                     "four and a half hours a day is my limit", "my partner and I both work on Fridays"):
            self.assertEqual(split_clauses(text), [text])
        self.assertEqual(split_clauses("I want online tutorials and as few campus days as possible"),
                         ["I want online tutorials", "as few campus days as possible"])

    def test_number_add_ons_stay_with_their_clause(self):
        for text in ("as few days as possible, maybe 2", "Ideally only 2 days, but 3 is ok",
                     "only one day would be a dream but realistically two", "an hour gap is fine but no more"):
            self.assertEqual(split_clauses(text), [text])
        self.assertEqual(split_clauses("No mornings Tue/Thu, max 3 days"), ["No mornings Tue/Thu", "max 3 days"])

    def test_back_references_and_lone_words(self):
        for text in ("fewer, longer days please", "After 3pm I'm free, before that I'm at work",
                     "the less I have to come in, the happier I am", "Monday is my kids' day, I have them all day"):
            self.assertEqual(split_clauses(text), [text])
        self.assertEqual(split_clauses("Wednesdays I'm free, other days I work from 3"),
                         ["Wednesdays I'm free", "other days I work from 3"])

    def test_reasons_stay_with_their_request(self):
        for text in ("Fridays are a no-go, I've got a shift", "pls avoid wed, it's my only day with my kids",
                     "I'm in the uni orchestra, rehearsals are Thursday 5 to 8", "周一不能上课，有兼职"):
            self.assertEqual(split_clauses(text), [text])
        self.assertEqual(split_clauses("I work Fridays, I hate gaps"), ["I work Fridays", "I hate gaps"])

    def test_full_stop_after_a_number_ends_the_sentence(self):
        self.assertEqual(split_clauses("no 8ams, and ideally I'm done by 4. Fridays off please"),
                         ["no 8ams", "ideally I'm done by 4", "Fridays off please"])
        self.assertEqual(split_clauses("4.5 hours a day max"), ["4.5 hours a day max"])

    def test_drops_pleasantries_and_empty_text(self):
        self.assertEqual(split_clauses("一周最多三天，谢谢！"), ["一周最多三天"])
        self.assertEqual(split_clauses("  "), [])


class NumberTests(unittest.TestCase):
    def test_chinese_numbers_only_with_units(self):
        self.assertEqual(normalize("一周三天，每周三，十点半，两个小时"), "一周3天,每周三,10点半,2个小时")
        self.assertEqual(normalize("周一三点"), "周一3点")
        self.assertEqual(normalize("上午的课少一点"), "上午的课少一点")

    def test_blocked_days_and_times(self):
        self.assertEqual(block("blocked_time", "周五要打工"), "Fri all")
        self.assertEqual(block("blocked_time", "每天早上送孩子"), "Mon-Fri 0:00-10:00")
        self.assertEqual(block("blocked_time", "十点前没法上课"), "Mon-Fri 0:00-10:00")
        self.assertEqual(block("blocked_time", "晚上7点以后要上班"), "Mon-Fri 19:00-24:00")
        self.assertEqual(block("blocked_time", "周二、四下午两点半到四点有训练"), "Tue,Thu 14:30-16:00")
        self.assertEqual(block("blocked_time", "I work 9-5 on Tuesdays"), "Tue 9:00-17:00")
        self.assertEqual(block("blocked_time", "no classes after 6"), "Mon-Fri 18:00-24:00")

    def test_days_paired_with_their_own_times(self):
        self.assertEqual(block("blocked_time", "周一上午、周三下午有训练"), "Mon 0:00-12:00; Wed 12:00-18:00")
        self.assertEqual(block("blocked_time", "before 10am on Mondays and Wednesdays"), "Mon,Wed 0:00-10:00")

    def test_only_and_finish_flip_the_window(self):
        self.assertEqual(block("blocked_time", "只想周二周四去学校"), "Mon,Wed,Fri all")
        self.assertEqual(block("blocked_time", "周二周四有空，其他天都不行"), "Mon,Wed,Fri all")
        self.assertEqual(block("blocked_time", "周五只能上午上课"), "Fri 12:00-24:00")
        self.assertEqual(block("blocked_time", "I can only come after 10am on Tuesdays"), "Tue 0:00-10:00")
        self.assertEqual(block("blocked_time", "下午三点前要走"), "Mon-Fri 15:00-24:00")
        self.assertEqual(block("blocked_time", "10点以后才有空"), "Mon-Fri 0:00-10:00")
        self.assertEqual(block("blocked_time", "不希望早于10am上课"), "Mon-Fri 0:00-10:00")
        self.assertEqual(block("blocked_time", "除了周二和周四的晚上，其他时间都不方便上课"),
                         "Mon,Wed,Fri all; Tue,Thu 0:00-18:00")
        self.assertEqual(block("blocked_time", "周三下午不行，其他时间都没问题"), "Wed 12:00-18:00")

    def test_round_two_reading_fixes(self):
        self.assertEqual(block("blocked_time", "please keep my afternoons clear"), "Mon-Fri 12:00-18:00")
        self.assertEqual(block("blocked_time", "no arvo classes"), "Mon-Fri 12:00-18:00")
        self.assertEqual(block("blocked_time", "keep everything before 11 free"), "Mon-Fri 0:00-11:00")
        self.assertEqual(block("blocked_time", "I'd rather keep nights free"), "Mon-Fri 18:00-24:00")
        self.assertEqual(block("blocked_time", "classes have to be over by 2:30"), "Mon-Fri 14:30-24:00")
        self.assertEqual(block("blocked_time", "the earliest I can get there is 10"), "Mon-Fri 0:00-10:00")
        self.assertEqual(block("blocked_time", "my shift ends at 10am every day"), "Mon-Fri 0:00-10:00")
        self.assertEqual(block("blocked_time", "no evening classes after 6:30"), "Mon-Fri 18:30-24:00")
        self.assertEqual(block("blocked_time", "I tutor 4-7 on Tuesdays"), "Tue 16:00-19:00")
        self.assertEqual(block("blocked_time", "I start work at 2 on Fridays"), "Fri 14:00-24:00")
        self.assertEqual(block("blocked_time", "Wednesday and Thursday only"), "Mon,Tue,Fri all")
        self.assertEqual(block("blocked_time", "put all my classes on Tuesday and Wednesday"), "Mon,Thu,Fri all")
        self.assertEqual(block("blocked_time", "课都排在周三周四吧"), "Mon,Tue,Fri all")
        self.assertEqual(block("blocked_time", "pls avoid wed, it's my only day with my kids"), "Wed all")
        self.assertEqual(fields("prefer_no_early_late", "I'm way more awake in the afternoon"),
                         {"cares": ["outside_hours"]})

    def test_day_counts_in_words_and_add_ons(self):
        for text, days in (("as few days as possible, maybe 2", 2), ("a 2-day week would be amazing", 2),
                           ("I'd love to only come in twice a week", 2),
                           ("only one day would be a dream but realistically two", 2),
                           ("I work 4 days so I can only do uni on the other 1", 1)):
            self.assertEqual(fields("max_days", text), {"max_days_per_week": days}, text)
        self.assertEqual(fields("max_daily_hours", "I'd like to leave campus within 6 hours of arriving"),
                         {"max_daily_span": 360})
        self.assertEqual(fields("lunch", "I'd like lunch at 12 for 45 minutes")["lunch"],
                         {"start_min": 720, "end_min": 765, "minutes": 45})

    def test_counts_hours_lunch_and_soft_hours(self):
        self.assertEqual(fields("max_days", "一周最多来三天"), {"max_days_per_week": 3})
        self.assertEqual(fields("max_days", "at most four days a week"), {"max_days_per_week": 4})
        self.assertEqual(fields("max_daily_hours", "每天上课别超过四个半小时"), {"max_daily_minutes": 270})
        self.assertEqual(fields("max_daily_hours", "no more than 8 hours on campus a day"), {"max_daily_span": 480})
        self.assertEqual(fields("lunch", "中午要留时间吃饭")["lunch"], {"start_min": 690, "end_min": 840, "minutes": 30})
        self.assertEqual(fields("lunch", "12点到1点要吃饭")["lunch"], {"start_min": 720, "end_min": 780, "minutes": 60})
        self.assertEqual(fields("prefer_no_early_late", "最好十点以后再上课")["preferred_hours"],
                         {"weekday": 1, "start_min": 600, "end_min": 1080})
        self.assertEqual(fields("prefer_no_early_late", "ideally finish by 4pm")["preferred_hours"]["end_min"], 960)
        self.assertEqual(fields("prefer_no_early_late", "最好九点以后的课多一点")["preferred_hours"]["start_min"], 540)
        self.assertEqual(fields("prefer_no_early_late", "ideally no classes before 10")["preferred_hours"]["start_min"],
                         600)
        self.assertEqual(fields("prefer_no_early_late", "早上起不来"), {"cares": ["outside_hours"]})

    def test_missing_numbers_give_no_fields(self):
        self.assertEqual(fields("blocked_time", "我要打工"), {})
        self.assertEqual(fields("max_days", "少来几天"), {})
        self.assertEqual(fields("other", "周五"), {})


class GoldFormatTests(unittest.TestCase):
    def test_block_cells_round_trip(self):
        cell = "Mon-Fri 0:00-10:00; Fri all"
        self.assertEqual(write_block(read_block(cell)), "Mon-Thu 0:00-10:00; Fri all")
        self.assertEqual(read_block("Tue,Thu 18:00-24:00"), [
            {"weekday": 2, "start_min": 1080, "end_min": 1440}, {"weekday": 4, "start_min": 1080, "end_min": 1440}])

    def test_template_loads_and_rules_read_its_numbers(self):
        sentences = load(TEMPLATE)
        self.assertEqual(len(sentences), 10)
        for sentence in sentences:
            for clause in sentence["clauses"]:
                self.assertEqual(fields(clause["label"], clause["text"]), clause["fields"], clause["text"])

    def test_parse_merges_clauses(self):
        result = parse("我周五要打工，每天早上送孩子，不想课之间等太久", keyword_label)
        self.assertEqual([c["label"] for c in result["clauses"]],
                         ["blocked_time", "blocked_time", "prefer_less_waiting"])
        self.assertEqual(write_block(result["conditions"]["unavailable_windows"]),
                         "Mon-Thu 0:00-10:00; Fri all")
        self.assertEqual(result["conditions"]["cares"], ["gap"])


if __name__ == "__main__":
    unittest.main()
