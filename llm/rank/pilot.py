"""Pilot: can a local Qwen 7B play a student and pick the better of two timetables consistently?

Each persona gets real candidate timetables from the snapshot (hard limits applied first).
Every pair is judged twice with A and B swapped; only answers that survive the swap would be
used as training labels. The same pairs are written to an answer sheet so team members can
make their own choices for comparison.

    python3 -m llm.rank.pilot            # 6 personas x 5 pairs, qwen2.5:7b
"""
from __future__ import annotations

import argparse
import html
import json
import random
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from uniplan.arrangement import arrange_timetables, candidate_from_ids  # noqa: E402
from uniplan.catalog import SnapshotCatalog  # noqa: E402
from uniplan.profile import prepare_student_profile  # noqa: E402
from uniplan.ranking import dated_meetings, pareto_front  # noqa: E402
from uniplan.timetable_data import load_timetable_data  # noqa: E402

DAYS = "一二三四五六日"
OUT = ROOT / "llm" / "rank" / "output"


def blocked(day: int, start: int, end: int) -> dict[str, int]:
    return {"weekday": day, "start_min": start, "end_min": end}


PERSONAS = [
    {"id": "commuter", "units": ("ENGG2112", "AMME2301"), "blocked": [],
     "text": "我住得很远，单程通勤 90 分钟。希望每周来学校的天数越少越好，一天课多一点、中间等一会儿都没关系。"},
    {"id": "friday_worker", "units": ("ENGG2112", "AMME2301"), "blocked": [blocked(5, 0, 1439)],
     "text": "我周五全天打工，所以周五不能有课。其他日子希望课排得紧凑，不想在学校干等，空档对我来说是浪费。"},
    {"id": "parent", "units": ("ENGG2112", "AMME2301"), "blocked": [blocked(day, 0, 570) for day in range(1, 6)],
     "text": "我每天早上要送孩子上学，九点半之前到不了学校；下午最好早点结束，四点以后的课越少越好。"},
    {"id": "night_owl", "units": ("ENGG2112", "AMME2301"), "blocked": [],
     "text": "我是夜猫子，早上起不来，最好十点以后再上课，晚一点下课没关系。"},
    {"id": "intern", "units": ("ENGG2112", "AMME2262", "CIVL3206"), "blocked": [],
     "text": "我在做实习，想把课集中在尽量少的几天，空出整天去上班。"},
    {"id": "near_campus", "units": ("ENGG2112", "AMME2262", "CIVL3206"), "blocked": [],
     "text": "我就住在学校旁边，不介意天天来。但我讨厌一天上很多课，也讨厌课和课之间等很久。"},
]

# Version 1 used A/B labels and long per-day text: 53% of answers survived the swap, mostly
# because the model mixed up which letter was which. Version 2 names the timetables 红/蓝,
# puts the numbers side by side, and asks for the deciding item before the choice.
METRICS = {"到校天数": "每周到校天数", "空等": "课间空等（小时/周）", "早晚课": "9 点前或 18 点后的课（分钟/周）",
           "最早": "最早上课", "最晚": "最晚下课"}
SYSTEM = ("你要扮演一位大学生，根据他自己的情况，从“红”“蓝”两份课表里选更适合他的一份。"
          "先说出对这位学生最重要的是哪一项（focus），再对照表格里这一项的数字说理由，"
          "最后给出选择：红、蓝，或者“差不多”（两份在他在意的地方几乎一样）。"
          "数字越小越好的项：到校天数、空等、早晚课。")
SCHEMA = {"type": "object", "properties": {
    "focus": {"type": "string", "enum": list(METRICS)},
    "reason": {"type": "string"}, "choice": {"type": "string", "enum": ["红", "蓝", "差不多"]}},
    "required": ["focus", "reason", "choice"]}


