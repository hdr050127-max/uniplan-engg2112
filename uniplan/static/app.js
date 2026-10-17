"use strict";

/* ===================== basics ===================== */

const $ = (id) => document.getElementById(id);
const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};
const SVG_NS = "http://www.w3.org/2000/svg";
const svgEl = (tag, attrs = {}) => {
  const node = document.createElementNS(SVG_NS, tag);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
  return node;
};

function button(label, handler, { className = "button", title = null } = {}) {
  const node = el("button", className, label);
  node.type = "button";
  if (title) {
    node.title = title;
    node.setAttribute("aria-label", title);
  }
  node.addEventListener("click", () => handler(node));
  return node;
}

const DAY = ["一", "二", "三", "四", "五", "六", "日"];
const AXES = ["campus_days", "gap", "outside_hours"];
const AXIS_FEATURE = { gap: "gap_min", campus_days: "campus_days", outside_hours: "outside_min" };
const AXIS_CHIP = { campus_days: "少到校", gap: "少空等", outside_hours: "少早晚课" };
const AXIS_TAG = { campus_days: "到校最少", gap: "空等最少", outside_hours: "早晚课最少" };
const PRESETS = {
  mon: { label: "周一全天", windows: [[1, 0, 1439]] },
  fri: { label: "周五全天", windows: [[5, 0, 1439]] },
  early: { label: "10 点前", windows: [1, 2, 3, 4, 5].map((day) => [day, 0, 600]) },
  late: { label: "18 点后", windows: [1, 2, 3, 4, 5].map((day) => [day, 1080, 1439]) },
};
const STUDY_MODE = new URLSearchParams(location.search).has("study");
const LETTERS = "ABCDEFGHIJKL";
const NOW = new Date();
const TODAY = `${NOW.getFullYear()}-${String(NOW.getMonth() + 1).padStart(2, "0")}-${String(NOW.getDate()).padStart(2, "0")}`;
const NOW_MIN = NOW.getHours() * 60 + NOW.getMinutes();

const state = {
  units: [], blocks: [], matches: [], activeMatch: -1, searchRevision: 0,
  busy: false, data: null, groups: null, pinned: {}, excluded: [], result: null,
  cares: new Set(AXES), selected: null, variant: {}, week: {}, routeDay: {},
  tab: "week", enrolled: {}, friend: null, notice: "", compare: [], history: [],
  sharedPlan: null, participant: null, firstInteraction: null,
  say: null, view: "all", reasons: {},
};

function minutes(value) {
  if (!/^\d{2}:\d{2}$/.test(value || "")) return null;
  const [hour, minute] = value.split(":").map(Number);
  return hour <= 23 && minute <= 59 ? hour * 60 + minute : null;
}

function clock(value) {
  return `${String(Math.floor(value / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`;
}

function term() {
  const [year, session_code] = $("termSelect").value.split("|");
  return { year: Number(year), session_code };
}

function groupName(id) {
  const parts = id.split("|");
  return parts.length >= 2 ? `${parts[0].split("-")[0]} ${parts[parts.length - 1]}` : id;
}

function activityOf(meeting) {
  return (meeting.group_id || "").split("|").pop();
}

function daysText(pattern) {
  return pattern ? `周${[...pattern].map((day) => DAY[Number(day) - 1]).join("")}` : "无固定到校日";
}

function hoursText(minutesPerWeek) {
  return minutesPerWeek >= 60 ? `${(minutesPerWeek / 60).toFixed(1)} 小时` : `${Math.round(minutesPerWeek)} 分钟`;
}

function addDays(isoDate, days) {
  const day = new Date(`${isoDate}T00:00:00Z`);
  day.setUTCDate(day.getUTCDate() + days);
  return day.toISOString().slice(0, 10);
}

function daysBetween(from, to) {
  return Math.round((new Date(`${to}T00:00:00Z`) - new Date(`${from}T00:00:00Z`)) / 86400000);
}

function weekdayOf(isoDate) {
  return ((new Date(`${isoDate}T00:00:00Z`).getUTCDay() + 6) % 7) + 1;
}

function shortDate(isoDate) {
  return `${Number(isoDate.slice(5, 7))}/${Number(isoDate.slice(8, 10))}`;
}

function elapsedMs() {
  return state.firstInteraction === null ? null : Math.round(performance.now() - state.firstInteraction);
}

function setError(id, message) {
  $(id).textContent = message || "";
}

let toastTimer = null;
function toast(message) {
  const box = $("toast");
  box.textContent = message;
  box.hidden = false;
  requestAnimationFrame(() => requestAnimationFrame(() => box.classList.add("show")));
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    box.classList.remove("show");
    toastTimer = setTimeout(() => { box.hidden = true; }, 220);
  }, 2400);
}

/* ===================== theme ===================== */

function storedTheme() {
  try {
    return localStorage.getItem("uniplan:theme");
  } catch {
    return null;
  }
}

