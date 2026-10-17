"""80 synthetic student personas for the ranking block (and, later, the parsing block).

SYNTHETIC: every sentence and every condition below was written by Claude (an LLM) for
this project. None of it comes from a real student. personas.json says the same.

Each persona is one sentence plus the conditions that sentence implies, in the
llm.contracts.Conditions format. The rules used to write the gold conditions:
- A specific time or day the student cannot attend ("不能", "没法", "到不了") is a hard
  ``unavailable_windows`` entry (weekdays 1-5 unless the sentence says otherwise).
- "最好 / 越少越好" with a specific time is soft: ``preferred_hours`` plus the
  ``outside_hours`` care. An unstated end is 18:00 and an unstated start is 09:00
  (the scheduler's defaults). A general dislike of early or late classes, with no time,
  is the ``outside_hours`` care alone.
- An explicit number is a hard limit: days per week (``max_days_per_week``), class hours
  per day (``max_daily_minutes``), hours on campus per day (``max_daily_span``), lunch.
- ``cares`` is ordered by importance; ``cares[0]`` is the persona's main concern
  ("focus"), which the labelling program uses for its tie rule.
- Wishes outside the contract (e.g. "不想为一节课专门跑一趟") stay in the sentence only;
  the teacher model reads them, the gold conditions do not contain them.

    python3 -m llm.rank.personas      # write llm/rank/data/personas.json and check each one
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "llm" / "rank" / "data" / "personas.json"
WEEKDAYS = (1, 2, 3, 4, 5)
SEED = 2112

A = ("ENGG2112", "AMME2301")
B = ("ENGG2112", "AMME1362")
C = ("AMME2301", "AMME1362")
D = ("AMME2262", "AMME1362")
E = ("CIVL3206", "AMME1362")
G = ("ENGG2112", "AMME2301", "AMME2262")
I = ("ENGG2112", "AMME2262", "AMME1362")
J = ("ENGG2112", "CIVL3206", "AMME1362")
K = ("ENGG2112", "AMME1362", "MTRX3700")
L = ("AMME2301", "AMME1362", "MTRX1705")
M = ("AMME1362", "MTRX1705")
P = ("AMME2301", "CIVL3206", "AMME1362")
PILOT = ("ENGG2112", "AMME2262", "CIVL3206")    # the pilot's intern and near-campus units


def h(clock: str) -> int:
    hours, _, minutes = clock.partition(":")
    return int(hours) * 60 + int(minutes or 0)


def block(days, start: str = "0", end: str = "24") -> list[dict]:
    return [{"weekday": day, "start_min": h(start), "end_min": h(end)} for day in days]


def hours(start: str = "9", end: str = "18") -> dict:
    return {"weekday": 0, "start_min": h(start), "end_min": h(end)}


def lunch(start: str, end: str, minutes: int) -> dict:
    return {"start_min": h(start), "end_min": h(end), "minutes": minutes}


# (type, units, sentence, conditions). Order inside a type is the persona number.
SPECS = [
    # ---- commuter: lives far away ----
    ("commuter", A, "我住得很远，单程通勤 90 分钟。希望每周来学校的天数越少越好，一天课多一点、中间等一会儿都没关系。",
     {"cares": ["campus_days"]}),
    ("commuter", B, "我从中央海岸坐火车来学校，单程两个小时，想尽量少来几天；来的那天最好十点以后再上课。",
     {"preferred_hours": hours("10", "18"), "cares": ["campus_days", "outside_hours"]}),
    ("commuter", A, "我住在彭里斯，开车过来要一个多小时还要找车位，每周最多来三天，能更少就更好。",
     {"max_days_per_week": 3, "cares": ["campus_days"]}),
    ("commuter", C, "我住在卧龙岗，通勤来回四个小时，希望课都挤在少数几天里，中间有空档我可以去图书馆自习。",
     {"cares": ["campus_days"]}),
    ("commuter", G, "我每天坐轮渡再转公交来学校，单程一个半小时，最在意少跑几趟，其次希望别在学校干等太久。",
     {"cares": ["campus_days", "gap"]}),
    ("commuter", B, "我家在郊区，回家的直达巴士最晚一班是晚上六点半，所以六点以后不能有课；另外希望来学校的天数少一点。",
     {"unavailable_windows": block(WEEKDAYS, "18"), "cares": ["campus_days"]}),
    ("commuter", C, "我住得远，周一和周五都没有直达的车，这两天没法来学校；其他日子希望来的天数越少越好。",
     {"unavailable_windows": block((1, 5)), "cares": ["campus_days"]}),
    ("commuter", G, "我住在一个半小时车程外，希望少来几天，但一天在学校也不能待超过九个小时。",
     {"max_daily_span": h("9"), "cares": ["campus_days"]}),

    # ---- worker: part-time job ----
    ("worker", A, "我周五全天打工，所以周五不能有课。其他日子希望课排得紧凑，不想在学校干等，空档对我来说是浪费。",
     {"unavailable_windows": block((5,)), "cares": ["gap"]}),
    ("worker", B, "我周二和周四下午两点以后要去咖啡店上班，这两个时间段不能排课；希望课和课之间别空太久。",
     {"unavailable_windows": block((2, 4), "14"), "cares": ["gap"]}),
    ("worker", D, "我每周一、三、五下午五点以后在餐厅打工，那几天五点后不能有课；我最在意少来几天学校。",
     {"unavailable_windows": block((1, 3, 5), "17"), "cares": ["campus_days"]}),
    ("worker", B, "我周三和周末全天在超市上班，周三不能来学校；其余时间希望空档越少越好，其次少跑几天。",
     {"unavailable_windows": block((3, 6, 7)), "cares": ["gap", "campus_days"]}),
    ("worker", B, "我工作日每天早上七点到十一点在面包店打工，十一点前没法上课；希望课排得紧一点。",
     {"unavailable_windows": block(WEEKDAYS, "0", "11"), "cares": ["gap"]}),
    ("worker", G, "我在做家教，周二、周四晚上六点以后要给学生上课，那两晚不能排课；另外我不喜欢太早或太晚的课。",
     {"unavailable_windows": block((2, 4), "18"), "cares": ["outside_hours"]}),
    ("worker", A, "我周一、周二上午九点到下午一点在药房兼职，这段时间不能有课；我希望一周来学校的天数少一点。",
     {"unavailable_windows": block((1, 2), "9", "13"), "cares": ["campus_days"]}),
    ("worker", K, "我晚上在酒吧打工到很晚，所以早上十点之前不能有课；课最好排得紧凑一些，中间别等太久。",
     {"unavailable_windows": block(WEEKDAYS, "0", "10"), "cares": ["gap"]}),

    # ---- parent: looks after children ----
    ("parent", A, "我每天早上要送孩子上学，九点半之前到不了学校；下午最好早点结束，四点以后的课越少越好。",
     {"unavailable_windows": block(WEEKDAYS, "0", "9:30"), "preferred_hours": hours("9:30", "16"),
      "cares": ["outside_hours"]}),
    ("parent", E, "我下午五点要去接孩子放学，周一到周五四点半以后都不能有课；也希望来学校的天数少一些。",
     {"unavailable_windows": block(WEEKDAYS, "16:30"), "cares": ["campus_days"]}),
    ("parent", C, "我一个人带两个孩子，最好课都在早上九点到下午四点之间；能少来几天更好。",
     {"preferred_hours": hours("9", "16"), "cares": ["outside_hours", "campus_days"]}),
    ("parent", A, "我女儿每周三下午有课外班要我接送，周三下午一点以后不能有课；其他时候希望课间别空太多。",
     {"unavailable_windows": block((3,), "13"), "cares": ["gap"]}),
    ("parent", D, "我要照顾刚出生的宝宝，晚上必须在家，下午五点以后不能上课；白天希望课尽量集中在少数几天。",
     {"unavailable_windows": block(WEEKDAYS, "17"), "cares": ["campus_days"]}),
    ("parent", B, "孩子放学后需要我看着，最好下午三点半前就能离开学校；早上九点以后上课没问题。",
     {"preferred_hours": hours("9", "15:30"), "cares": ["outside_hours"]}),
    ("parent", C, "我每天八点半送孩子去学校，九点之前到不了学校；下午最好五点前结束，中间也少等一点。",
     {"unavailable_windows": block(WEEKDAYS, "0", "9"), "preferred_hours": hours("9", "17"),
      "cares": ["outside_hours", "gap"]}),
    ("parent", B, "我周二和周四要带孩子去做康复训练，这两天中午十二点以后都不能来；其他日子课排得紧凑就行。",
     {"unavailable_windows": block((2, 4), "12"), "cares": ["gap"]}),

    # ---- night owl ----
    ("night_owl", A, "我是夜猫子，早上起不来，最好十点以后再上课，晚一点下课没关系。",
     {"preferred_hours": hours("10", "21"), "cares": ["outside_hours"]}),
    ("night_owl", B, "我习惯晚睡，上午的课对我很痛苦，最好十一点以后才开始上课，下课到晚上七点都可以。",
     {"preferred_hours": hours("11", "19"), "cares": ["outside_hours"]}),
    ("night_owl", G, "我晚上精神最好，早上九点的课基本起不来，最好别有十点前的课；另外别让我在学校干等。",
     {"preferred_hours": hours("10", "18"), "cares": ["outside_hours", "gap"]}),
    ("night_owl", B, "我是夜猫子，早上实在起不来，上午十点前没法上课；希望来学校的天数少一点。",
     {"unavailable_windows": block(WEEKDAYS, "0", "10"), "cares": ["campus_days"]}),
    ("night_owl", K, "我常常熬夜做项目，最好十点半以后再上课，晚上八点前下课都行；课间等一下没关系。",
     {"preferred_hours": hours("10:30", "20"), "cares": ["outside_hours"]}),
    ("night_owl", I, "我睡得晚，最怕早上八九点的课，最好第一节课在十点以后；同时也不想每天都来学校。",
     {"preferred_hours": hours("10", "18"), "cares": ["outside_hours", "campus_days"]}),
    ("night_owl", C, "我每天中午才真正清醒，最好中午十二点以后再上课，晚到七点下课也没关系。",
     {"preferred_hours": hours("12", "19"), "cares": ["outside_hours"]}),
    ("night_owl", J, "我习惯晚上学习，最好别在十点前上课，也最好晚上七点前下课；空档多一点我也能接受。",
     {"preferred_hours": hours("10", "19"), "cares": ["outside_hours"]}),

    # ---- intern ----
    ("intern", PILOT, "我在做实习，想把课集中在尽量少的几天，空出整天去上班。",
     {"cares": ["campus_days"]}),
    ("intern", A, "我在一家工程公司实习，每周四、周五全天在公司，这两天不能有课；其他日子希望来的天数越少越好。",
     {"unavailable_windows": block((4, 5)), "cares": ["campus_days"]}),
    ("intern", A, "我在银行实习，公司要求每周至少上三天班，所以我每周最多只能来学校三天，来的那几天课间别空太久。",
     {"max_days_per_week": 3, "cares": ["gap"]}),
    ("intern", B, "我每周五要去公司实习，周一上午还要开例会，周五全天和周一中午十二点前都不能来学校；希望课排紧凑，别有大空档。",
     {"unavailable_windows": block((1,), "0", "12") + block((5,)), "cares": ["gap"]}),
    ("intern", I, "我在律所做兼职实习，每周想空出两个完整的工作日，最多来学校三天，越少越好。",
     {"max_days_per_week": 3, "cares": ["campus_days"]}),
    ("intern", P, "我在一家初创公司远程实习，时间比较自由，但希望每周到校天数少，而且不想在学校等太久。",
     {"cares": ["campus_days", "gap"]}),
    ("intern", C, "我在医院做实习，周五全天和周三中午十二点前都要在医院，这些时间不能有课；最好来学校的天数少。",
     {"unavailable_windows": block((3,), "0", "12") + block((5,)), "cares": ["campus_days"]}),
    ("intern", G, "我每周要做二十小时的实习，希望来学校的天数尽量少，课多一点也行，但一天上课不能超过六个小时。",
     {"max_daily_minutes": h("6"), "cares": ["campus_days"]}),

    # ---- near campus ----
    ("near_campus", PILOT, "我就住在学校旁边，不介意天天来。但我讨厌一天上很多课，也讨厌课和课之间等很久。",
     {"cares": ["gap"]}),
    ("near_campus", B, "我住在学校对面的宿舍，走路五分钟，来几次都无所谓，只希望课与课之间不要有很长的空档。",
     {"cares": ["gap"]}),
    ("near_campus", C, "我住在 Newtown，骑车十分钟到学校，最怕一天里两节课之间干等两三个小时；早晚课也尽量少一些。",
     {"cares": ["gap", "outside_hours"]}),
    ("near_campus", A, "我住校，每天都在学校，希望每天的课都别太多，一天最多上四个小时课，课间也别等太久。",
     {"max_daily_minutes": h("4"), "cares": ["gap"]}),
    ("near_campus", G, "我家离学校很近，可以天天来，但中午十二点到一点半之间要留出至少半小时吃饭，其余时间希望课排得紧一点。",
     {"lunch": lunch("12", "13:30", 30), "cares": ["gap"]}),
    ("near_campus", I, "我住在学校附近，喜欢每天来一点，不想某一天从早待到晚，一天在学校最多八个小时；空档少一点更好。",
     {"max_daily_span": h("8"), "cares": ["gap"]}),
    ("near_campus", K, "我住得很近，来学校很方便，最在意的是别有太早或太晚的课，空档无所谓。",
     {"cares": ["outside_hours"]}),
    ("near_campus", J, "我住学校附近，要回宿舍做饭，希望课之间不要空太久，最好也不用为了一节课专门跑一趟。",
     {"cares": ["gap"]}),

    # ---- early bird / busy evenings ----
    ("early_bird", D, "我习惯早睡早起，早上八点上课完全没问题，但最好下午三点前就能下课。",
     {"preferred_hours": hours("8", "15"), "cares": ["outside_hours"]}),
    ("early_bird", B, "我每天晚上要去健身房当教练，最好下午五点前结束所有课，早上八点的课也没关系。",
     {"preferred_hours": hours("8", "17"), "cares": ["outside_hours"]}),
    ("early_bird", I, "我是早起型的人，最喜欢上午上课，最好下午两点以后的课越少越好；也希望少来几天。",
     {"preferred_hours": hours("8", "14"), "cares": ["outside_hours", "campus_days"]}),
    ("early_bird", A, "我每周一到周四晚上六点以后在社区中心做志愿者，那几天六点以后不能有课；希望课间空等少一些。",
     {"unavailable_windows": block((1, 2, 3, 4), "18"), "cares": ["gap"]}),
    ("early_bird", J, "我住在家里，晚饭前要回家帮忙，最好每天四点前下课；早上八点半的课也可以接受。",
     {"preferred_hours": hours("8:30", "16"), "cares": ["outside_hours"]}),
    ("early_bird", L, "我早上精神好，晚上效率低，最好课都在早上八点到下午三点之间，能少等就少等。",
     {"preferred_hours": hours("8", "15"), "cares": ["outside_hours", "gap"]}),
    ("early_bird", G, "我晚上要学一门语言课，周二和周四下午五点以后不能来学校上课；其他时间早晚课越少越好。",
     {"unavailable_windows": block((2, 4), "17"), "cares": ["outside_hours"]}),
    ("early_bird", M, "我平时早上六点就起床，最好课都在下午四点前结束，早上八点开始也行，课集中在几天也好。",
     {"preferred_hours": hours("8", "16"), "cares": ["outside_hours", "campus_days"]}),

    # ---- athlete / club training ----
    ("athlete", K, "我是校划船队的，周一、周三、周五早上要训练，这三天九点前不能有课；其余希望课排得紧凑。",
     {"unavailable_windows": block((1, 3, 5), "0", "9"), "cares": ["gap"]}),
    ("athlete", A, "我参加校足球队，周二和周四下午四点以后要训练，不能有课；另外希望来学校的天数越少越好。",
     {"unavailable_windows": block((2, 4), "16"), "cares": ["campus_days"]}),
    ("athlete", C, "我是游泳队的，工作日每天早上七点到九点训练，九点前没法上课；我还希望一周的空等时间少一点。",
     {"unavailable_windows": block(WEEKDAYS, "0", "9"), "cares": ["gap"]}),
    ("athlete", B, "我在学校乐团，每周三下午两点到五点要排练，这段时间不能上课；其他时候不在意早晚，只希望少跑几天。",
     {"unavailable_windows": block((3,), "14", "17"), "cares": ["campus_days"]}),
    ("athlete", D, "我打篮球校队，周一和周四下午五点以后要训练或比赛，不能有课；课间等太久我会很烦。",
     {"unavailable_windows": block((1, 4), "17"), "cares": ["gap"]}),
    ("athlete", K, "我是戏剧社的，周二晚上六点以后和周五中午十二点以后都要排练，不能有课；希望早晚课少一些。",
     {"unavailable_windows": block((2,), "18") + block((5,), "12"), "cares": ["outside_hours"]}),
    ("athlete", E, "我在练田径，工作日每天下午四点以后要训练，所以四点以后不能有课；希望空档少一点。",
     {"unavailable_windows": block(WEEKDAYS, "16"), "cares": ["gap"]}),
    ("athlete", I, "我参加校羽毛球队，周三下午整个下午都要训练，周三下午一点以后不能有课；我还希望来学校的天数少。",
     {"unavailable_windows": block((3,), "13"), "cares": ["campus_days"]}),

    # ---- carer / health ----
    ("carer", B, "我要照顾生病的妈妈，每天在学校的时间不能超过六个小时；希望课排紧一点，别有空档。",
     {"max_daily_span": h("6"), "cares": ["gap"]}),
    ("carer", A, "我有慢性病，体力有限，一天最多上三个小时课，但不介意多来几天，只要课间别等太久。",
     {"max_daily_minutes": h("3"), "cares": ["gap"]}),
    ("carer", C, "我身体不太好，中午十二点到两点之间一定要留出至少一个小时休息吃饭；另外早上九点前和晚上六点后的课越少越好。",
     {"lunch": lunch("12", "14", 60), "preferred_hours": hours("9", "18"), "cares": ["outside_hours"]}),
    ("carer", G, "我腿受过伤，走路慢，不想一天在学校来回跑很久，一天在学校最多七个小时，来的天数少一点更好。",
     {"max_daily_span": h("7"), "cares": ["campus_days"]}),
    ("carer", C, "我每周二上午要去医院复诊，周二中午十二点前不能有课；其他时候希望课排得紧凑、空档少。",
     {"unavailable_windows": block((2,), "0", "12"), "cares": ["gap"]}),
    ("carer", D, "我需要照顾弟弟妹妹，工作日每天下午四点前要离开学校，所以四点以后不能有课；希望少来几天。",
     {"unavailable_windows": block(WEEKDAYS, "16"), "cares": ["campus_days"]}),
    ("carer", K, "我一天里如果空等太久会很焦虑，所以最在意课间空档少，早晚课无所谓。",
     {"cares": ["gap"]}),
    ("carer", I, "我每天要按时吃药休息，中午十一点半到一点半之间要空出至少半小时；我还希望每周少来几天。",
     {"lunch": lunch("11:30", "13:30", 30), "cares": ["campus_days"]}),

    # ---- other needs: in-person only, lunch, exchange... ----
    ("other", A, "我是国际学生，想多和同学交流，希望所有课都是线下的，不要线上课；空档少一点更好。",
     {"in_person_only": True, "cares": ["gap"]}),
    ("other", B, "我不喜欢线上课，只要现场上课；每周最多来四天，越少越好。",
     {"in_person_only": True, "max_days_per_week": 4, "cares": ["campus_days"]}),
    ("other", I, "我是大一新生，不在乎来几天，但最好少一些早上九点前和晚上六点后的课。",
     {"preferred_hours": hours("9", "18"), "cares": ["outside_hours"]}),
    ("other", B, "我在准备雅思，周二、周四晚上在校外上课，这两天下午六点以后不能有课；其他时间希望空档少。",
     {"unavailable_windows": block((2, 4), "18"), "cares": ["gap"]}),
    ("other", C, "我一边读书一边在家里的店帮忙，每周最多来三天，越少越好，课间等久一点没关系。",
     {"max_days_per_week": 3, "cares": ["campus_days"]}),
    ("other", B, "我希望中午十二点到两点之间能空出一个小时吃饭，另外少来几天，课和课之间也别空太久。",
     {"lunch": lunch("12", "14", 60), "cares": ["campus_days", "gap"]}),
    ("other", G, "我是交换生，周五想出去旅行，周五不能有课；另外早课和晚课越少越好。",
     {"unavailable_windows": block((5,)), "cares": ["outside_hours"]}),
    ("other", D, "我住在寄宿家庭，晚饭六点开始，最好五点半前下课；课间也别等太久。",
     {"preferred_hours": hours("9", "17:30"), "cares": ["outside_hours", "gap"]}),
]

TYPES = ("commuter", "worker", "parent", "night_owl", "intern", "near_campus",
         "early_bird", "athlete", "carer", "other")
# The six pilot personas (llm/rank/pilot.py) keep their sentences; they are prompt-design
# data, so they always go to the training split.
PILOT_IDS = {"commuter": "commuter_1", "friday_worker": "worker_1", "parent": "parent_1",
             "night_owl": "night_owl_1", "intern": "intern_1", "near_campus": "near_campus_1"}
TEST_PER_TYPE = 2


def build() -> list[dict]:
    personas, counts = [], {}
    for kind, units, text, conditions in SPECS:
        counts[kind] = counts.get(kind, 0) + 1
        personas.append({"id": f"{kind}_{counts[kind]}", "type": kind, "units": list(units), "text": text,
                         "conditions": conditions, "focus": conditions["cares"][0], "synthetic": True})
    # Fixed train/test split by persona, decided before any labelling: two per type.
    rng = random.Random(SEED)
    pilot = set(PILOT_IDS.values())
    for kind in TYPES:
        pickable = [p for p in personas if p["type"] == kind and p["id"] not in pilot]
        test = {p["id"] for p in rng.sample(pickable, TEST_PER_TYPE)}
        for persona in personas:
            if persona["type"] == kind:
                persona["split"] = "test" if persona["id"] in test else "train"
    return personas


def load() -> list[dict]:
    return json.loads(DATA.read_text(encoding="utf-8"))["personas"]


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from llm.rank.pool import persona_pool   # uniplan is only needed for the check

    personas = build()
    assert len(personas) == 80 and all(sum(p["type"] == t for p in personas) == 8 for t in TYPES)
    problems = 0
    for persona in personas:
        pool = persona_pool(persona)
        persona["pool_size"] = len(pool)
        flag = "" if len(pool) >= 8 else "  <-- too few"
        problems += bool(flag)
        print(f"{persona['id']:15s} {persona['split']:5s} {persona['focus']:13s} {len(pool):5d}{flag}", flush=True)
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps({
        "note": "合成数据（SYNTHETIC）：80 个学生画像的句子和条件都由 Claude 为本项目编写，不是真实学生的数据。"
                "conditions 按 llm/contracts.py 的 Conditions 格式；cares 按重要性排序，cares[0] 即 focus。"
                "split 在打标签之前用固定种子划分，每类 2 个测试画像，之后不改。",
        "generated_by": "llm/rank/personas.py", "seed": SEED, "personas": personas,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {DATA.relative_to(ROOT)}; {problems} persona(s) with fewer than 8 timetables")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