def clock(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def summary(meetings: list[dict], features: dict[str, float]) -> dict[str, str]:
    """The comparison numbers shown side by side in the version 2 prompt."""
    weeks = Counter((m["weekday"], m["start_min"], m["end_min"]) for m in meetings if not m["is_online"])
    routine = [slot for slot, count in weeks.items() if count >= 3]
    return {"到校天数": f"{features['campus_days']:.1f}", "空等": f"{features['gap_min'] / 60:.1f}",
            "早晚课": f"{features['outside_min']:.0f}",
            "最早": clock(min(s[1] for s in routine)) if routine else "-",
            "最晚": clock(max(s[2] for s in routine)) if routine else "-"}


def describe(meetings: list[dict], features: dict[str, float]) -> str:
    """The weekly routine (classes repeating in at least three weeks), one line per weekday."""
    weeks = Counter((m["weekday"], m["start_min"], m["end_min"], m["unit_code"],
                     m["group_id"].split("|")[-1], m["is_online"]) for m in meetings)
    routine = sorted(key for key, count in weeks.items() if count >= 3)
    lines = []
    for day in range(1, 8):
        today = [slot for slot in routine if slot[0] == day]
        if day > 5 and not today:
            continue
        lessons = "；".join(f"{clock(s)}–{clock(e)} {unit} {activity}{'（线上）' if online else ''}"
                           for _, s, e, unit, activity, online in today)
        lines.append(f"周{DAYS[day - 1]}：{lessons or '没课'}")
    campus = [slot for slot in routine if not slot[5]]
    span = (f"，最早 {clock(min(s[1] for s in campus))}，最晚 {clock(max(s[2] for s in campus))}"
            if campus else "")
    lines.append(f"合计：每周到校 {features['campus_days']:.1f} 天，课间空等 "
                 f"{features['gap_min'] / 60:.1f} 小时{span}")
    return "\n".join(lines)


def candidates(persona: dict, catalog: SnapshotCatalog) -> tuple[list[dict], list[dict]]:
    base = {"year": 2026, "session_code": "S2C", "unit_codes": list(persona["units"])}
    prepared = prepare_student_profile({**base, "unavailable_windows": persona["blocked"]}, catalog)
    profile = prepared["profile"]
    data = load_timetable_data(profile, prepared["snapshot_ref"], catalog)
    groups = {unit["unit_code"]: [group["group_id"] for group in unit["groups"] if group["default_selected"]]
              for unit in data.summary["units"]}
    ranking = arrange_timetables(data.meetings, groups, profile)
    pool = ranking["_pool"]
    for entry in pool:
        candidate = candidate_from_ids(entry["candidate_id"], entry["option_ids"], ranking["_options"])
        meetings = dated_meetings(candidate, profile)
        entry["text"] = describe(meetings, entry["features"])
        entry["summary"] = summary(meetings, entry["features"])
    return pool, pareto_front(pool)


def pairs_for(pool: list[dict], front: list[dict], count: int, rng: random.Random) -> list[tuple[dict, dict]]:
    """Mostly real trade-offs (both on the Pareto front), the rest random feasible pairs."""
    chosen: list[tuple[dict, dict]] = []
    seen = set()

    def add(a: dict, b: dict) -> None:
        key = frozenset((a["candidate_id"], b["candidate_id"]))
        if a is not b and key not in seen and a["text"] != b["text"]:
            seen.add(key)
            chosen.append((a, b) if rng.random() < 0.5 else (b, a))

    front_pairs = [(a, b) for i, a in enumerate(front) for b in front[i + 1:]]
    rng.shuffle(front_pairs)
    for a, b in front_pairs[:3]:
        add(a, b)
    for _ in range(200):
        if len(chosen) >= count:
            break
        add(*rng.sample(pool, 2))
    return chosen[:count]


def ask(model: str, persona: str, red: dict, blue: dict) -> dict:
    table = "\n".join(f"| {label} | {red['summary'][key]} | {blue['summary'][key]} |" for key, label in METRICS.items())
    user = (f"学生情况：{persona}\n\n| 项目 | 红 | 蓝 |\n| --- | --- | --- |\n{table}\n\n"
            f"红课表（每周固定的课）：\n{red['text'].rsplit(chr(10), 1)[0]}\n\n"
            f"蓝课表（每周固定的课）：\n{blue['text'].rsplit(chr(10), 1)[0]}")
    body = {"model": model, "stream": False, "format": SCHEMA, "options": {"temperature": 0, "num_predict": 250},
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]}
    request = urllib.request.Request("http://127.0.0.1:11434/api/chat", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.loads(json.loads(response.read())["message"]["content"])


def write_sheet(records: list[dict], path: Path) -> None:
    """A standalone page for team members to make the same 30 choices and download them."""
    blocks = []
    for index, record in enumerate(records):
        tables = "".join(f"<div class='tt'><h3>课表 {side}</h3><pre>{html.escape(text)}</pre></div>"
                         for side, text in (("A", record["a_text"]), ("B", record["b_text"])))
        radios = "".join(f"<label><input type='radio' name='q{index}' value='{value}'> {value}</label>"
                         for value in ("A", "B", "差不多"))
        blocks.append(f"<section><h2>{index + 1} / {len(records)}</h2><p class='who'>{html.escape(record['persona_text'])}</p>"
                      f"<div class='pair'>{tables}</div><div class='pick'>{radios}</div></section>")
    page = f"""<!doctype html><meta charset="utf-8"><title>课表二选一</title>
<style>body{{font:14px -apple-system,"PingFang SC",sans-serif;max-width:980px;margin:24px auto;padding:0 16px;color:#111}}
section{{border-top:1px solid #ddd;padding:14px 0}}h2{{font-size:14px;margin:0 0 6px}}.who{{margin:0 0 10px}}
.pair{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}h3{{font-size:13px;margin:0 0 4px}}
pre{{white-space:pre-wrap;margin:0;font:13px/1.6 inherit}}.pick{{margin-top:8px;display:flex;gap:18px}}
@media(max-width:700px){{.pair{{grid-template-columns:1fr}}}}</style>
<h1 style="font-size:18px">课表二选一（{len(records)} 题）</h1>
<p>请把自己当成每题写的那位学生，选出对他更合适的课表。做完点最下面的按钮下载答案。</p>
<p>你的名字缩写：<input id="who" size="6"></p>
{''.join(blocks)}
<p><button id="save">下载答案</button> <span id="left"></span></p>
<script>
const total = {len(records)};
document.getElementById("save").onclick = () => {{
  const answers = [];
  for (let i = 0; i < total; i++) {{
    const picked = document.querySelector(`input[name=q${{i}}]:checked`);
    answers.push(picked ? picked.value : null);
  }}
  const missing = answers.filter((a) => a === null).length;
  document.getElementById("left").textContent = missing ? `还有 ${{missing}} 题没选` : "";
  if (missing) return;
  const who = document.getElementById("who").value.trim() || "anon";
  const blob = new Blob([JSON.stringify({{who, answers}})], {{type: "application/json"}});
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `rank_pilot_answers_${{who}}.json`;
  link.click();
}};
</script>"""
    path.write_text(page, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default="qwen2.5:7b")
    parser.add_argument("--pairs", type=int, default=5, help="pairs per persona")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", default="rank_pilot_v2.json")
    args = parser.parse_args()
    rng = random.Random(args.seed)
    catalog = SnapshotCatalog(ROOT / "data/processed", ROOT / "data/requirements")
    OUT.mkdir(parents=True, exist_ok=True)

    records = []
    for persona in PERSONAS:
        pool, front = candidates(persona, catalog)
        pairs = pairs_for(pool, front, args.pairs, rng)
        print(f"{persona['id']}: {len(pool)} distinct timetables, {len(front)} on the front, {len(pairs)} pairs",
              flush=True)
        for a, b in pairs:
            records.append({"persona": persona["id"], "persona_text": persona["text"],
                            "a_id": a["candidate_id"], "b_id": b["candidate_id"],
                            "a_features": a["features"], "b_features": b["features"],
                            "a_text": a["text"], "b_text": b["text"],
                            "a_summary": a["summary"], "b_summary": b["summary"],
                            "both_on_front": a in front and b in front})
    write_sheet(records, OUT / "rank_pilot_sheet.html")

    started = time.time()
    for index, record in enumerate(records):
        a = {"text": record["a_text"], "summary": record["a_summary"]}
        b = {"text": record["b_text"], "summary": record["b_summary"]}
        forward = ask(args.model, record["persona_text"], a, b)   # red = A
        swapped = ask(args.model, record["persona_text"], b, a)   # red = B
        # Express both answers in terms of the original A/B.
        forward["choice"] = {"红": "A", "蓝": "B"}.get(forward["choice"], forward["choice"])
        swapped["choice"] = {"红": "B", "蓝": "A"}.get(swapped["choice"], swapped["choice"])
        record["forward"] = forward
        record["swapped"] = swapped
        record["swapped_as_original"] = swapped["choice"]
        record["consistent"] = forward["choice"] == swapped["choice"]
        print(f"{index + 1:2d}/{len(records)} {record['persona']:13s} first={forward['choice']:3s} "
              f"swapped={record['swapped_as_original']:3s} {'ok' if record['consistent'] else 'FLIP'}", flush=True)

    consistent = sum(record["consistent"] for record in records)
    # Which colour was picked, i.e. the first-listed (red) vs second (blue) position.
    first_slot = Counter({"A": "red", "B": "blue"}.get(r["forward"]["choice"], "tie") for r in records)
    first_slot.update({"B": "red", "A": "blue"}.get(r["swapped"]["choice"], "tie") for r in records)
    summary = {
        "model": args.model, "pairs": len(records), "consistent": consistent,
        "consistent_rate": round(consistent / len(records), 3),
        "answers_by_position": dict(first_slot),
        "consistent_on_front_pairs": f"{sum(r['consistent'] for r in records if r['both_on_front'])}/"
                                     f"{sum(r['both_on_front'] for r in records)}",
        "by_persona": {p["id"]: f"{sum(r['consistent'] for r in records if r['persona'] == p['id'])}/"
                                f"{sum(r['persona'] == p['id'] for r in records)}" for p in PERSONAS},
        "seconds": round(time.time() - started),
    }
    (OUT / args.out).write_text(json.dumps({"summary": summary, "records": records},
                                                    ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