function applyTheme() {
  // A saved choice wins; otherwise follow the system setting.
  const dark = (storedTheme() || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")) === "dark";
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  $("themeToggle").textContent = dark ? "浅色" : "深色";
}

function toggleTheme() {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  try {
    localStorage.setItem("uniplan:theme", next);
  } catch {
    document.documentElement.dataset.theme = next;
  }
  applyTheme();
}

/* ===================== courses ===================== */

function hideSuggestions() {
  $("suggestions").hidden = true;
  $("unitQuery").setAttribute("aria-expanded", "false");
  state.activeMatch = -1;
}

function renderSuggestions() {
  const list = $("suggestions");
  list.replaceChildren();
  if (!state.matches.length) {
    hideSuggestions();
    return;
  }
  state.matches.forEach((item, index) => {
    const li = el("li");
    li.setAttribute("role", "option");
    li.setAttribute("aria-selected", String(index === state.activeMatch));
    const choice = el("button", index === state.activeMatch ? "active" : "");
    choice.type = "button";
    choice.append(el("span", "suggest-code", item.unit_code), el("span", "suggest-name", item.unit_name));
    if (!item.available_in_snapshot) choice.append(el("span", "suggest-note", "暂无课表数据"));
    choice.addEventListener("click", () => addUnit(item.unit_code, item.unit_name));
    li.append(choice);
    list.append(li);
  });
  list.hidden = false;
  $("unitQuery").setAttribute("aria-expanded", "true");
}

async function searchUnits() {
  const query = $("unitQuery").value.trim();
  const revision = ++state.searchRevision;
  if (query.length < 2 || !$("termSelect").value) {
    state.matches = [];
    hideSuggestions();
    return;
  }
  const { year, session_code } = term();
  try {
    const response = await fetch(`/api/suggest?q=${encodeURIComponent(query)}&year=${year}&session_code=${encodeURIComponent(session_code)}`);
    const data = await response.json();
    if (revision !== state.searchRevision || $("unitQuery").value.trim() !== query) return;
    state.matches = data.suggestions || [];
    state.activeMatch = -1;
    renderSuggestions();
  } catch {
    if (revision === state.searchRevision) hideSuggestions();
  }
}

function renderUnits() {
  const box = $("chosenUnits");
  box.replaceChildren();
  state.units.forEach((unit) => {
    const chip = el("span", "chip");
    chip.style.setProperty("--c", `var(--c${courseIndex(unit.code)})`);
    chip.append(el("i", "dot"), el("strong", "", unit.code));
    if (unit.name) chip.append(el("span", "", unit.name));
    const remove = el("button", "", "×");
    remove.type = "button";
    remove.setAttribute("aria-label", `移除 ${unit.code}`);
    remove.addEventListener("click", () => {
      state.units = state.units.filter((other) => other.code !== unit.code);
      renderUnits();
    });
    chip.append(remove);
    box.append(chip);
  });
  $("unitQuery").placeholder = state.units.length ? (state.units.length >= 5 ? "最多 5 门" : "继续添加") : "输入课程代码，如 ENGG2112";
}

function addUnit(code, name = "") {
  code = code.trim().toUpperCase();
  if (!/^[A-Z]{4}\d{4}$/.test(code)) {
    setError("unitError", "课程代码应为 4 个字母加 4 个数字");
    return false;
  }
  if (state.units.some((unit) => unit.code === code)) {
    setError("unitError", `${code} 已添加`);
    return false;
  }
  if (state.units.length >= 5) {
    setError("unitError", "最多 5 门课");
    return false;
  }
  const unit = { code, name };
  state.units.push(unit);
  if (!name) {
    fetch(`/api/suggest?q=${encodeURIComponent(code)}`).then((response) => response.json()).then((data) => {
      const exact = (data.suggestions || []).find((item) => item.unit_code === code);
      if (exact && !unit.name) {
        unit.name = exact.unit_name;
        renderUnits();
      }
    }).catch(() => {});
  }
  $("unitQuery").value = "";
  setError("unitError", "");
  state.matches = [];
  state.searchRevision += 1; // ignore answers to searches typed before this course was added
  hideSuggestions();
  renderUnits();
  return true;
}

/* ===================== times to avoid ===================== */

function renderBlocks() {
  const box = $("blocks");
  box.replaceChildren();
  state.blocks.forEach((block) => {
    const token = el("span", "token", block.label);
    const remove = el("button", "", "×");
    remove.type = "button";
    remove.setAttribute("aria-label", `删除 ${block.label}`);
    remove.addEventListener("click", () => {
      state.blocks = state.blocks.filter((other) => other !== block);
      renderBlocks();
    });
    token.append(remove);
    box.append(token);
  });
  // A preset is hidden once its times are already avoided (e.g. Friday from the sentence).
  const avoided = state.blocks.flatMap((block) => block.windows);
  document.querySelectorAll(".preset[data-preset]").forEach((preset) => {
    preset.hidden = state.blocks.some((block) => block.key === preset.dataset.preset) ||
      PRESETS[preset.dataset.preset].windows.every(([weekday, start, end]) => avoided.some((w) =>
        w.weekday === weekday && w.start_min <= start && w.end_min >= end));
  });
}

function addBlock(key, label, windows) {
  if (key && state.blocks.some((block) => block.key === key)) return;
  state.blocks.push({ key, label, windows: windows.map(([weekday, start_min, end_min]) => ({ weekday, start_min, end_min })) });
  renderBlocks();
}

function addCustomBlock() {
  const day = Number($("customDay").value);
  const start = minutes($("customStart").value);
  const end = minutes($("customEnd").value);
  if (start === null || end === null || start >= end) {
    setError("windowError", "结束时间要晚于开始时间");
    return;
  }
  setError("windowError", "");
  addBlock(null, `周${DAY[day - 1]} ${clock(start)}–${clock(end)}`, [[day, start, end]]);
}

/* ===================== settings ===================== */

const SETTING_FIELDS = ["preferredStart", "preferredEnd", "maxDaily", "maxSpan", "lunchStart", "lunchEnd",
  "lunchMinutes", "maxDays", "commute", "transition", "walkSpeed", "minSeats"];
const SETTING_CHECKS = ["lunchOn", "inPerson"];

function fillTimes(select, from, to, value) {
  for (let minute = from; minute <= to; minute += 30) {
    const option = el("option", "", clock(minute));
    option.value = clock(minute);
    select.append(option);
  }
  select.value = value;
}

function setField(id, value) {
  // Old share links may carry times that are not on the half-hour list.
  const field = $(id);
  if (field.tagName === "SELECT" && value !== "" && ![...field.options].some((option) => option.value === value)) {
    const extra = el("option", "", value);
    extra.value = value;
    field.append(extra);
  }
  field.value = value;
}

function syncSegmented() {
  document.querySelectorAll(".segmented[data-target]").forEach((group) => {
    const value = $(group.dataset.target).value;
    group.querySelectorAll("button").forEach((choice) => {
      const on = choice.dataset.value === value;
      choice.classList.toggle("on", on);
      choice.setAttribute("aria-pressed", String(on));
    });
  });
}

function numberOrNull(id) {
  const raw = $(id).value.trim();
  return raw === "" ? null : Number(raw);
}

function readSettings() {
  // Empty values mean "no limit"; only chosen ones are sent.
  const settings = {};
  const daily = numberOrNull("maxDaily");
  const span = numberOrNull("maxSpan");
  if (daily) settings.max_daily_minutes = Math.round(daily * 60);
  if (span) settings.max_daily_span = Math.round(span * 60);
  if ($("maxDays").value) settings.max_days_per_week = Number($("maxDays").value);
  if ($("lunchOn").checked) {
    settings.lunch = { start_min: minutes($("lunchStart").value), end_min: minutes($("lunchEnd").value),
      minutes: Number($("lunchMinutes").value || 30) };
  }
  if ($("walkSpeed").value) settings.walk_speed = Number($("walkSpeed").value);
  if ($("inPerson").checked) settings.in_person_only = true;
  const seats = numberOrNull("minSeats");
  if (seats) settings.min_seats = seats;
  return settings;
}

function settingsCount() {
  const preferredChanged = $("preferredStart").value !== "09:00" || $("preferredEnd").value !== "18:00";
  return Object.keys(readSettings()).length + (preferredChanged ? 1 : 0) +
    (numberOrNull("transition") ? 1 : 0) + (numberOrNull("commute") ? 1 : 0);
}

function updateSettingsCount() {
  const count = settingsCount();
  $("moreCount").hidden = !count;
  $("moreCount").textContent = String(count);
  $("lunchRow").hidden = !$("lunchOn").checked;
  syncSegmented();
}

function settingsSnapshot() {
  const settings = {};
  SETTING_FIELDS.forEach((id) => { settings[id] = $(id).value; });
  SETTING_CHECKS.forEach((id) => { settings[id] = $(id).checked; });
  return settings;
}

function restoreSettings(settings) {
  Object.entries(settings || {}).forEach(([id, value]) => {
    if (SETTING_FIELDS.includes(id) && $(id)) setField(id, String(value ?? ""));
    if (SETTING_CHECKS.includes(id) && $(id)) $(id).checked = Boolean(value);
  });
  updateSettingsCount();
}

function commuteMinutes() {
  return Math.max(0, numberOrNull("commute") || 0);
}

/* ===================== one sentence ===================== */

// What each condition type means when the parser found the type but no usable value.
const LABEL_NAME = {
  blocked_time: "不能上课的时间", max_days: "每周最多到校天数", max_daily_hours: "每天最多上课时长",
  lunch: "午饭时间", in_person_only: "只要现场课", prefer_fewer_days: "少到校",
  prefer_less_waiting: "少空等", prefer_no_early_late: "少早晚课",
};
// Which form controls each parsed field fills in.
const SAY_CONTROLS = {
  max_days_per_week: ["maxDays"], max_daily_minutes: ["maxDaily"], max_daily_span: ["maxSpan"],
  lunch: ["lunchOn", "lunchStart", "lunchEnd", "lunchMinutes"], in_person_only: ["inPerson"],
  preferred_hours: ["preferredStart", "preferredEnd"],
};

function hoursLabel(value) {
  return String(Number((value / 60).toFixed(2)));
}

function windowsLabel(windows) {
  // "周五全天", "周一至周五 10:00 前", "周三 14:00–18:00"
  const byTime = new Map();
  windows.forEach((w) => {
    const key = `${w.start_min}|${w.end_min}`;
    if (!byTime.has(key)) byTime.set(key, []);
    byTime.get(key).push(w.weekday);
  });
  return [...byTime].map(([key, days]) => {
    const [start, end] = key.split("|").map(Number);
    days.sort((a, b) => a - b);
    const run = days.length >= 3 && days.every((day, index) => index === 0 || day === days[index - 1] + 1);
    const dayText = run ? `周${DAY[days[0] - 1]}至周${DAY[days[days.length - 1] - 1]}` : days.map((day) => `周${DAY[day - 1]}`).join("、");
    const time = start === 0 && end >= 1439 ? "全天" : start === 0 ? ` ${clock(end)} 前` : end >= 1439 ? ` ${clock(start)} 后` : ` ${clock(start)}–${clock(end)}`;
    return `${dayText}${time}`;
  }).join("，");
}

function clauseMeaning(clause) {
  const f = clause.profile_fields;
  const parts = [];
  if (f.unavailable_windows) parts.push(`${windowsLabel(f.unavailable_windows)}不上课`);
  if (f.max_days_per_week) parts.push(`每周最多到校 ${f.max_days_per_week} 天`);
  if (f.max_daily_minutes) parts.push(`每天最多上课 ${hoursLabel(f.max_daily_minutes)} 小时`);
  if (f.max_daily_span) parts.push(`每天最长在校 ${hoursLabel(f.max_daily_span)} 小时`);
  if (f.lunch) parts.push(`${clock(f.lunch.start_min)}–${clock(f.lunch.end_min)} 留 ${f.lunch.minutes} 分钟吃午饭`);
  if (f.in_person_only) parts.push("只要现场课");
  if (f.preferred_hours) parts.push(`希望上课时间 ${clock(f.preferred_hours.start_min)}–${clock(f.preferred_hours.end_min)}`);
  clause.cares.forEach((care) => parts.push(`在意${AXIS_CHIP[care]}`));
  return parts.join("；");
}

function setSegment(target, value, text) {
  // Parsed values may not be one of the preset buttons; add one so the choice stays visible.
  const group = document.querySelector(`.segmented[data-target="${target}"]`);
  if (group && ![...group.querySelectorAll("button")].some((choice) => choice.dataset.value === value)) {
    const extra = el("button", "", text);
    extra.type = "button";
    extra.dataset.value = value;
    group.append(extra);
  }
  $(target).value = value;
}

function sayControls(clause) {
  return Object.keys(clause.profile_fields).flatMap((key) => SAY_CONTROLS[key] || []);
}

function unapplySay() {
  // Back to the form as it was before the sentence was applied.
  const say = state.say;
  if (!say) return;
  state.blocks = state.blocks.filter((block) => !String(block.key || "").startsWith("say"));
  const touched = new Set(say.clauses.flatMap(sayControls));
  touched.forEach((id) => {
    if (SETTING_CHECKS.includes(id)) $(id).checked = say.base.settings[id];
    else setField(id, say.base.settings[id]);
  });
  state.cares = new Set(say.base.cares);
}

function applySay() {
  const say = state.say;
  unapplySay();
  const cares = new Set();
  say.clauses.forEach((clause, index) => {
    if (!say.on[index]) return;
    const f = clause.profile_fields;
    if (f.unavailable_windows) {
      state.blocks.push({ key: `say${index}`, label: windowsLabel(f.unavailable_windows),
        windows: f.unavailable_windows.map(({ weekday, start_min, end_min }) => ({ weekday, start_min, end_min })) });
    }
    if (f.max_days_per_week) setSegment("maxDays", String(f.max_days_per_week), `${f.max_days_per_week} 天`);
    if (f.max_daily_minutes) setSegment("maxDaily", hoursLabel(f.max_daily_minutes), `${hoursLabel(f.max_daily_minutes)} 时`);
    if (f.max_daily_span) setSegment("maxSpan", hoursLabel(f.max_daily_span), `${hoursLabel(f.max_daily_span)} 时`);
    if (f.lunch) {
      $("lunchOn").checked = true;
      setField("lunchStart", clock(f.lunch.start_min));
      setField("lunchEnd", clock(f.lunch.end_min));
      setField("lunchMinutes", String(f.lunch.minutes));
    }
    if (f.in_person_only) $("inPerson").checked = true;
    if (f.preferred_hours) {
      setField("preferredStart", clock(f.preferred_hours.start_min));
      setField("preferredEnd", clock(f.preferred_hours.end_min));
    }
    clause.cares.forEach((care) => cares.add(care));
  });
  if (cares.size) state.cares = cares;
  renderBlocks();
  updateSettingsCount();
  document.querySelectorAll(".setting.said").forEach((row) => row.classList.remove("said"));
  const said = say.clauses.filter((_, index) => say.on[index]).flatMap(sayControls);
  said.forEach((id) => $(id).closest(".setting")?.classList.add("said"));
  if (said.length) $("moreSettings").open = true;
}

function renderSay() {
  const box = $("sayResult");
  box.replaceChildren();
  const say = state.say;
  if (!say) {
    box.hidden = true;
    return;
  }
  box.append(el("p", "say-head", "我理解为"));
  say.clauses.forEach((clause, index) => {
    const quote = el("span", "quote", `“${clause.text}”`);
    const row = el("div", "say-row");
    if (Object.keys(clause.profile_fields).length || clause.cares.length) {
      const label = el("label", "check");
      const box = el("input");
      box.type = "checkbox";
      box.checked = say.on[index];
      box.addEventListener("change", () => {
        say.on[index] = box.checked;
        applySay();
      });
      label.append(box, document.createTextNode(clauseMeaning(clause)));
      row.append(label, quote);
    } else {
      row.classList.add("note");
      const meaning = clause.label === "other" ? "没听懂，可以在下面手动设置"
        : `听出是“${LABEL_NAME[clause.label] || clause.label}”，但没找到具体的数或时间，请在下面设置`;
      row.append(el("span", "", clause.problems.length ? "识别出的时间或数字不合理，已忽略" : meaning), quote);
    }
    box.append(row);
  });
  const used = say.clauses.filter((_, index) => say.on[index]);
  const places = [];
  if (used.some((clause) => clause.profile_fields.unavailable_windows)) places.push("“不想上课的时间”");
  if (used.some((clause) => sayControls(clause).length)) places.push("“更多设置”里左边有竖线的几项");
  if (used.some((clause) => clause.cares.length)) places.push("结果页的“我在意”");
  box.append(el("p", "say-foot", used.length
    ? `已填进${places.join("、")}，可以直接改；没问题就点“生成课表”。`
    : "这句话里没有能直接设置的条件。"));
  box.hidden = false;
}

async function readSay() {
  const text = $("sayText").value.trim();
  setError("sayError", "");
  if (!text) {
    setError("sayError", "先写一句话");
    return false;
  }
  const button = $("sayRead");
  button.disabled = true;
  try {
    const data = await post("/api/parse", { text });
    if (!data.clauses) throw new Error(data.error || "暂时无法识别");
    unapplySay();
    const clauses = data.clauses;
    state.say = {
      text, clauses, on: clauses.map((clause) => Boolean(Object.keys(clause.profile_fields).length || clause.cares.length)),
      base: { settings: settingsSnapshot(), cares: [...state.cares] },
    };
    applySay();
    renderSay();
    return true;
  } catch (error) {
    setError("sayError", error.message);
    return false;
  } finally {
    button.disabled = false;
  }
}

function sayText() {
  // The sentence goes to the ranker only while it is the one the shown conditions came from.
  return state.say && $("sayText").value.trim() === state.say.text ? state.say.text : "";
}

/* ===================== requests ===================== */

function buildProfile() {
  ["unitError", "windowError", "settingsError"].forEach((id) => setError(id, ""));
  const typed = $("unitQuery").value.trim();
  if (typed && !addUnit(typed, state.matches.find((item) => item.unit_code === typed.toUpperCase())?.unit_name || "")) return null;
  if (!state.units.length) {
    setError("unitError", "请至少添加 1 门课");
    collapseSetup(false);
    $("unitQuery").focus();
    return null;
  }
  const fail = (message) => {
    collapseSetup(false);
    $("moreSettings").open = true;
    setError("settingsError", message);
    return null;
  };
  const start = minutes($("preferredStart").value);
  const end = minutes($("preferredEnd").value);
  if (start === null || end === null || start >= end) return fail("希望上课的结束时间要晚于开始时间");
  const settings = readSettings();
  if (settings.lunch) {
    const { start_min: from, end_min: to, minutes: length } = settings.lunch;
    if (from === null || to === null || from >= to || length > to - from) return fail("午饭时间要放得进所选时段");
  }
  const { year, session_code } = term();
  return {
    schema_version: 1, year, session_code,
    unit_codes: state.units.map((unit) => unit.code),
    unavailable_windows: state.blocks.flatMap((block) => block.windows),
    transition_min: numberOrNull("transition") || 0,
    preferred_hours: { start_min: start, end_min: end },
    ...settings,
  };
}

async function post(path, body) {
  const response = await fetch(path, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok && !data.status && response.status !== 422) throw new Error(data.error || "请求失败");
  return data;
}

function defaultGroups(data) {
  return Object.fromEntries((data.units || []).map((unit) => [unit.unit_code,
    unit.groups.filter((group) => group.default_selected).map((group) => group.group_id)]));
}

function snapshot() {
  // Everything a re-plan may change, so "撤销" can put it back.
  return { groups: structuredClone(state.groups), pinned: { ...state.pinned }, excluded: [...state.excluded],
    enrolled: { ...state.enrolled }, blocks: structuredClone(state.blocks), settings: settingsSnapshot(), tab: state.tab };
}

async function plan(profile, { groups = null, pinned = {}, excluded = [], notice = "", undoTo = null, enrolled = null } = {}) {
  if (state.busy) return;
  state.busy = true;
  const submit = $("submitButton");
  submit.disabled = true;
  showLoading();
  try {
    let data = state.data;
    if (!groups) {
      const first = await post("/api/prepare", { profile, save: false });
      if (first.status === "invalid") {
        showInvalid(first);
        return;
      }
      if (!first.module_two_result) {
        showEmpty("暂时无法生成", first.blockers?.[0]?.message || "缺少这些课程的课表数据。", []);
        return;
      }
      data = first.module_two_result;
      groups = defaultGroups(data);
      state.history = [];
    }
    const body = { profile, save: $("consent").checked, required_groups: groups, student_text: sayText() };
    if (Object.keys(pinned).length) body.pinned = pinned;
    if (excluded.length) body.excluded = excluded;
    if (state.participant) body.participant = state.participant;
    const result = await post("/api/prepare", body);
    if (result.saved) state.participant = result.participant_id || result.profile.profile_id;
    if (undoTo) state.history.push(undoTo);
    state.data = result.module_two_result || data;
    state.groups = groups;
    state.pinned = result.pinned || {};
    state.excluded = result.excluded || [];
    state.result = result;
    state.selected = null;
    state.variant = {};
    state.week = {};
    state.routeDay = {};
    state.compare = [];
    state.notice = notice;
    // A new plan opens on the three recommended timetables; re-plans keep the current view.
    const recommended = Boolean(result.ranking_result?.recommendation);
    if (!recommended) state.view = "all";
    else if (!notice) state.view = state.sharedPlan ? "all" : "recommend";
    if (enrolled) state.enrolled = enrolled;
    else if (!notice) {
      state.enrolled = {};
      state.tab = "week";
    }
    writeShareHash();
    if (result.status === "invalid") showInvalid(result);
    else showResult(result);
  } catch (error) {
    showEmpty("服务暂时不可用", error.message, []);
  } finally {
    state.busy = false;
    submit.disabled = false;
  }
}

function replan(notice, { groups = state.groups, pinned = state.pinned, excluded = state.excluded, undoTo = snapshot() } = {}) {
  const profile = buildProfile();
  if (profile) return plan(profile, { groups, pinned, excluded, notice, undoTo });
  return Promise.resolve();
}

function undo() {
  const previous = state.history.pop();
  if (!previous) return;
  state.blocks = previous.blocks;
  renderBlocks();
  restoreSettings(previous.settings);
  state.tab = previous.tab;
  const profile = buildProfile();
  if (!profile) return;
  plan(profile, { groups: previous.groups, pinned: previous.pinned, excluded: previous.excluded,
    notice: "已撤销上一步", enrolled: previous.enrolled });
}

function collapseSetup(collapsed) {
  $("setupFull").hidden = collapsed;
  $("setupSummary").hidden = !collapsed;
  $("saved").hidden = collapsed || !$("saved").childElementCount;
  if (!collapsed) return;
  const chips = $("summaryChips");
  chips.replaceChildren();
  state.units.forEach((unit) => {
    const chip = el("span", "course");
    chip.style.setProperty("--c", `var(--c${courseIndex(unit.code)})`);
    chip.append(el("i", "dot"), document.createTextNode(unit.code));
    chips.append(chip);
  });
  const said = sayText();
  if (said) chips.append(el("span", "", `“${said.length > 18 ? `${said.slice(0, 18)}…` : said}”`));
  state.blocks.forEach((block) => chips.append(el("span", "", `避开 ${block.label}`)));
  const count = settingsCount();
  if (count) chips.append(el("span", "", `${count} 项设置`));
}

/* ===================== result states ===================== */

function resultBox() {
  const box = $("result");
  box.hidden = false;
  box.replaceChildren();
  return box;
}

function showLoading() {
  const line = el("div", "loading");
  line.append(el("span", "spinner"), document.createTextNode("正在计算所有可行的排法…"));
  resultBox().append(line);
}

function showInvalid(result) {
  $("result").hidden = true;
  collapseSetup(false);
  const map = { unit_codes: "unitError", unavailable_windows: "windowError" };
  (result.errors || []).forEach((error) => setError(map[(error.field || "").split(".")[0]] || "settingsError", error.message));
}

function emptiedGroups() {
  // Required activities whose every class was marked full on enrolment day.
  const chosen = new Set(Object.values(state.groups || {}).flat());
  return (state.data?.units || []).flatMap((unit) => unit.groups)
    .filter((group) => chosen.has(group.group_id) && group.options.length &&
      group.options.every((option) => state.excluded.includes(option.option_id)))
    .map((group) => group.group_id);
}

function showEmpty(title, message, fixes) {
  const card = el("section", "empty");
  if (state.notice && state.result) card.append(el("div", "notice", state.notice));
  card.append(el("h2", "", title), el("p", "", message));
  if (fixes.length) {
    card.append(el("h4", "section-title", "这样改就能排出来"));
    const list = el("div", "fixes");
    fixes.forEach((fix) => list.append(fix));
    card.append(list);
  }
  if (state.history.length) card.append(button("撤销上一步", undo));
  resultBox().append(card);
}

function dataBadge(data) {
  const age = data?.snapshot_age_days;
  const time = data?.snapshot_time || "";
  const badge = el("span", `badge${age >= 1 ? " stale" : ""}`,
    time ? `数据 ${shortDate(time.slice(0, 10))}${age >= 1 ? ` · ${age} 天前` : ""}` : "本地数据");
  if (age >= 1) badge.title = "无法实时查询，座位和时间可能已变化";
  return badge;
}

function changeLabel(change) {
  if (change.kind === "group") return `${groupName(change.group_id)} 不去（如看录播）`;
  if (change.kind === "pin") return `取消固定 ${groupName(change.group_id)}`;
  if (change.kind === "buffer") return "换楼时间改为 0";
  if (change.kind !== "window") return change.label;
  const w = change.window;
  const full = w.start_min === 0 && w.end_min >= 1439;
  return `周${DAY[w.weekday - 1]}${full ? "全天" : ` ${clock(w.start_min)}–${clock(w.end_min)}`}也可以上课`;
}

function applyChange(change) {
  const undoTo = snapshot();
  if (change.kind === "window") {
    const w = change.window;
    state.blocks = state.blocks.map((block) => ({ ...block, windows: block.windows.filter((own) =>
      !(own.weekday === w.weekday && own.start_min >= w.start_min && own.end_min <= w.end_min)) }))
      .filter((block) => block.windows.length);
    renderBlocks();
  }
  const resets = { buffer: "transition", max_days_per_week: "maxDays", max_daily_minutes: "maxDaily",
    max_daily_span: "maxSpan", min_seats: "minSeats", walk_speed: "walkSpeed" };
  const steps = { max_days_per_week: 1, max_daily_minutes: 60, max_daily_span: 60 };
  if (change.value != null && steps[change.kind]) $(resets[change.kind]).value = String(change.value / steps[change.kind]);
  else if (resets[change.kind]) $(resets[change.kind]).value = "";
  if (change.kind === "lunch") $("lunchOn").checked = false;
  if (change.kind === "in_person_only") $("inPerson").checked = false;
  updateSettingsCount();
  const groups = structuredClone(state.groups);
  const pinned = { ...state.pinned };
  if (change.kind === "group") {
    Object.keys(groups).forEach((unit) => { groups[unit] = groups[unit].filter((id) => id !== change.group_id); });
  }
  if (change.kind === "pin") delete pinned[change.group_id];
  replan(`已调整：${changeLabel(change)}`, { groups, pinned, undoTo });
}

function hintLine(text, change, actionLabel = "改成这样") {
  const line = el("div", "hint-line");
  line.append(el("span", "text", text), button(actionLabel, () => applyChange(change)));
  return line;
}

function showResult(result) {
  collapseSetup(true);
  const ranking = result.ranking_result;
  if (result.status === "no_feasible" && ranking) {
    const core = ranking.conflict_core;
    const reason = core
      ? `${core.group_ids.map((id) => `${groupName(id)}（${core.slots[id].join("、")}）`).join(" 与 ")}${{
        time_overlap: "时间冲突", limits: "在你设的每天或每周限制下排不进去",
        filters: "按你的选班条件找不到能一起上的班" }[core.reason] || "之间换楼时间不够"}。`
      : emptiedGroups().length
        ? `${emptiedGroups().map(groupName).join("、")} 的班都被标记为已满，没有可选的班。`
        : "所选活动之间没有不冲突的组合。";
    // When a one-step loosening works as well as dropping the limit, only offer the smaller change.
    const changes = ranking.what_if?.changes || [];
    const fixes = changes.filter((change) => !(change.value == null && changes.some((other) =>
      other.kind === change.kind && other.value != null && other.count === change.count))).map((change) =>
      hintLine(`${changeLabel(change)} → ${change.count.toLocaleString()} 种排法`, change));
    showEmpty("排不出课表", reason, fixes);
    $("result").append(renderAdjust(true));
    return;
  }
  if (!ranking?.feasible_count) {
    showEmpty("暂时无法生成", (result.blockers || [])[0]?.message || "请调整课程后重试。", []);
    if (state.data) $("result").append(renderAdjust(true));
    return;
  }
  renderPlans();
}

/* ===================== plans ===================== */

function courseIndex(code) {
  const index = state.units.findIndex((unit) => unit.code === code);
  return (index < 0 ? 0 : index) % 6;
}

function menu() {
  const shortlist = state.result.ranking_result.shortlist;
  const axes = ["gap", "campus_days", "outside_hours"].filter((axis) => state.cares.has(axis));
  return (shortlist.menus[axes.join(",")] || []).map((id) => shortlist.items[id])
    .sort((a, b) => a.features.campus_days - b.features.campus_days || a.features.gap_min - b.features.gap_min);
}

function planLabel(index) {
  return state.view === "recommend" ? String(index + 1) : LETTERS[index];
}

function recommendation() {
  // The recommended picks for the features currently ticked under "我在意".
  const rec = state.result?.ranking_result?.recommendation;
  if (!rec) return null;
  const axes = ["gap", "campus_days", "outside_hours"].filter((axis) => state.cares.has(axis)).join(",");
  const menu = rec.menus[axes];
  return menu ? { axes, menu, token: rec.explain_token, key: `${rec.explain_token}|${axes}` } : null;
}

function reasonOf(index) {
  const rec = recommendation();
  const written = state.reasons[rec.key];
  return written?.reasons?.[index] || rec.menu.reasons[index];
}

function reasonSource() {
  const written = state.reasons[recommendation().key];
  const status = written?.status;
  if (status === "pending") return "正在请本地千问把理由说得更口语…";
  if (status === "model" || status === "partial") {
    return `理由由本地千问（${written.model}）改写，每句都和课表核对过${status === "partial" ? "；没通过核对的句子保留原样" : ""}。`;
  }
  if (status === "rejected") return "千问改写的句子没通过和课表的核对，显示按课表数据生成的原句。";
  if (status) return "本地千问暂时不可用，理由按课表数据生成。";
  return "理由按课表数据生成。";
}

function updateReasons() {
  // In place, so a late answer does not reset what the student is doing on the page.
  if (state.view !== "recommend" || !recommendation()) return;
  document.querySelectorAll("[data-reason]").forEach((node) => { node.textContent = reasonOf(Number(node.dataset.reason)); });
  const source = document.querySelector(".reason-source");
  if (source) source.textContent = reasonSource();
}

async function loadReasons() {
  const rec = recommendation();
  if (state.view !== "recommend" || !rec?.token || state.reasons[rec.key]) return;
  state.reasons[rec.key] = { status: "pending" };
  updateReasons();
  try {
    const data = await post("/api/explain", { token: rec.token, axes: rec.axes });
    state.reasons[rec.key] = data.reasons ? data : { status: "failed" };
  } catch {
    state.reasons[rec.key] = { status: "failed" };
  }
  updateReasons();
}

function shownItem(base) {
  const shortlist = state.result.ranking_result.shortlist;
  return shortlist.items[state.variant[base.candidate_id] || base.candidate_id] || base;
}

function pickSharedPlan(plans) {
  if (!state.sharedPlan) return;
  const wanted = [...state.sharedPlan].sort().join("|");
  const items = state.result.ranking_result.shortlist.items;
  for (const base of plans) {
    const match = [base, ...(base.variants || []).map((variant) => items[variant.candidate_id]).filter(Boolean)]
      .find((candidate) => [...candidate.option_ids].sort().join("|") === wanted);
    if (match) {
      state.selected = base.candidate_id;
      if (match !== base) state.variant[base.candidate_id] = match.candidate_id;
      break;
    }
  }
  state.sharedPlan = null;
}

function renderPlans() {
  const box = resultBox();
  const ranking = state.result.ranking_result;
  const rec = state.view === "recommend" ? recommendation() : null;
  if (state.view === "recommend" && !rec) state.view = "all";
  const plans = rec ? rec.menu.picks.map((id) => ranking.shortlist.items[id]).filter(Boolean) : menu();
  pickSharedPlan(plans);
  if (!state.selected || !plans.some((item) => item.candidate_id === state.selected)) {
    state.selected = plans[0]?.candidate_id || null;
  }
  state.compare = state.compare.filter((id) => plans.some((item) => item.candidate_id === id));

  const head = el("div", "result-head");
  if (rec) {
    head.append(el("h2", "", `为你挑的 ${plans.length} 份课表`), el("span", "meta",
      `从 ${ranking.feasible_count.toLocaleString()} 种可行排法中先选出 ${rec.menu.candidates.length} 份候选，再按你的情况排序`));
  } else {
    head.append(el("h2", "", plans.length === 1 ? "最合适的课表" : `${plans.length} 个值得考虑的方案`));
    head.append(el("span", "meta", `从 ${ranking.feasible_count.toLocaleString()} 种可行排法中挑出`));
  }
  head.append(dataBadge(state.data), el("span", "spacer"));
  if (ranking.recommendation) {
    const views = el("div", "segmented views");
    views.setAttribute("role", "group");
    views.setAttribute("aria-label", "显示哪些方案");
    [["recommend", "推荐"], ["all", `全部方案 ${menu().length}`]].forEach(([key, text]) => {
      const choice = el("button", state.view === key ? "on" : "", text);
      choice.type = "button";
      choice.setAttribute("aria-pressed", String(state.view === key));
      choice.addEventListener("click", () => {
        if (state.view === key) return;
        state.view = key;
        state.selected = null;
        state.compare = [];
        renderPlans();
      });
      views.append(choice);
    });
    head.append(views);
  }
  // Otherwise the undo button sits in the notice inside the plan detail.
  if (state.history.length && state.compare.length === 2) head.append(button("撤销", undo));
  box.append(head);

  const cares = el("div", "cares");
  cares.append(el("span", "", "我在意"));
  AXES.forEach((axis) => {
    const chip = el("button", `care${state.cares.has(axis) ? " on" : ""}`, AXIS_CHIP[axis]);
    chip.type = "button";
    chip.setAttribute("aria-pressed", String(state.cares.has(axis)));
    chip.addEventListener("click", () => {
      if (state.cares.has(axis) && state.cares.size === 1) {
        toast("至少保留一项");
        return;
      }
      if (state.cares.has(axis)) state.cares.delete(axis); else state.cares.add(axis);
      writeShareHash();
      renderPlans();
    });
    cares.append(chip);
  });
  if (plans.length > 1) cares.append(el("span", "cares-hint", "点卡片右上角可对比两个方案"));
  box.append(cares);

  const workspace = el("div", "workspace");
  const list = el("div", "plan-list");
  plans.forEach((item, index) => list.append(planCard(item, index, plans)));
  if (rec) list.append(el("p", "reason-source", reasonSource()));
  const side = el("div", "side");
  if (state.compare.length === 2) {
    const [a, b] = state.compare.map((id) => plans.find((item) => item.candidate_id === id));
    side.append(renderCompare(a, b, plans));
  } else {
    if (state.compare.length === 1) {
      const bar = el("div", "compare-bar");
      bar.append(document.createTextNode(`已选方案 ${planLabel(plans.findIndex((item) => item.candidate_id === state.compare[0]))}，再选一个即可对比`),
        el("span", "spacer"), button("取消", () => { state.compare = []; renderPlans(); }, { className: "button ghost" }));
      side.append(bar);
    }
    const current = plans.find((item) => item.candidate_id === state.selected);
    if (current) side.append(renderDetail(current, plans));
  }
  workspace.append(list, side);
  box.append(workspace);

  const hints = renderHints(ranking.constraint_costs);
  if (hints) box.append(hints);
  box.append(renderAdjust(false));
  if (STUDY_MODE && state.result.study) box.append(renderStudy(state.result.study));
  if (rec) loadReasons();
}

function planCard(base, index, plans) {
  const item = shownItem(base);
  const selected = base.candidate_id === state.selected && state.compare.length < 2;
  const compared = state.compare.includes(base.candidate_id);
  const card = el("div", `plan${selected ? " selected" : ""}${compared ? " compared" : ""}`);
  card.tabIndex = 0;
  card.setAttribute("role", "button");
  card.setAttribute("aria-pressed", String(selected));
  const select = () => {
    state.selected = base.candidate_id;
    if (state.compare.length === 2) state.compare = [];
    renderPlans();
  };
  card.addEventListener("click", (event) => {
    if (!event.target.closest(".variant, .compare-toggle")) select();
  });
  card.addEventListener("keydown", (event) => {
    if (event.target === card && (event.key === "Enter" || event.key === " ")) {
      event.preventDefault();
      select();
    }
  });

  const head = el("div", "plan-head");
  head.append(el("span", "avatar", planLabel(index)));
  const title = el("div", "plan-title", daysText(item.pattern));
  title.append(el("small", "", base.equivalent_count > 1 ? `${base.equivalent_count.toLocaleString()} 种排法指标相同` : "唯一排法"));
  head.append(title);
  card.append(head);
  const tags = el("div", "tags");
  if (plans.length > 1) {
    AXES.filter((axis) => state.cares.has(axis)).forEach((axis) => {
      const key = AXIS_FEATURE[axis];
      const values = plans.map((other) => other.features[key]);
      const best = Math.min(...values);
      if (Math.max(...values) - best > 1e-6 && Math.abs(base.features[key] - best) < 1e-6) tags.append(el("span", "tag", AXIS_TAG[axis]));
    });
  }
  if (tags.childElementCount) card.append(tags);
  if (state.view === "recommend") {
    const reason = el("p", "reason", reasonOf(index));
    reason.dataset.reason = String(index);
    card.append(reason);
  }

  if (plans.length > 1) {
    const toggle = el("button", `compare-toggle${compared ? " on" : ""}`, compared ? "已选对比" : "对比");
    toggle.type = "button";
    toggle.setAttribute("aria-label", `对比方案 ${planLabel(index)}`);
    toggle.setAttribute("aria-pressed", String(compared));
    toggle.addEventListener("click", () => {
      state.compare = compared ? state.compare.filter((id) => id !== base.candidate_id)
        : [...state.compare, base.candidate_id].slice(-2);
      renderPlans();
    });
    card.append(toggle);
  }

  card.append(stats(base.features), weekGrid(slotsOf(item.meetings), { thumb: true, pattern: item.pattern }));
  const variants = (base.variants || []).filter((variant) => state.result.ranking_result.shortlist.items[variant.candidate_id]);
  if (variants.length > 1) {
    const row = el("div", "variants");
    row.append(el("span", "variants-label", "同样好的到校日"));
    variants.forEach((variant) => {
      const active = (state.variant[base.candidate_id] || base.candidate_id) === variant.candidate_id;
      const chip = el("button", `variant${active ? " on" : ""}`, daysText(variant.pattern));
      chip.type = "button";
      chip.setAttribute("aria-pressed", String(active));
      chip.addEventListener("click", () => {
        state.variant[base.candidate_id] = variant.candidate_id;
        state.selected = base.candidate_id;
        renderPlans();
      });
      row.append(chip);
    });
    card.append(row);
  }
  return card;
}

function stats(features, compareTo = null) {
  const box = el("div", "stats");
  const values = [
    ["campus_days", features.campus_days.toFixed(1), "天", "每周到校", "campus_days"],
    ["gap", features.gap_min >= 60 ? (features.gap_min / 60).toFixed(1) : String(Math.round(features.gap_min)), features.gap_min >= 60 ? "时" : "分", "每周空等", "gap_min"],
    ["outside_hours", String(Math.round(features.outside_min)), "分", "每周早晚课", "outside_min"],
  ];
  values.forEach(([axis, value, unit, label, key]) => {
    const stat = el("div", `stat${state.cares.has(axis) ? "" : " dim"}`);
    const strong = el("strong", "", value);
    strong.append(el("small", "", unit));
    if (compareTo) {
      const diff = features[key] - compareTo.features[key];
      if (Math.abs(diff) > (key === "campus_days" ? 0.05 : 1)) {
        const text = key === "campus_days" ? `${diff.toFixed(1)}天`
          : Math.abs(diff) >= 60 ? `${(diff / 60).toFixed(1)}时` : `${Math.round(diff)}分`;
        strong.append(el("span", `delta ${diff < 0 ? "better" : "worse"}`, `${diff > 0 ? "+" : ""}${text}`));
      }
    }
    stat.append(strong, el("span", "", label));
    box.append(stat);
  });
  return box;
}

/* ===================== week grids ===================== */

function slotsOf(meetings) {
  // The weekly routine: classes that repeat in at least three weeks.
  const slots = new Map();
  meetings.forEach((meeting) => {
    const key = [meeting.weekday, meeting.start_min, meeting.end_min, meeting.unit_code, meeting.group_id, meeting.is_online].join("|");
    if (!slots.has(key)) slots.set(key, { ...meeting, weeks: 0 });
    slots.get(key).weeks += 1;
  });
  return [...slots.values()].filter((slot) => slot.weeks >= 3);
}

function hourRange(meetings, base = [9 * 60, 17 * 60]) {
  let [from, to] = base;
  meetings.forEach((meeting) => {
    from = Math.min(from, Math.floor(meeting.start_min / 60) * 60);
    to = Math.max(to, Math.ceil(meeting.end_min / 60) * 60);
  });
  return [from, to];
}

function laneLayout(meetings) {
  // Side-by-side columns for overlapping blocks (used when showing every class of an activity).
  const placed = new Map();
  const sorted = [...meetings].sort((a, b) => a.start_min - b.start_min || a.end_min - b.end_min);
  let cluster = [];
  let clusterEnd = -1;
  const flush = () => {
    const lanes = [];
    cluster.forEach((meeting) => {
      let lane = lanes.findIndex((end) => end <= meeting.start_min);
      if (lane < 0) {
        lane = lanes.length;
        lanes.push(0);
      }
      lanes[lane] = meeting.end_min;
      placed.set(meeting, { lane, lanes: 0 });
    });
    cluster.forEach((meeting) => { placed.get(meeting).lanes = lanes.length; });
    cluster = [];
  };
  sorted.forEach((meeting) => {
    if (cluster.length && meeting.start_min >= clusterEnd) flush();
    cluster.push(meeting);
    clusterEnd = Math.max(clusterEnd, meeting.end_min);
  });
  if (cluster.length) flush();
  return placed;
}

function weekGrid(meetings, { thumb = false, dates = null, range = null, pattern = "", todayIndex = -1,
  onDay = null, activeDay = null, decorate = null, lanes = false, nowLine = false, compact = false } = {}) {
  const used = new Set(meetings.map((meeting) => meeting.weekday));
  const days = [1, 2, 3, 4, 5, ...[6, 7].filter((day) => used.has(day))];
  const [from, to] = range || hourRange(meetings);
  const hourHeight = thumb ? Math.max(6, Math.floor(80 / ((to - from) / 60))) : compact ? 34 : 46;
  const height = ((to - from) / 60) * hourHeight;
  const grid = el("div", `week${thumb ? " thumb" : ""}${compact ? " compact" : ""}`);
  grid.style.setProperty("--cols", String(days.length));
  grid.style.setProperty("--hour", `${hourHeight}px`);
  if (!thumb) grid.append(el("div"));
  days.forEach((day, index) => {
    if (thumb) {
      grid.append(el("div", `head${pattern.includes(String(day)) ? " on" : ""}`, DAY[day - 1]));
      return;
    }
    const head = el(onDay ? "button" : "div", `head${index === todayIndex ? " today" : ""}${activeDay === day ? " active" : ""}`);
    if (onDay) {
      head.type = "button";
      head.title = "查看这天的路线";
      head.setAttribute("aria-pressed", String(activeDay === day));
      head.addEventListener("click", () => onDay(day));
    }
    head.append(el("b", "", `周${DAY[day - 1]}`));
    if (dates) head.append(document.createTextNode(index === todayIndex ? "今天" : dates[index]));
    grid.append(head);
  });
  if (!thumb) {
    const hours = el("div", "hours");
    hours.style.height = `${height}px`;
    for (let hour = from; hour <= to; hour += 60) {
      const label = el("span", "", `${hour / 60}:00`);
      label.style.top = `${((hour - from) / 60) * hourHeight}px`;
      hours.append(label);
    }
    grid.append(hours);
  }
  days.forEach((day, index) => {
    const col = el("div", `col${index === todayIndex ? " today" : ""}`);
    col.style.height = `${height}px`;
    const daily = meetings.filter((meeting) => meeting.weekday === day);
    const layout = lanes ? laneLayout(daily) : null;
    daily.forEach((meeting) => {
      const block = el("div", `block${meeting.is_online ? " online" : ""}${meeting.unavailable_exception ? " exception" : ""}`);
      block.style.setProperty("--c", `var(--c${courseIndex(meeting.unit_code)})`);
      block.style.top = `${((meeting.start_min - from) / 60) * hourHeight}px`;
      block.style.height = `${Math.max(((meeting.end_min - meeting.start_min) / 60) * hourHeight - 2, 3)}px`;
      if (layout && layout.get(meeting).lanes > 1) {
        const { lane, lanes: count } = layout.get(meeting);
        block.style.left = `calc(${(lane / count) * 100}% + 2px)`;
        block.style.right = "auto";
        block.style.width = `calc(${100 / count}% - 4px)`;
      }
      const activity = activityOf(meeting);
      const room = meeting.is_online ? "线上" : meeting.building_code || "";
      block.title = `${meeting.unit_code} ${activity} ${meeting.class_code || ""}  ${clock(meeting.start_min)}–${clock(meeting.end_min)}  ${meeting.is_online ? "线上" : meeting.location_raw || room}`;
      if (!thumb) {
        block.append(el("b", "", meeting.unit_code), el("span", "act", `${activity} ${meeting.class_code || ""}`.trim()));
        if (room) block.append(el("span", "room", room));
      }
      if (decorate) decorate(block, meeting);
      col.append(block);
    });
    if (nowLine && index === todayIndex && NOW_MIN > from && NOW_MIN < to) {
      const line = el("div", "now-line");
      line.style.top = `${((NOW_MIN - from) / 60) * hourHeight}px`;
      col.append(line);
    }
    grid.append(col);
  });
  return grid;
}

/* ===================== detail ===================== */

const TABS = [["week", "周课表"], ["term", "学期"], ["time", "时间"], ["enrol", "选课"], ["friend", "和朋友"]];

function renderDetail(base, plans) {
  const item = shownItem(base);
  const index = plans.findIndex((other) => other.candidate_id === base.candidate_id);
  const letter = planLabel(index);
  const detail = el("section", "detail");

  const head = el("div", "detail-head");
  const title = el("h3");
  title.append(el("span", "avatar", letter), document.createTextNode(daysText(item.pattern)));
  head.append(title, el("span", "spacer"));
  const tools = el("div", "tool-row");
  tools.append(
    button("日历", () => { downloadIcs(item); toast("已导出 .ics，可导入 Google / Apple / Outlook 日历"); }, { title: "导出到日历" }),
    button("分享", () => copyText(shareUrl(item), "链接已复制，朋友打开就能看到这个方案"), { title: "复制分享链接" }),
    button("收藏", () => { saveFavourite(item, letter); toast("已收藏，回到首页可打开"); }, { title: "收藏到本机" }),
    button("打印", () => window.print(), { title: "打印" }),
    button("就选这个", (node) => acceptPlan(item, index, plans, node), { className: "button primary" }),
  );
  head.append(tools);
  detail.append(head);
  if (state.notice) {
    const notice = el("div", "notice", state.notice);
    if (state.history.length) notice.append(button("撤销", undo, { className: "button ghost" }));
    detail.append(notice);
  }
  const next = nextClass(item);
  if (next) detail.append(next);

  const bar = el("div", "tabs");
  bar.setAttribute("role", "tablist");
  const panel = el("div", "tab-panel");
  TABS.forEach(([key, label]) => {
    const tab = el("button", `tab${state.tab === key ? " on" : ""}`, label);
    tab.type = "button";
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-selected", String(state.tab === key));
    tab.addEventListener("click", () => {
      state.tab = key;
      bar.querySelectorAll(".tab").forEach((other) => {
        other.classList.toggle("on", other === tab);
        other.setAttribute("aria-selected", String(other === tab));
      });
      panel.replaceChildren(TAB_VIEWS[key](item, base));
    });
    bar.append(tab);
  });
  panel.append(TAB_VIEWS[state.tab](item, base));
  detail.append(bar, panel);
  return detail;
}

function nextClass(item) {
  // During the term, the next class of this plan from now on.
  const upcoming = item.meetings
    .filter((meeting) => meeting.date > TODAY || (meeting.date === TODAY && meeting.end_min > NOW_MIN))
    .sort((a, b) => a.date.localeCompare(b.date) || a.start_min - b.start_min)[0];
  const first = item.meetings.reduce((min, meeting) => (meeting.date < min ? meeting.date : min), "9999");
  if (!upcoming || daysBetween(TODAY, first) > 14) return null;
  const days = daysBetween(TODAY, upcoming.date);
  const when = days === 0 ? (upcoming.start_min <= NOW_MIN ? "正在上" : `今天 ${clock(upcoming.start_min)}`)
    : days === 1 ? `明天 ${clock(upcoming.start_min)}` : `${shortDate(upcoming.date)} 周${DAY[upcoming.weekday - 1]} ${clock(upcoming.start_min)}`;
  const box = el("div", "next-class");
  box.append(el("span", "next-label", days === 0 && upcoming.start_min <= NOW_MIN ? "现在" : "下一节"),
    el("b", "", when), el("span", "", `${upcoming.unit_code} ${activityOf(upcoming)} ${upcoming.class_code || ""}`),
    el("span", "muted", upcoming.is_online ? "线上" : upcoming.location_raw && upcoming.location_raw !== "-" ? upcoming.location_raw : upcoming.building_code || ""));
  return box;
}

function currentWeekIndex(weeks) {
  return weeks.findIndex((week) => TODAY >= week && TODAY <= addDays(week, 6));
}

function weekView(item, base) {
  const box = el("div");
  const weeks = state.result.ranking_result.teaching_weeks;
  if (state.week[base.candidate_id] === undefined) {
    // This week if the term is on, otherwise the first week with the full routine.
    const now = currentWeekIndex(weeks);
    const routine = slotsOf(item.meetings).map((slot) => `${slot.weekday}|${slot.start_min}|${slot.group_id}`);
    const inWeek = (week) => item.meetings.filter((meeting) => meeting.date >= week && meeting.date <= addDays(week, 6));
    const full = weeks.findIndex((week) => {
      const present = new Set(inWeek(week).map((meeting) => `${meeting.weekday}|${meeting.start_min}|${meeting.group_id}`));
      return routine.every((key) => present.has(key));
    });
    state.week[base.candidate_id] = now >= 0 ? now : Math.max(0, full);
  }
  const range = hourRange(item.meetings);
  const move = (step) => {
    state.week[base.candidate_id] = Math.min(weeks.length - 1, Math.max(0, state.week[base.candidate_id] + step));
    draw();
  };
  const nav = el("div", "week-nav");
  const prev = button("←", () => move(-1), { className: "button ghost", title: "上一周" });
  const next = button("→", () => move(1), { className: "button ghost", title: "下一周" });
  const label = el("span", "label");
  const nowPill = el("span", "pill", "本周");
  const thisWeek = currentWeekIndex(weeks);
  const back = button("回到本周", () => { state.week[base.candidate_id] = thisWeek; draw(); }, { className: "button ghost" });
  nav.append(prev, next, label, nowPill, back, el("span", "hint", "点星期看当天路线 · ← → 换周"));
  const holder = el("div", "week-holder");
  const route = el("div");
  box.append(nav, holder, route);
  box.dataset.weekNav = "1";
  box.addEventListener("weekstep", (event) => move(event.detail));

  function draw() {
    const position = state.week[base.candidate_id];
    const week = weeks[position];
    const end = addDays(week, 6);
    const meetings = item.meetings.filter((meeting) => meeting.date >= week && meeting.date <= end);
    label.textContent = `第 ${position + 1} 周 · ${shortDate(week)}–${shortDate(end)}`;
    nowPill.hidden = position !== thisWeek;
    back.hidden = thisWeek < 0 || position === thisWeek;
    prev.disabled = position === 0;
    next.disabled = position === weeks.length - 1;
    const used = new Set(meetings.map((meeting) => meeting.weekday));
    const dayList = [1, 2, 3, 4, 5, ...[6, 7].filter((day) => used.has(day))];
    const todayIndex = dayList.findIndex((day) => addDays(week, day - 1) === TODAY);
    const activeDay = state.routeDay[base.candidate_id] || null;
    holder.replaceChildren(weekGrid(meetings, {
      dates: dayList.map((day) => shortDate(addDays(week, day - 1))), range, todayIndex, activeDay, nowLine: true,
      onDay: (day) => {
        state.routeDay[base.candidate_id] = state.routeDay[base.candidate_id] === day ? null : day;
        draw();
      },
    }));
    if (!meetings.length) holder.append(el("p", "week-empty", "这周没有课"));
    route.replaceChildren();
    if (activeDay) {
      const date = addDays(week, activeDay - 1);
      route.append(routeView(item.meetings.filter((meeting) => meeting.date === date), date));
    }
  }
  draw();

  const legend = el("div", "legend");
  state.units.forEach((unit) => {
    const key = el("span");
    const swatch = el("i");
    swatch.style.setProperty("--c", `var(--c${courseIndex(unit.code)})`);
    key.append(swatch, document.createTextNode(unit.code));
    legend.append(key);
  });
  legend.append(el("span", "", "斜纹为线上课"));
  box.append(legend);
  const transfers = tightTransfers(item.meetings);
  if (transfers.length) {
    const alerts = el("div", "alerts");
    transfers.forEach((text) => {
      const line = el("div", "alert");
      line.textContent = text;
      alerts.append(line);
    });
    box.append(alerts);
  }
  return box;
}

function routeView(meetings, date) {
  // The day's walk between buildings, drawn from the campus map coordinates.
  const box = el("div", "route");
  const head = el("div", "route-head");
  head.append(el("b", "", `${shortDate(date)} 周${DAY[weekdayOf(date) - 1]} 路线`));
  box.append(head);
  const stops = [];
  meetings.filter((meeting) => !meeting.is_online && meeting.building_code)
    .sort((a, b) => a.start_min - b.start_min)
    .forEach((meeting) => {
      const last = stops[stops.length - 1];
      if (last && last.code === meeting.building_code) {
        last.until = meeting.end_min;
        last.what += ` · ${meeting.unit_code} ${activityOf(meeting)}`;
        return;
      }
      stops.push({ code: meeting.building_code, location: meeting.building_location, from: meeting.start_min,
        until: meeting.end_min, what: `${meeting.unit_code} ${activityOf(meeting)}` });
    });
  if (!stops.length) {
    head.append(el("span", "meta", meetings.length ? "这天只有线上课" : "这天没有课"));
    return box;
  }
  const located = stops.filter((stop) => stop.location?.latitude != null);
  let metres = 0;
  for (let index = 1; index < located.length; index += 1) metres += distanceMetres(located[index - 1].location, located[index].location);
  head.append(el("span", "meta", stops.length === 1 ? `整天都在 ${stops[0].code}` :
    `${stops.length} 段 · 共步行约 ${Math.max(1, Math.round((metres * 1.3) / 80))} 分钟（按地图直线距离估算）`));
  if (located.length) {
    const lat0 = located.reduce((sum, stop) => sum + stop.location.latitude, 0) / located.length;
    const project = (location) => [location.longitude * Math.cos((lat0 * Math.PI) / 180), -location.latitude];
    const raw = located.map((stop) => project(stop.location));
    const minX = Math.min(...raw.map(([x]) => x));
    const minY = Math.min(...raw.map(([, y]) => y));
    const spanX = Math.max(...raw.map(([x]) => x)) - minX || 1e-4;
    const spanY = Math.max(...raw.map(([, y]) => y)) - minY || 1e-4;
    const width = 560;
    const height = Math.round(Math.max(140, Math.min(230, (spanY / spanX) * 440 + 70)));
    const scale = Math.min((width - 160) / spanX, (height - 60) / spanY);
    const offsetX = (width - spanX * scale) / 2;
    const offsetY = (height - spanY * scale) / 2;
    const xy = raw.map(([x, y]) => [offsetX + (x - minX) * scale, offsetY + (y - minY) * scale]);
    const svg = svgEl("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": "当天在各楼之间的路线" });
    if (xy.length > 1) svg.append(svgEl("polyline", { class: "road", points: xy.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ") }));
    const byCode = new Map();
    located.forEach((stop, index) => {
      if (!byCode.has(stop.code)) byCode.set(stop.code, { at: xy[index], numbers: [] });
      byCode.get(stop.code).numbers.push(stops.indexOf(stop) + 1);
    });
    byCode.forEach(({ at: [x, y], numbers }, code) => {
      const text = numbers.join("·");
      svg.append(svgEl("circle", { class: "dot", cx: x.toFixed(1), cy: y.toFixed(1), r: 11 + 3.5 * (text.length - 1) }));
      const number = svgEl("text", { class: "dot-label", x: x.toFixed(1), y: y.toFixed(1) });
      number.textContent = text;
      const name = svgEl("text", { class: "name", x: (x + 16 + 3.5 * (text.length - 1)).toFixed(1), y: (y + 4).toFixed(1) });
      name.textContent = code;
      svg.append(number, name);
    });
    box.append(svg);
  }
  const list = el("ol", "stops");
  stops.forEach((stop, index) => {
    const li = el("li");
    if (index) {
      const prev = stops[index - 1];
      const gap = stop.from - prev.until;
      const a = prev.location;
      const b = stop.location;
      const walk = a?.latitude != null && b?.latitude != null ? Math.max(1, Math.round((distanceMetres(a, b) * 1.3) / 80)) : null;
      const leg = el("li", `leg${walk !== null && walk > gap ? " tight" : ""}`,
        `↓ 空 ${gap} 分钟${walk !== null ? `，走过去约 ${walk} 分钟` : ""}`);
      list.append(leg);
    }
    const name = stop.location?.name ? ` ${stop.location.name}` : "";
    li.append(el("b", "", String(index + 1)), el("span", "stop-time", `${clock(stop.from)}–${clock(stop.until)}`),
      el("strong", "", `${stop.code}${name}`), el("span", "muted", stop.what));
    if (stop.location?.map_url) {
      const link = el("a", "map-link", "地图");
      link.href = stop.location.map_url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      li.append(link);
    }
    list.append(li);
  });
  box.append(list);
  return box;
}

function termView(item) {
  // Every teaching week at a glance: on-campus hours per weekday, then one-off dates.
  const box = el("div");
  const weeks = state.result.ranking_result.teaching_weeks;
  const now = currentWeekIndex(weeks);
  const heat = el("div", "heat");
  heat.append(el("span"));
  for (let day = 1; day <= 5; day += 1) heat.append(el("span", "heat-head", `周${DAY[day - 1]}`));
  weeks.forEach((week, position) => {
    if (position && daysBetween(weeks[position - 1], week) > 7) heat.append(el("span", "heat-break", "期中假"));
    heat.append(el("span", `heat-week${position === now ? " now" : ""}`, `第 ${position + 1} 周`));
    for (let day = 1; day <= 5; day += 1) {
      const date = addDays(week, day - 1);
      const meetings = item.meetings.filter((meeting) => meeting.date === date);
      const onCampus = meetings.filter((meeting) => !meeting.is_online);
      const hours = onCampus.reduce((sum, meeting) => sum + meeting.end_min - meeting.start_min, 0) / 60;
      const cell = el("span", `heat-cell${onCampus.length ? "" : meetings.length ? " online" : " off"}${date === TODAY ? " now" : ""}${date < TODAY ? " past" : ""}`,
        onCampus.length ? `${Number(hours.toFixed(1))}h` : meetings.length ? "线上" : "–");
      if (onCampus.length) cell.style.setProperty("--level", String(Math.min(1, hours / 6)));
      if (meetings.some((meeting) => meeting.is_fixed_assessment)) cell.classList.add("exam");
      cell.title = `${shortDate(date)} ${meetings.map((meeting) => `${meeting.unit_code} ${activityOf(meeting)} ${clock(meeting.start_min)}`).join("，") || "无课"}`;
      heat.append(cell);
    }
  });
  box.append(heat);
  const key = el("div", "legend");
  key.append(el("span", "", "颜色越深在校越久"), el("span", "", "橙框为考试或固定测验"), el("span", "", "蓝框为今天"));
  box.append(key);
  const routine = new Set(slotsOf(item.meetings).map((slot) => `${slot.weekday}|${slot.start_min}|${slot.group_id}`));
  const oneOff = item.meetings.filter((meeting) => !routine.has(`${meeting.weekday}|${meeting.start_min}|${meeting.group_id}`))
    .sort((a, b) => a.date.localeCompare(b.date) || a.start_min - b.start_min);
  if (oneOff.length) {
    box.append(el("h4", "section-title", "不在每周固定时间的课"));
    const list = el("ul", "list");
    oneOff.forEach((meeting) => {
      const li = el("li", `${meeting.is_fixed_assessment ? "exam" : ""}${meeting.date < TODAY ? " past" : ""}`.trim());
      const days = daysBetween(TODAY, meeting.date);
      li.append(el("b", "", `${shortDate(meeting.date)} 周${DAY[meeting.weekday - 1]}`),
        el("span", "", `${clock(meeting.start_min)}–${clock(meeting.end_min)}`),
        el("span", "", `${meeting.unit_code} ${activityOf(meeting)} ${meeting.class_code || ""}`),
        el("span", "muted", meeting.is_online ? "线上" : meeting.building_code || ""));
      if (days >= 0 && days <= 21) li.append(el("span", "soon", days === 0 ? "今天" : `${days} 天后`));
      list.append(li);
    });
    box.append(list);
  }
  return box;
}

function timeView(item) {
  const box = el("div");
  const weeks = state.result.ranking_result.teaching_weeks.length;
  const f = item.features;
  const classMinutes = item.meetings.reduce((sum, meeting) => sum + meeting.end_min - meeting.start_min, 0) / weeks;
  const commute = commuteMinutes() * 2 * f.campus_days;
  const rows = [["上课", classMinutes, "c0"], ["空等", f.gap_min, "c2"], ["通勤", commute, "c4"]];
  const total = rows.reduce((sum, [, value]) => sum + value, 0);
  const ledger = el("div", "ledger");
  const totalLine = el("div", "ledger-total", hoursText(total));
  totalLine.append(el("small", "", `每周平均 · 整学期约 ${Math.round((total * weeks) / 60)} 小时`));
  const bar = el("div", "ledger-bar");
  rows.forEach(([label, value, color]) => {
    if (!value) return;
    const part = el("i");
    part.style.setProperty("--w", `${(value / total) * 100}%`);
    part.style.setProperty("--c", `var(--${color})`);
    part.title = `${label} ${hoursText(value)}`;
    bar.append(part);
  });
  const legend = el("div", "ledger-legend");
  rows.forEach(([label, value, color]) => {
    const key = el("span");
    const swatch = el("i");
    swatch.style.setProperty("--c", `var(--${color})`);
    key.append(swatch, document.createTextNode(`${label} ${hoursText(value)}`));
    legend.append(key);
  });
  if (!commuteMinutes()) legend.append(el("span", "muted", "在“更多设置”里选单程通勤，可把路上时间算进来"));
  ledger.append(totalLine, bar, legend);
  box.append(ledger);

  const routine = slotsOf(item.meetings);
  const table = el("table", "table");
  const header = el("tr");
  ["", "到校", "上课", "空等"].forEach((text) => header.append(el("th", "", text)));
  table.append(header);
  const free = [];
  for (let day = 1; day <= 5; day += 1) {
    const daily = routine.filter((slot) => slot.weekday === day).sort((a, b) => a.start_min - b.start_min);
    const campus = daily.filter((slot) => !slot.is_online);
    const row = el("tr");
    row.append(el("td", "", `周${DAY[day - 1]}`));
    if (!daily.length) {
      row.append(el("td", "muted", "不用上课"), el("td"), el("td"));
    } else {
      const span = campus.length ? `${clock(campus[0].start_min)}–${clock(Math.max(...campus.map((slot) => slot.end_min)))}` : "只有线上课";
      const taught = daily.reduce((sum, slot) => sum + slot.end_min - slot.start_min, 0);
      let waiting = 0;
      let latest = daily[0].end_min;
      daily.slice(1).forEach((slot) => {
        waiting += Math.max(0, slot.start_min - latest);
        latest = Math.max(latest, slot.end_min);
      });
      row.append(el("td", "", span), el("td", "", hoursText(taught)), el("td", "", waiting ? hoursText(waiting) : "—"));
    }
    table.append(row);
    let cursor = 9 * 60;
    [...daily, { start_min: 18 * 60, end_min: 18 * 60 }].forEach((slot) => {
      const start = Math.min(slot.start_min, 18 * 60);
      if (start - cursor >= 180) free.push(`周${DAY[day - 1]} ${clock(cursor)}–${clock(start)}`);
      cursor = Math.max(cursor, slot.end_min);
    });
  }
  box.append(el("h4", "section-title", "典型一周"), table);
  box.append(el("h4", "section-title", "整块空闲 · 适合打工或自习"));
  if (free.length) {
    const chips = el("div", "free-blocks");
    free.forEach((text) => chips.append(el("span", "", text)));
    box.append(chips);
  } else {
    box.append(el("p", "muted", "9:00–18:00 内没有 3 小时以上的空闲"));
  }
  return box;
}

function optionOf(item, group) {
  return item.option_ids.find((id) => id.startsWith(`${group}|`));
}

function seatPill(info) {
  const seats = seatNumber(info.seats);
  return el("span", `seat${seats === null ? "" : seats <= 3 ? " low" : " ok"}`, info.seats || "–");
}

function enrolView(item) {
  const box = el("div");
  const order = enrolmentOrder(item);
  const doneCount = order.filter(({ group }) => {
    const option = optionOf(item, group);
    return state.enrolled[group] === option || (state.pinned[group] || []).includes(option);
  }).length;
  const progress = el("div", "progress");
  const track = el("div", "progress-track");
  const fill = el("i");
  fill.style.setProperty("--w", `${order.length ? (doneCount / order.length) * 100 : 0}%`);
  track.append(fill);
  progress.append(el("span", "", `已报 ${doneCount} / ${order.length}`), track);
  box.append(progress, el("p", "muted", "从上往下报：余位少、没有同等替代的排在前面。点“满了”会保留已报上的班，重新安排其余的。"));
  const table = el("table", "table");
  const head = el("tr");
  ["", "课程", "班", "余位", "满了可换", ""].forEach((text) => head.append(el("th", "", text)));
  table.append(head);
  order.forEach(({ group, info }, index) => {
    const option = optionOf(item, group);
    const done = state.enrolled[group] === option || (state.pinned[group] || []).includes(option);
    const row = el("tr", done ? "done" : "");
    row.append(el("td", "num", done ? "✓" : String(index + 1)), el("td", "", groupName(group)), el("td", "strong", info.code));
    const seatCell = el("td");
    seatCell.append(seatPill(info));
    row.append(seatCell);
    const backup = el("td", "backup");
    if (done) backup.textContent = "已报上";
    else if (!info.backups.length) backup.textContent = "没有不冲突的备选";
    else {
      backup.textContent = info.backups.slice(0, 2).map((entry) => `${entry.code}（${deltaShort(entry.delta)}）`).join("　");
      if (info.alternatives > 2) backup.textContent += `　+${info.alternatives - 2}`;
    }
    row.append(backup);
    const actions = el("td", "row-actions");
    if (!done) {
      actions.append(
        button("报上了", () => { state.enrolled[group] = option; renderPlans(); toast(`${groupName(group)} ${info.code} 已报上`); }),
        button("满了", () => markFull(group, option), { className: "button danger" }),
      );
    } else if (state.enrolled[group] === option) {
      actions.append(button("取消", () => { delete state.enrolled[group]; renderPlans(); }, { className: "button ghost" }));
    }
    row.append(actions);
    table.append(row);
  });
  const scroller = el("div", "table-scroll");
  scroller.append(table);
  box.append(scroller);
  const tools = el("div", "tool-row spaced");
  tools.append(button("复制选课清单", () => copyText(`UniPlan 选课清单\n${enrolmentText(item)}`, "选课清单已复制")));
  if (state.excluded.length) {
    tools.append(button(`清除已满标记（${state.excluded.length}）`, () => replan("已清除已满标记", { excluded: [] })));
  }
  box.append(tools);
  return box;
}

function markFull(group, option) {
  // Keep what is already secured, leave this class out, and plan the rest again.
  const undoTo = snapshot();
  const pinned = { ...state.pinned };
  Object.entries(state.enrolled).forEach(([enrolledGroup, enrolledOption]) => { pinned[enrolledGroup] = [enrolledOption]; });
  state.tab = "enrol";
  replan(`${groupName(group)} ${option.split("|").pop()} 已满，已保留报上的班并重新安排。`,
    { pinned, excluded: [...new Set([...state.excluded, option])], undoTo });
}

function friendView(item) {
  const box = el("div");
  box.append(el("p", "muted", "粘贴朋友分享的方案链接，看看你们哪些课同班、哪天能一起吃饭，或者一键排到同一个班。"));
  const row = el("div", "friend-row");
  const input = el("input", "input");
  input.type = "url";
  input.placeholder = "朋友的分享链接";
  input.value = state.friend?.link || "";
  const result = el("div");
  const compare = () => {
    const shared = parseShare(input.value.split("#")[1] || "");
    if (!shared?.plan) {
      result.replaceChildren(el("p", "field-error", "这个链接里没有方案，请让朋友在方案详情里点“分享”"));
      return;
    }
    state.friend = { link: input.value, plan: shared.plan, slots: shared.slots || null };
    result.replaceChildren(friendCompare(item));
  };
  input.addEventListener("keydown", (event) => { if (event.key === "Enter") compare(); });
  row.append(input, button("对比", compare, { className: "button primary" }));
  box.append(row, result);
  if (state.friend) result.append(friendCompare(item));
  return box;
}

function freeTogether(item, friendSlots) {
  // Lunch-time windows (11:00–15:00) of at least 45 minutes when both of you are on campus and free.
  const mine = slotsOf(item.meetings);
  const out = [];
  for (let day = 1; day <= 5; day += 1) {
    const both = [...mine.filter((slot) => slot.weekday === day), ...friendSlots.filter((slot) => slot.weekday === day)];
    const meOn = mine.some((slot) => slot.weekday === day && !slot.is_online);
    const theyOn = friendSlots.some((slot) => slot.weekday === day && !slot.is_online);
    if (!meOn || !theyOn) continue;
    let cursor = 11 * 60;
    [...both.sort((a, b) => a.start_min - b.start_min), { start_min: 15 * 60, end_min: 15 * 60 }].forEach((slot) => {
      const start = Math.min(slot.start_min, 15 * 60);
      if (start - cursor >= 45) out.push(`周${DAY[day - 1]} ${clock(cursor)}–${clock(start)}`);
      cursor = Math.max(cursor, slot.end_min);
    });
  }
  return out;
}

function friendCompare(item) {
  const box = el("div");
  const mine = new Map(item.option_ids.map((id) => [id.split("|").slice(0, 2).join("|"), id]));
  const theirs = new Map(state.friend.plan.map((id) => [id.split("|").slice(0, 2).join("|"), id]));
  const shared = [...theirs.keys()].filter((group) => mine.has(group));
  if (state.friend.slots) {
    const together = freeTogether(item, state.friend.slots);
    box.append(el("h4", "section-title", "你们都在学校又都有空（午饭时段）"));
    if (together.length) {
      const chips = el("div", "free-blocks");
      together.forEach((text) => chips.append(el("span", "", text)));
      box.append(chips);
    } else {
      box.append(el("p", "muted", "11:00–15:00 之间没有共同的 45 分钟空档"));
    }
  }
  if (!shared.length) {
    box.append(el("p", "muted", "你们没有共同的课程活动。"));
    return box;
  }
  box.append(el("h4", "section-title", `共同的课 · 同班 ${shared.filter((group) => mine.get(group) === theirs.get(group)).length} / ${shared.length}`));
  const list = el("ul", "list");
  shared.forEach((group) => {
    const same = mine.get(group) === theirs.get(group);
    const li = el("li", same ? "same" : "");
    li.append(el("b", "", groupName(group)),
      el("span", "", same ? `同班 ${mine.get(group).split("|").pop()}` : `你 ${mine.get(group).split("|").pop()} · 朋友 ${theirs.get(group).split("|").pop()}`));
    list.append(li);
  });
  box.append(list);
  const different = shared.filter((group) => mine.get(group) !== theirs.get(group));
  if (different.length) {
    const join = button("尽量和朋友同班", () => {
      const undoTo = snapshot();
      const pinned = { ...state.pinned };
      different.forEach((group) => { pinned[group] = [theirs.get(group)]; });
      state.tab = "friend";
      replan("已按朋友的班级重新安排；排不进去时会提示要放宽哪一项。", { pinned, undoTo });
    }, { className: "button primary spaced" });
    box.append(join);
  }
  return box;
}

const TAB_VIEWS = { week: weekView, term: termView, time: timeView, enrol: enrolView, friend: friendView };

function renderCompare(a, b, plans) {
  const box = el("section", "detail compare");
  const head = el("div", "detail-head");
  const title = el("h3");
  title.append(document.createTextNode(`方案 ${planLabel(plans.indexOf(a))} 与 ${planLabel(plans.indexOf(b))}`));
  head.append(title, el("span", "spacer"),
    button("结束对比", () => { state.compare = []; renderPlans(); }, { className: "button ghost" }));
  box.append(head);
  const itemA = shownItem(a);
  const itemB = shownItem(b);
  const range = hourRange([...slotsOf(itemA.meetings), ...slotsOf(itemB.meetings)]);
  const grid = el("div", "compare-grid");
  [[a, b], [b, a]].forEach(([own, other]) => {
    const item = shownItem(own);
    const col = el("div", "compare-col");
    const title = el("div", "plan-head");
    title.append(el("span", "avatar", planLabel(plans.indexOf(own))), el("div", "plan-title", daysText(item.pattern)));
    col.append(title, stats(own.features, other), weekGrid(slotsOf(item.meetings), { range, compact: true }));
    col.append(button("看这个方案", () => { state.selected = own.candidate_id; state.compare = []; renderPlans(); }));
    grid.append(col);
  });
  box.append(grid);
  const byGroup = (item) => new Map(item.option_ids.map((id) => [id.split("|").slice(0, 2).join("|"), id]));
  const groupsA = byGroup(itemA);
  const groupsB = byGroup(itemB);
  const differing = [...groupsA.keys()].filter((group) => groupsA.get(group) !== groupsB.get(group));
  box.append(el("h4", "section-title", differing.length ? `只有 ${differing.length} 门活动的班不同` : "两个方案的班级完全相同"));
  if (differing.length) {
    const slot = (item, group) => {
      const meeting = slotsOf(item.meetings).find((entry) => entry.option_id.startsWith(group)) ||
        item.meetings.find((entry) => entry.option_id.startsWith(group));
      return meeting ? `周${DAY[meeting.weekday - 1]} ${clock(meeting.start_min)}` : "";
    };
    const list = el("ul", "list");
    differing.forEach((group) => {
      const li = el("li");
      li.append(el("b", "", groupName(group)),
        el("span", "", `${planLabel(plans.indexOf(a))}：${groupsA.get(group).split("|").pop()} ${slot(itemA, group)}`),
        el("span", "", `${planLabel(plans.indexOf(b))}：${groupsB.get(group).split("|").pop()} ${slot(itemB, group)}`));
      list.append(li);
    });
    box.append(list);
  }
  return box;
}

/* ===================== enrolment ===================== */

function seatNumber(text) {
  const value = Number.parseInt(text, 10);
  return Number.isFinite(value) ? value : null;
}

function deltaShort(delta) {
  const parts = [];
  if (Math.abs(delta.campus_days) >= 0.05) parts.push(`到校${delta.campus_days > 0 ? "+" : "−"}${Math.abs(delta.campus_days).toFixed(1)} 天`);
  if (Math.abs(delta.gap_min) >= 1) parts.push(`${delta.gap_min > 0 ? "多" : "少"}等 ${Math.round(Math.abs(delta.gap_min))} 分`);
  if (Math.abs(delta.outside_min) >= 1) parts.push(`早晚课${delta.outside_min > 0 ? "+" : "−"}${Math.round(Math.abs(delta.outside_min))} 分`);
  return parts.length ? parts.join("，") : "不变";
}

function enrolmentOrder(item) {
  // Fewest seats and no equal substitute first: those classes are the easiest to lose.
  return Object.entries(item.class_backups || {}).map(([group, info]) => {
    const seats = seatNumber(info.seats);
    return { group, info, seats,
      risk: 2 * (seats === null ? 50 : Math.min(seats, 50)) + (info.equal_codes.length ? 20 : 0) + (info.alternatives ? 5 : 0) };
  }).sort((a, b) => a.risk - b.risk || a.group.localeCompare(b.group));
}

function enrolmentText(item) {
  return enrolmentOrder(item).map(({ group, info }, index) => {
    const backups = info.backups.slice(0, 2).map((backup) => `${backup.code}（${deltaShort(backup.delta)}）`).join("、");
    return `${index + 1}. ${groupName(group)} ${info.code}${info.seats ? `，剩 ${info.seats} 座` : ""}${backups ? `；满了换 ${backups}` : ""}`;
  }).join("\n");
}

async function acceptPlan(item, index, plans, node) {
  node.disabled = true;
  node.textContent = "已选定";
  state.tab = "enrol";
  toast("已选定，去“选课”按顺序报名");
  const tab = [...document.querySelectorAll(".tab")].find((other) => other.textContent === "选课");
  if (tab) tab.click();
  if (!state.result?.saved) return;
  const axes = ["gap", "campus_days", "outside_hours"].filter((axis) => state.cares.has(axis));
  try {
    await post("/api/accept", {
      profile_id: state.result.profile.profile_id, method: state.view === "recommend" ? "recommended" : "shortlist", rank: index + 1,
      candidate_id: item.candidate_id, elapsed_ms: elapsedMs(),
      menu: plans.map((other) => [other.features.gap_min, other.features.campus_days, other.features.outside_min]),
      chosen: index, axes,
    });
  } catch {
    // Recording is optional; the plan is still chosen.
  }
}

/* ===================== hints and adjustments ===================== */

function renderHints(costs) {
  const useful = (costs?.changes || []).filter((change) =>
    change.gain.campus_days > 0.05 || change.gain.gap_min > 15 || change.gain.outside_min > 15);
  if (!useful.length) {
    return costs?.changes?.length && !costs.skipped
      ? el("p", "muted hints-ok", "你设的限制没有让最好的方案变差，放宽也不会更好。") : null;
  }
  const box = el("div", "hints");
  box.append(el("h4", "section-title", "放宽一项会更好"));
  useful.forEach((change) => {
    const gains = [];
    if (change.gain.campus_days > 0.05) gains.push(`每周少到校 ${change.gain.campus_days.toFixed(1)} 天`);
    if (change.gain.gap_min > 15) gains.push(`少等 ${hoursText(change.gain.gap_min)}`);
    if (change.gain.outside_min > 15) gains.push(`早晚课少 ${Math.round(change.gain.outside_min)} 分钟`);
    box.append(hintLine(`${changeLabel(change)}，最多可以${gains.join("、")}`, change, "试试"));
  });
  return box;
}

function renderExplorer(unit, group, pinSelect, currentItem) {
  const current = currentItem ? optionOf(currentItem, group.group_id) : null;
  // Every class of one activity on a week grid, coloured by seats; click one to pin it.
  const box = el("div", "explorer");
  const meetings = group.options.map((option) => ({
    weekday: option.weekday, start_min: minutes(option.start_time) ?? 0, end_min: minutes(option.end_time) ?? 0,
    unit_code: unit.unit_code, group_id: group.group_id, class_code: option.class_code, option_id: option.option_id,
    building_code: option.building_code, is_online: !option.building_code,
    status: option.status, seats: option.available_seats,
  })).filter((meeting) => meeting.end_min > meeting.start_min);
  const overlaps = (meeting, other) => meeting.weekday === other.weekday &&
    meeting.start_min < other.end_min && other.start_min < meeting.end_min;
  const windows = state.blocks.flatMap((block) => block.windows)
    .map((w) => ({ weekday: w.weekday, start_min: w.start_min, end_min: w.end_min }));
  const others = currentItem ? slotsOf(currentItem.meetings).filter((slot) => slot.group_id !== group.group_id) : [];
  const draw = () => {
    box.replaceChildren(weekGrid(meetings, {
      lanes: true,
      decorate: (block, meeting) => {
        const seats = seatNumber(meeting.seats);
        const full = meeting.status === "full" || state.excluded.includes(meeting.option_id);
        const blocked = windows.some((w) => overlaps(meeting, w));
        const clash = others.find((slot) => overlaps(meeting, slot));
        if (full) {
          block.classList.add("full");
          block.style.removeProperty("--c");
        } else {
          block.style.setProperty("--c", seats !== null && seats <= 3 ? "var(--c3)" : "var(--c1)");
        }
        if (blocked && !full) block.classList.add("avoid");
        if (pinSelect.value === meeting.option_id) block.classList.add("picked");
        if (current && current === meeting.option_id) block.classList.add("current");
        const note = full ? "已满" : blocked ? "在你避开的时间"
          : clash && current !== meeting.option_id ? `撞 ${clash.unit_code} ${activityOf(clash)}`
            : meeting.seats ? `剩 ${meeting.seats}` : "余位未知";
        block.title = `${meeting.class_code} · 周${DAY[meeting.weekday - 1]} ${clock(meeting.start_min)}–${clock(meeting.end_min)} · ${meeting.building_code || "线上"} · ${note}`;
        block.replaceChildren(el("b", "", meeting.class_code), el("span", "", note));
        if (full) return;
        block.tabIndex = 0;
        block.setAttribute("role", "button");
        const pick = () => {
          pinSelect.value = pinSelect.value === meeting.option_id ? "" : meeting.option_id;
          pinSelect.dispatchEvent(new Event("change"));
          draw();
        };
        block.addEventListener("click", pick);
        block.addEventListener("keydown", (event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            pick();
          }
        });
      },
    }), el("p", "muted", "绿色有余位，红色余位 ≤ 3，斜纹已满，淡色在你避开的时间，虚框是当前方案的班。点一个班即固定它，再点“重新生成”。"));
  };
  draw();
  return box;
}

function renderAdjust(open) {
  const details = el("details", "adjust");
  details.open = open;
  const summary = el("summary");
  summary.append(el("span", "", "调整课程活动与班级"));
  const pinnedCount = Object.keys(state.pinned).length;
  if (pinnedCount) summary.append(el("span", "count", String(pinnedCount)));
  details.append(summary);
  const data = state.data;
  if (!data) return details;
  const conflict = new Set(state.result?.ranking_result?.conflict_core?.group_ids || []);
  const current = state.result?.ranking_result?.shortlist && state.selected
    ? shownItem(state.result.ranking_result.shortlist.items[state.selected] || {}) : null;
  const container = el("div", "groups");
  container.append(el("p", "muted", "不勾选的活动不参与排课（比如 Lecture 看录播）；选定某个班会固定它。"));
  (data.units || []).forEach((unit) => {
    const fieldset = el("fieldset", "unit-groups");
    const legend = el("legend");
    legend.style.setProperty("--c", `var(--c${courseIndex(unit.unit_code)})`);
    legend.append(el("i", "dot"), document.createTextNode(unit.unit_code));
    fieldset.append(legend);
    unit.groups.forEach((group) => {
      const row = el("div", `group-row${conflict.has(group.group_id) ? " conflict" : ""}`);
      const label = el("label");
      const checkbox = el("input");
      checkbox.type = "checkbox";
      checkbox.value = group.group_id;
      checkbox.dataset.unit = unit.unit_code;
      checkbox.checked = (state.groups?.[unit.unit_code] || []).includes(group.group_id);
      label.append(checkbox, document.createTextNode(`${group.group_id.split("|").pop()}${conflict.has(group.group_id) ? "（冲突）" : ""}`));
      row.append(label);
      if (!group.default_selected && group.default_reason) row.append(el("span", "muted", group.default_reason));
      fieldset.append(row);
      if ((group.options || []).length > 1) {
        const pin = el("select", "select");
        pin.dataset.group = group.group_id;
        pin.setAttribute("aria-label", `${group.group_id.split("|").pop()} 班级`);
        const any = el("option", "", `任意班（共 ${group.options.length} 个）`);
        any.value = "";
        pin.append(any);
        group.options.forEach((option) => {
          const seats = option.status === "full" ? " · 满" : option.available_seats ? ` · 剩 ${option.available_seats}` : "";
          const choice = el("option", "", `${option.class_code} · 周${DAY[option.weekday - 1]} ${option.start_time}${seats}`);
          choice.value = option.option_id;
          pin.append(choice);
        });
        pin.value = (state.pinned[group.group_id] || [""])[0];
        pin.addEventListener("change", () => { if (pin.value) checkbox.checked = true; });
        const explorerHolder = el("div");
        const browse = button("看全部班级", (node) => {
          const open = !explorerHolder.childElementCount;
          explorerHolder.replaceChildren(...(open ? [renderExplorer(unit, group, pin, current)] : []));
          node.classList.toggle("on", open);
        });
        row.append(pin, browse);
        fieldset.append(explorerHolder);
      }
    });
    container.append(fieldset);
  });
  const actions = el("div", "groups-actions");
  const error = el("p", "field-error");
  actions.append(button("重新生成", () => {
    const groups = {};
    container.querySelectorAll("input[type=checkbox]").forEach((input) => {
      groups[input.dataset.unit] = groups[input.dataset.unit] || [];
      if (input.checked) groups[input.dataset.unit].push(input.value);
    });
    const empty = Object.entries(groups).find(([, ids]) => !ids.length);
    if (empty) {
      error.textContent = `${empty[0]} 至少要保留一项`;
      return;
    }
    const chosen = Object.values(groups).flat();
    const pinned = {};
    container.querySelectorAll("select[data-group]").forEach((pin) => {
      if (pin.value && chosen.includes(pin.dataset.group)) pinned[pin.dataset.group] = [pin.value];
    });
    replan("已按调整重新生成", { groups, pinned });
  }, { className: "button primary" }), button("Lecture 都看录播", () => {
    container.querySelectorAll("input[type=checkbox]").forEach((input) => {
      if (/lecture/i.test(input.value.split("|").pop())) input.checked = false;
    });
    toast("已取消所有 Lecture，点“重新生成”");
  }), button("清除固定", () => {
    container.querySelectorAll("select[data-group]").forEach((pin) => { pin.value = ""; });
    toast("已清除所有固定的班，点“重新生成”");
  }, { className: "button ghost" }));
  container.append(actions, error);
  details.append(container);
  return details;
}

/* ===================== calendar export and building changes ===================== */

function hhmm(value) {
  return `${String(Math.floor(value / 60)).padStart(2, "0")}${String(value % 60).padStart(2, "0")}`;
}

function icsEscape(text) {
  return String(text).replace(/\\/g, "\\\\").replace(/\n/g, "\\n").replace(/([,;])/g, "\\$1");
}

function icsFold(line) {
  // RFC 5545: lines longer than 75 octets continue on a line starting with a space.
  const encoder = new TextEncoder();
  const out = [];
  let current = "";
  let bytes = 0;
  for (const ch of line) {
    const size = encoder.encode(ch).length;
    if (bytes + size > 73) {
      out.push(current);
      current = ` ${ch}`;
      bytes = 1 + size;
    } else {
      current += ch;
      bytes += size;
    }
  }
  out.push(current);
  return out.join("\r\n");
}

const SYDNEY_VTIMEZONE = [
  "BEGIN:VTIMEZONE", "TZID:Australia/Sydney",
  "BEGIN:STANDARD", "DTSTART:19700405T030000", "RRULE:FREQ=YEARLY;BYMONTH=4;BYDAY=1SU",
  "TZOFFSETFROM:+1100", "TZOFFSETTO:+1000", "TZNAME:AEST", "END:STANDARD",
  "BEGIN:DAYLIGHT", "DTSTART:19701004T020000", "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=1SU",
  "TZOFFSETFROM:+1000", "TZOFFSETTO:+1100", "TZNAME:AEDT", "END:DAYLIGHT",
  "END:VTIMEZONE",
];

function downloadIcs(item) {
  const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
  const lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//UniPlan//Timetable//ZH",
    "CALSCALE:GREGORIAN", "X-WR-CALNAME:UniPlan 课表", ...SYDNEY_VTIMEZONE];
  item.meetings.forEach((meeting, index) => {
    const day = meeting.date.replace(/-/g, "");
    const place = meeting.is_online ? "Online" :
      (meeting.location_raw && meeting.location_raw !== "-" ? meeting.location_raw : meeting.building_code || "");
    lines.push("BEGIN:VEVENT", `UID:${item.candidate_id}-${index}@uniplan.local`, `DTSTAMP:${stamp}`,
      `DTSTART;TZID=Australia/Sydney:${day}T${hhmm(meeting.start_min)}00`,
      `DTEND;TZID=Australia/Sydney:${day}T${hhmm(meeting.end_min)}00`,
      `SUMMARY:${icsEscape(`${meeting.unit_code} ${activityOf(meeting)} ${meeting.class_code || ""}`.trim())}`,
      `LOCATION:${icsEscape(place)}`, "END:VEVENT");
  });
  lines.push("END:VCALENDAR");
  const blob = new Blob([`${lines.map(icsFold).join("\r\n")}\r\n`], { type: "text/calendar;charset=utf-8" });
  const link = el("a");
  link.href = URL.createObjectURL(blob);
  link.download = `uniplan-${state.units.map((unit) => unit.code).join("-")}.ics`;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 2000);
}

function distanceMetres(a, b) {
  const rad = Math.PI / 180;
  const dLat = (b.latitude - a.latitude) * rad;
  const dLon = (b.longitude - a.longitude) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.latitude * rad) * Math.cos(b.latitude * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * 6371000 * Math.asin(Math.sqrt(h));
}

function tightTransfers(meetings) {
  // Back-to-back in-person classes in different buildings, once per weekly pattern.
  const byDate = new Map();
  meetings.filter((meeting) => !meeting.is_online && meeting.building_code).forEach((meeting) => {
    if (!byDate.has(meeting.date)) byDate.set(meeting.date, []);
    byDate.get(meeting.date).push(meeting);
  });
  const seen = new Map();
  byDate.forEach((daily) => {
    daily.sort((a, b) => a.start_min - b.start_min);
    daily.slice(1).forEach((next, index) => {
      const prev = daily[index];
      const gap = next.start_min - prev.end_min;
      if (prev.building_code === next.building_code || gap > 15) return;
      const key = `${next.weekday}|${prev.end_min}|${prev.building_code}|${next.building_code}`;
      if (seen.has(key)) return;
      const a = prev.building_location;
      const b = next.building_location;
      const walk = a?.latitude != null && b?.latitude != null
        ? `，步行约 ${Math.max(1, Math.round((distanceMetres(a, b) * 1.3) / 80))} 分钟` : "";
      seen.set(key, `周${DAY[next.weekday - 1]} ${clock(prev.end_min)} 从 ${prev.building_code} 到 ${next.building_code} 只有 ${gap} 分钟${walk}`);
    });
  });
  return [...seen.values()];
}

/* ===================== preference study (?study=1, for the pilot) ===================== */

function renderStudy(study) {
  const box = el("section", "study");
  box.append(el("h3", "", "偏好比较"));
  if (!study.available) {
    box.append(el("p", "muted", study.reason));
    return box;
  }
  box.append(button(`开始（${study.pairs.length} 组）`, () => runStudy(study, box)));
  return box;
}

function studyCard(card, letter) {
  const box = el("div", "plan");
  const head = el("div", "plan-head");
  head.append(el("span", "avatar", letter));
  const meetings = card.slots.filter((slot) => slot.weeks >= 3).map((slot) => ({
    weekday: slot.weekday, start_min: slot.start_min, end_min: slot.end_min, unit_code: slot.unit_code,
    group_id: slot.activity, is_online: slot.online, class_code: "",
  }));
  box.append(head, stats(card.features), weekGrid(meetings, { thumb: true }));
  return box;
}

function runStudy(study, box) {
  const answers = new Map();
  const started = performance.now();
  let index = 0;
  const stage = el("div");
  box.replaceChildren(el("h3", "", "偏好比较"), stage);
  const choose = (choice) => {
    answers.set(study.pairs[index].pair_id, choice);
    index += 1;
    if (index < study.pairs.length) draw(); else submit();
  };
  function draw() {
    const pair = study.pairs[index];
    stage.replaceChildren(el("p", "muted", `${index + 1} / ${study.pairs.length} · 你更想要哪一个？`));
    const grid = el("div", "pair");
    grid.append(studyCard(study.schedules[pair.left], "A"), studyCard(study.schedules[pair.right], "B"));
    const row = el("div", "choice-row");
    row.append(button("A", () => choose("left"), { className: "button primary" }),
      button("差不多", () => choose("tie")), button("B", () => choose("right"), { className: "button primary" }));
    stage.append(grid, row);
  }
  async function submit() {
    stage.replaceChildren(el("p", "muted", "计算中…"));
    try {
      const data = await post("/api/study", {
        study_id: study.study_id,
        answers: [...answers].map(([pair_id, choice]) => ({ pair_id, choice })),
        elapsed_ms: Math.round(performance.now() - started),
      });
      if (data.error) throw new Error(data.error);
      stage.replaceChildren();
      if (data.status !== "learned") {
        stage.append(el("p", "", data.message));
        return;
      }
      const bars = el("div", "bars");
      data.model.axes.forEach((axis) => {
        const row = el("div", "bar");
        const track = el("div");
        const fill = el("i");
        fill.style.width = `${Math.round(axis.share * 100)}%`;
        track.append(fill);
        row.append(el("span", "", AXIS_CHIP[axis.axis]), track, el("span", "", `${Math.round(axis.share * 100)}%`));
        bars.append(row);
      });
      const result = data.evaluation;
      const percent = (value) => (value == null ? "—" : `${Math.round(value * 100)}%`);
      stage.append(el("p", "muted", "你的选择显示的偏好"), bars,
        el("p", "muted", `留出检验：学习 ${percent(result.learned?.accuracy)} · 等权 ${percent(result.equal_weight?.accuracy)} · 随机 50%`));
    } catch (error) {
      stage.replaceChildren(el("p", "", `无法完成：${error.message}`));
    }
  }
  draw();
}

/* ===================== sharing, bookmarks, copying ===================== */

function encodeShare(value) {
  const bytes = new TextEncoder().encode(JSON.stringify(value));
  let binary = "";
  bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function parseShare(hash) {
  if (!hash || !hash.startsWith("p=")) return null;
  try {
    const binary = atob(hash.slice(2).replace(/-/g, "+").replace(/_/g, "/"));
    const value = JSON.parse(new TextDecoder().decode(Uint8Array.from(binary, (ch) => ch.charCodeAt(0))));
    return value && value.v === 1 && Array.isArray(value.units) ? value : null;
  } catch {
    return null;
  }
}

function shareState(item = null) {
  const value = { v: 1, term: $("termSelect").value, units: state.units.map((unit) => unit.code),
    blocks: state.blocks, settings: settingsSnapshot(), cares: [...state.cares] };
  if (item) {
    value.plan = item.option_ids;
    // The weekly routine lets a friend's page find free time in common without re-planning.
    value.slots = slotsOf(item.meetings).map((slot) => ({ weekday: slot.weekday, start_min: slot.start_min,
      end_min: slot.end_min, is_online: Boolean(slot.is_online) }));
  }
  return value;
}

function shareUrl(item) {
  return `${location.origin}${location.pathname}#p=${encodeShare(shareState(item))}`;
}

function writeShareHash() {
  try {
    history.replaceState(null, "", `#p=${encodeShare(shareState())}`);
  } catch {
    // Embedded views may forbid history changes; the share button still works.
  }
}

function restoreShare(shared) {
  if (shared.term && [...$("termSelect").options].some((option) => option.value === shared.term)) {
    $("termSelect").value = shared.term;
  }
  state.units = [];
  shared.units.slice(0, 5).forEach((code) => addUnit(code));
  state.blocks = (shared.blocks || []).filter((block) => Array.isArray(block.windows));
  renderBlocks();
  restoreSettings(shared.settings);
  if (Array.isArray(shared.cares) && shared.cares.length) state.cares = new Set(shared.cares.filter((axis) => AXES.includes(axis)));
  if (!state.cares.size) state.cares = new Set(AXES);
  state.sharedPlan = Array.isArray(shared.plan) ? shared.plan : null;
  state.say = null;
  $("sayText").value = "";
  renderSay();
  document.querySelectorAll(".setting.said").forEach((row) => row.classList.remove("said"));
}

async function copyText(text, done) {
  try {
    await navigator.clipboard.writeText(text);
    toast(done);
  } catch {
    window.prompt("复制以下内容", text);
  }
}

function loadFavourites() {
  try {
    return JSON.parse(localStorage.getItem("uniplan:saved") || "[]");
  } catch {
    return [];
  }
}

function storeFavourites(list) {
  try {
    localStorage.setItem("uniplan:saved", JSON.stringify(list.slice(0, 20)));
  } catch {
    // Private windows may block storage; bookmarks are only a convenience.
  }
  renderFavourites();
}

function saveFavourite(item, letter) {
  const title = `${state.units.map((unit) => unit.code).join(" · ")} · ${state.view === "recommend" ? "推荐" : "方案"} ${letter} · ${daysText(item.pattern)}`;
  const list = loadFavourites().filter((entry) => entry.title !== title);
  storeFavourites([{ title, url: shareUrl(item), at: new Date().toISOString().slice(0, 10) }, ...list]);
}

function renderFavourites() {
  const box = $("saved");
  const list = loadFavourites();
  box.replaceChildren();
  if (!list.length) {
    box.hidden = true;
    return;
  }
  box.append(el("span", "field-label", "收藏的方案"));
  list.forEach((entry, index) => {
    const row = el("div", "saved-row");
    const link = el("a", "", entry.title);
    link.href = entry.url;
    link.addEventListener("click", (event) => {
      event.preventDefault();
      const shared = parseShare(entry.url.split("#")[1] || "");
      if (!shared) return;
      restoreShare(shared);
      const profile = buildProfile();
      if (profile) plan(profile);
    });
    const remove = el("button", "remove", "×");
    remove.type = "button";
    remove.setAttribute("aria-label", "删除收藏");
    remove.addEventListener("click", () => storeFavourites(loadFavourites().filter((_, position) => position !== index)));
    row.append(link, el("span", "muted", entry.at), remove);
    box.append(row);
  });
  box.hidden = !$("setupSummary").hidden;
}

/* ===================== withdraw ===================== */

async function withdrawSaved(event) {
  event.preventDefault();
  const code = $("withdrawCode").value.trim().toLowerCase();
  const message = $("withdrawMessage");
  if (!/^[0-9a-f]{32}$/.test(code)) {
    message.textContent = "请输入完整的 32 位参与码";
    return;
  }
  try {
    const response = await fetch(`/api/profiles/${code}`, { method: "DELETE" });
    const data = await response.json();
    message.textContent = data.removed ? "已删除" : "没有找到这个参与码";
  } catch {
    message.textContent = "暂时无法连接";
  }
}

/* ===================== start ===================== */

function typingTarget(target) {
  return target.closest("input, select, textarea, [contenteditable]");
}

async function start() {
  applyTheme();
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { if (!storedTheme()) applyTheme(); });
  $("themeToggle").addEventListener("click", toggleTheme);

  fillTimes($("preferredStart"), 7 * 60, 13 * 60, "09:00");
  fillTimes($("preferredEnd"), 13 * 60, 22 * 60, "18:00");
  fillTimes($("lunchStart"), 10 * 60, 14 * 60, "11:30");
  fillTimes($("lunchEnd"), 12 * 60, 16 * 60, "14:00");
  fillTimes($("customStart"), 7 * 60, 22 * 60, "09:00");
  fillTimes($("customEnd"), 7 * 60 + 30, 23 * 60 + 30, "12:00");
  document.querySelectorAll(".segmented[data-target]").forEach((group) => {
    group.addEventListener("click", (event) => {
      const choice = event.target.closest("button");
      if (!choice) return;
      $(group.dataset.target).value = choice.dataset.value;
      group.closest(".setting")?.classList.remove("said");
      updateSettingsCount();
    });
  });

  try {
    const response = await fetch("/api/catalog");
    const data = await response.json();
    const seen = new Set();
    (data.snapshots || []).forEach((snap) => {
      const value = `${snap.year}|${snap.session_code}`;
      if (seen.has(value)) return;
      seen.add(value);
      const option = el("option", "", `${snap.year} ${snap.session_code}`);
      option.value = value;
      $("termSelect").append(option);
    });
  } catch {
    // The form still works; suggestions just stay empty.
  }
  $("unitQuery").addEventListener("input", searchUnits);
  $("unitQuery").addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      hideSuggestions();
    } else if (event.key === "ArrowDown" && state.matches.length) {
      event.preventDefault();
      state.activeMatch = (state.activeMatch + 1) % state.matches.length;
      renderSuggestions();
    } else if (event.key === "ArrowUp" && state.matches.length) {
      event.preventDefault();
      state.activeMatch = (state.activeMatch - 1 + state.matches.length) % state.matches.length;
      renderSuggestions();
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (state.activeMatch >= 0) {
        addUnit(state.matches[state.activeMatch].unit_code, state.matches[state.activeMatch].unit_name);
      } else if ($("unitQuery").value.trim()) {
        const exact = state.matches.find((item) => item.unit_code === $("unitQuery").value.trim().toUpperCase());
        addUnit($("unitQuery").value, exact?.unit_name || "");
      }
    } else if (event.key === "Backspace" && !$("unitQuery").value && state.units.length) {
      state.units.pop();
      renderUnits();
    }
  });
  document.querySelectorAll(".preset[data-preset]").forEach((preset) => preset.addEventListener("click", () => {
    const chosen = PRESETS[preset.dataset.preset];
    addBlock(preset.dataset.preset, chosen.label, chosen.windows);
  }));
  $("customToggle").addEventListener("click", () => { $("customBlock").hidden = !$("customBlock").hidden; });
  $("customAdd").addEventListener("click", addCustomBlock);
  [...SETTING_FIELDS, ...SETTING_CHECKS].forEach((id) => $(id).addEventListener("change", () => {
    $(id).closest(".setting")?.classList.remove("said");
    updateSettingsCount();
  }));
  updateSettingsCount();
  renderFavourites();
  $("profileForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = $("sayText").value.trim();
    if (text && text !== state.say?.text) {
      // Show what was understood first; the student confirms by pressing the button again.
      if (await readSay()) toast("已按你的话填好设置，确认无误再点“生成课表”");
      return;
    }
    const profile = buildProfile();
    if (profile) plan(profile);
  });
  $("sayRead").addEventListener("click", readSay);
  $("sayText").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      readSay();
    }
  });
  $("profileForm").addEventListener("focusin", () => {
    if (state.firstInteraction === null) state.firstInteraction = performance.now();
  });
  $("editSetup").addEventListener("click", () => {
    collapseSetup(false);
    $("profileForm").scrollIntoView({ behavior: "smooth", block: "start" });
  });
  $("withdrawToggle").addEventListener("click", () => { $("withdrawForm").hidden = !$("withdrawForm").hidden; });
  $("withdrawForm").addEventListener("submit", withdrawSaved);
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".course-input-wrap")) hideSuggestions();
  });
  document.addEventListener("keydown", (event) => {
    // ← / → move between weeks while the week tab is open.
    if (!["ArrowLeft", "ArrowRight"].includes(event.key) || typingTarget(event.target) || event.metaKey || event.ctrlKey || event.altKey) return;
    const view = document.querySelector("[data-week-nav]");
    if (!view) return;
    event.preventDefault();
    view.dispatchEvent(new CustomEvent("weekstep", { detail: event.key === "ArrowLeft" ? -1 : 1 }));
  });
  const shared = parseShare(location.hash.slice(1));
  if (shared) {
    restoreShare(shared);
    const profile = buildProfile();
    if (profile) plan(profile);
  }
}

start();
