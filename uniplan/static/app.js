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

const DAY = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const DAY_LONG = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
  "October", "November", "December"];
const AXES = ["campus_days", "gap", "outside_hours"];
const AXIS_FEATURE = { gap: "gap_min", campus_days: "campus_days", outside_hours: "outside_min" };
const AXIS_CHIP = { campus_days: "Fewer days on campus", gap: "Less waiting", outside_hours: "Fewer early or late classes" };
const AXIS_TAG = { campus_days: "fewest days on campus", gap: "least waiting", outside_hours: "least early or late class" };
const PRESETS = {
  mon: { label: "Mondays", windows: [[1, 0, 1439]] },
  fri: { label: "Fridays", windows: [[5, 0, 1439]] },
  early: { label: "Weekdays before 10 am", windows: [1, 2, 3, 4, 5].map((day) => [day, 0, 600]) },
  late: { label: "Weekdays after 6 pm", windows: [1, 2, 3, 4, 5].map((day) => [day, 1080, 1439]) },
};
const COURSE_COLOURS = 5; // sandstone, eucalypt, harbour, jacaranda, brick (docs/DESIGN.md)
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
  say: null, view: "all", viewPicked: false, reasons: {},
  // Whether the student has stated an order for "What matters" (state.cares keeps insertion order).
  caresTouched: false,
};

function minutes(value) {
  if (!/^\d{2}:\d{2}$/.test(value || "")) return null;
  const [hour, minute] = value.split(":").map(Number);
  return hour <= 23 && minute <= 59 ? hour * 60 + minute : null;
}

function clock(value) {
  // The value of a time field: "09:00".
  return `${String(Math.floor(value / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`;
}

function keepUnits(text) {
  // A number stays on the same line as its unit: "3 h 14 min", "6 pm", "2.8 days".
  return String(text).replace(/(\d) (?=(?:h|min|days?|am|pm)\b)/g, "$1\u00a0").replace(/\bh (?=\d)/g, "h\u00a0");
}

function timeText(value) {
  // How a time reads on the page: "9 am", "6:30 pm".
  if (value >= 1440) return "midnight";
  const hour = Math.floor(value / 60);
  const minute = value % 60;
  return keepUnits(`${hour % 12 || 12}${minute ? `:${String(minute).padStart(2, "0")}` : ""} ${hour < 12 ? "am" : "pm"}`);
}

function spanText(start, end) {
  return `${timeText(start)} to ${timeText(end)}`;
}

function durationText(minutes) {
  // 72 -> "1 h 12 min", 45 -> "45 min".
  const total = Math.round(minutes);
  const hours = Math.floor(total / 60);
  const rest = total % 60;
  if (!hours) return keepUnits(`${rest} min`);
  return keepUnits(rest ? `${hours} h ${rest} min` : `${hours} h`);
}

function joinWords(words, last = "and") {
  return words.length <= 1 ? words.join("") : `${words.slice(0, -1).join(", ")} ${last} ${words[words.length - 1]}`;
}

function plural(count, word) {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

function termName(year, sessionCode) {
  const semester = /^S([12])/.exec(sessionCode || "");
  return semester ? `Semester ${semester[1]}, ${year}` : `${sessionCode} ${year}`;
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
  return pattern ? [...pattern].map((day) => DAY[Number(day) - 1]).join(", ") : "No set campus days";
}

function hoursText(minutesPerWeek) {
  return durationText(minutesPerWeek);
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

function dateText(isoDate) {
  // "12 October", the Australian way.
  return `${Number(isoDate.slice(8, 10))} ${MONTHS[Number(isoDate.slice(5, 7)) - 1]}`;
}

function dayDate(isoDate) {
  // "Mon 12 October".
  return `${DAY[weekdayOf(isoDate) - 1]} ${dateText(isoDate)}`;
}

function rangeText(from, to) {
  // "12 to 18 October", or "28 September to 4 October".
  return from.slice(5, 7) === to.slice(5, 7) ? `${Number(from.slice(8, 10))} to ${dateText(to)}`
    : `${dateText(from)} to ${dateText(to)}`;
}

function elapsedMs() {
  return state.firstInteraction === null ? null : Math.round(performance.now() - state.firstInteraction);
}

function setError(id, message) {
  $(id).textContent = message || "";
}

function announce(text) {
  // One short line for screen readers; the redrawn regions themselves are not live.
  const box = $("announce");
  box.textContent = "";
  setTimeout(() => { box.textContent = text || ""; }, 60); // a fresh change, so the same words are read again
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
  }, Math.max(2400, message.length * 60));
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
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", dark ? "#14161d" : "#ffffff");
  $("themeToggle").textContent = dark ? "Light" : "Dark";
  $("themeToggle").setAttribute("aria-label", dark ? "Use the light theme" : "Use the dark theme");
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
  $("unitQuery").removeAttribute("aria-activedescendant");
  state.activeMatch = -1;
}

function renderSuggestions() {
  // A combobox: focus stays in the field, arrow keys move the highlighted option.
  const list = $("suggestions");
  list.replaceChildren();
  if (!state.matches.length) {
    hideSuggestions();
    return;
  }
  state.matches.forEach((item, index) => {
    const li = el("li");
    li.id = `suggestion-${index}`;
    li.setAttribute("role", "option");
    li.setAttribute("aria-selected", String(index === state.activeMatch));
    li.append(el("span", "suggest-code", item.unit_code), el("span", "suggest-name", item.unit_name));
    if (!item.available_in_snapshot) li.append(el("span", "suggest-note", "No timetable data"));
    li.addEventListener("mousedown", (event) => event.preventDefault()); // keep focus in the field
    li.addEventListener("click", () => addUnit(item.unit_code, item.unit_name));
    list.append(li);
  });
  list.hidden = false;
  $("unitQuery").setAttribute("aria-expanded", "true");
  if (state.activeMatch >= 0) {
    $("unitQuery").setAttribute("aria-activedescendant", `suggestion-${state.activeMatch}`);
    $(`suggestion-${state.activeMatch}`).scrollIntoView({ block: "nearest" });
  } else {
    $("unitQuery").removeAttribute("aria-activedescendant");
  }
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
    const swatch = el("i", "swatch");
    paint(swatch, unit.code);
    const code = el("strong", "", unit.code);
    code.translate = false;
    chip.append(swatch, code);
    if (unit.name) chip.append(el("span", "name", unit.name));
    const remove = el("button", "", "×");
    remove.type = "button";
    remove.setAttribute("aria-label", `Remove ${unit.code}`);
    remove.addEventListener("click", () => {
      state.units = state.units.filter((other) => other.code !== unit.code);
      renderUnits();
    });
    chip.append(remove);
    box.append(chip);
  });
  $("unitQuery").placeholder = state.units.length ? (state.units.length >= 5 ? "5 units at most" : "Add another unit")
    : "Add a unit, like ENGG2112";
}

function addUnit(code, name = "") {
  code = code.trim().toUpperCase();
  if (!/^[A-Z]{4}\d{4}$/.test(code)) {
    setError("unitError", "A unit code is 4 letters and 4 digits, like ENGG2112.");
    return false;
  }
  if (state.units.some((unit) => unit.code === code)) {
    setError("unitError", `${code} is already added.`);
    return false;
  }
  if (state.units.length >= 5) {
    setError("unitError", "You can add up to 5 units. Remove one first.");
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
    remove.setAttribute("aria-label", `Remove ${block.label}`);
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
    setError("windowError", "The end time must be after the start time.");
    return;
  }
  setError("windowError", "");
  addBlock(null, windowsLabel([{ weekday: day, start_min: start, end_min: end }]), [[day, start, end]]);
}

/* ===================== settings ===================== */

const SETTING_FIELDS = ["preferredStart", "preferredEnd", "maxDaily", "maxSpan", "lunchStart", "lunchEnd",
  "lunchMinutes", "maxDays", "commute", "transition", "walkSpeed", "minSeats"];
const SETTING_CHECKS = ["lunchOn", "inPerson"];

function fillTimes(select, from, to, value) {
  for (let minute = from; minute <= to; minute += 30) {
    const option = el("option", "", timeText(minute));
    option.value = clock(minute);
    select.append(option);
  }
  select.value = value;
}

function setField(id, value) {
  // Old share links may carry times that are not on the half-hour list.
  const field = $(id);
  if (field.tagName === "SELECT" && value !== "" && ![...field.options].some((option) => option.value === value)) {
    const extra = el("option", "", minutes(value) === null ? value : timeText(minutes(value)));
    extra.value = value;
    field.append(extra);
  }
  field.value = value;
}

function syncSegmented() {
  // Option groups behave as radio groups: one tab stop, the chosen option checked.
  document.querySelectorAll(".segmented[data-target]").forEach((group) => {
    const value = $(group.dataset.target).value;
    group.querySelectorAll("button").forEach((choice) => {
      const on = choice.dataset.value === value;
      choice.setAttribute("role", "radio");
      choice.setAttribute("aria-checked", String(on));
      choice.tabIndex = on ? 0 : -1;
    });
  });
}

function radioKeys(group) {
  // Arrow keys move to the next option and choose it, as in a native radio group.
  group.addEventListener("keydown", (event) => {
    const keys = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
    if (!(event.key in keys) && event.key !== "Home" && event.key !== "End") return;
    const choices = [...group.querySelectorAll("[role=radio]")].filter((choice) => !choice.disabled);
    const at = choices.indexOf(document.activeElement);
    if (at < 0 || !choices.length) return;
    event.preventDefault();
    const next = event.key === "Home" ? 0 : event.key === "End" ? choices.length - 1
      : (at + keys[event.key] + choices.length) % choices.length;
    choices[next].focus();
    choices[next].click();
  });
}

function paint(node, code) {
  // A unit's colour: a light fill and a darker edge of the same hue.
  const index = courseIndex(code);
  node.style.setProperty("--fill", `var(--c${index}-fill)`);
  node.style.setProperty("--edge", `var(--c${index}-edge)`);
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
  $("moreCount").textContent = `${count} set`;
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

// Which form controls each parsed field fills in.
const SAY_CONTROLS = {
  max_days_per_week: ["maxDays"], max_daily_minutes: ["maxDaily"], max_daily_span: ["maxSpan"],
  lunch: ["lunchOn", "lunchStart", "lunchEnd", "lunchMinutes"], in_person_only: ["inPerson"],
  preferred_hours: ["preferredStart", "preferredEnd"],
};

function hoursLabel(value) {
  return String(Number((value / 60).toFixed(2)));
}

function capital(text) {
  return text ? text[0].toUpperCase() + text.slice(1) : text;
}

function windowsLabel(windows) {
  // "Fri", "weekdays before 10 am", "Tue and Thu after 6 pm", "Wed 2 pm to 6 pm"
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
    const dayText = days.join() === "1,2,3,4,5" ? "weekdays" : days.join() === "6,7" ? "weekends"
      : run ? `${DAY[days[0] - 1]} to ${DAY[days[days.length - 1] - 1]}` : joinWords(days.map((day) => DAY[day - 1]));
    const time = start <= 0 && end >= 1439 ? "" : start <= 0 ? ` before ${timeText(end)}`
      : end >= 1439 ? ` after ${timeText(start)}` : ` ${spanText(start, end)}`;
    return `${dayText}${time}`;
  }).join("; ");
}

function setSegment(target, value, text) {
  // Parsed values may not be one of the preset options; add one so the choice stays visible.
  const group = document.querySelector(`.segmented[data-target="${target}"]`);
  if (group && ![...group.querySelectorAll("button")].some((choice) => choice.dataset.value === value)) {
    const extra = el("button", "", text);
    extra.type = "button";
    extra.dataset.value = value;
    // Keep the numbers in order ("No limit" has no number and stays first).
    const after = [...group.querySelectorAll("button")].find((choice) =>
      choice.dataset.value !== "" && Number(choice.dataset.value) > Number(value));
    group.insertBefore(extra, after || null);
  }
  $(target).value = value;
}

function sayControls(item) {
  return Object.keys(item.profile_fields).flatMap((key) => SAY_CONTROLS[key] || []);
}

function chosen(say, q) {
  return say.questions[q].options[say.answers[q] || 0];
}

function sayItems(say) {
  // What the sentence and the answers add: one item per clause (its own fields, overridden by the
  // option chosen for a question about it) and one per offer the student took up.
  const items = say.clauses.map((clause, index) => {
    let fields = clause.profile_fields;
    let cares = clause.cares;
    say.questions.forEach((question, q) => {
      if (question.kind === "offer" || question.clause_index !== index) return;
      const option = chosen(say, q);
      fields = { ...fields, ...option.profile_fields };
      cares = [...cares, ...option.cares.filter((care) => !cares.includes(care))];
    });
    return { key: `say${index}`, clause, profile_fields: fields, cares, on: say.on[index] };
  });
  say.questions.forEach((question, q) => {
    const option = chosen(say, q);
    if (question.kind === "offer" && (Object.keys(option.profile_fields).length || option.cares.length)) {
      items.push({ key: `sayask${q}`, profile_fields: option.profile_fields, cares: option.cares, on: true });
    }
  });
  return items;
}

function unapplySay() {
  // Back to the form as it was before the sentence was applied.
  const say = state.say;
  if (!say) return;
  state.blocks = state.blocks.filter((block) => !String(block.key || "").startsWith("say"));
  const options = say.questions.flatMap((question) => question.options);
  const touched = new Set([...say.clauses, ...options].flatMap(sayControls));
  touched.forEach((id) => {
    if (SETTING_CHECKS.includes(id)) $(id).checked = say.base.settings[id];
    else setField(id, say.base.settings[id]);
  });
  state.cares = new Set(say.base.cares);
  state.caresTouched = say.base.caresTouched;
}

function applySay() {
  const say = state.say;
  unapplySay();
  const cares = new Set();
  const used = sayItems(say).filter((item) => item.on);
  used.forEach((item) => {
    const f = item.profile_fields;
    if (f.unavailable_windows) {
      state.blocks.push({ key: item.key, label: capital(windowsLabel(f.unavailable_windows)),
        windows: f.unavailable_windows.map(({ weekday, start_min, end_min }) => ({ weekday, start_min, end_min })) });
    }
    if (f.max_days_per_week) setSegment("maxDays", String(f.max_days_per_week), String(f.max_days_per_week));
    if (f.max_daily_minutes) setSegment("maxDaily", hoursLabel(f.max_daily_minutes), `${hoursLabel(f.max_daily_minutes)} h`);
    if (f.max_daily_span) setSegment("maxSpan", hoursLabel(f.max_daily_span), `${hoursLabel(f.max_daily_span)} h`);
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
    item.cares.forEach((care) => cares.add(care));
  });
  if (cares.size) {
    state.cares = cares; // in the order the sentence states them: the first is the main concern
    state.caresTouched = true;
  }
  renderBlocks();
  updateSettingsCount();
  document.querySelectorAll(".setting.from-sentence").forEach((row) => row.classList.remove("from-sentence"));
  const said = used.flatMap(sayControls);
  said.forEach((id) => $(id).closest(".setting")?.classList.add("from-sentence"));
  if (said.length) $("moreSettings").open = true;
}

async function answer(q, o) {
  // An answer to a question about a clause re-reads that clause as the chosen type; an offer is
  // applied like a setting. Questions stay as first asked, so any answer can be changed back,
  // and an offer answered here is never asked again by a later re-read.
  const say = state.say;
  const before = say.answers[q] || 0;
  if (before === o || say.busy) return;
  const question = say.questions[q];
  say.answers[q] = o;
  say.focus = `[data-q="${q}"][data-o="${o}"]`;
  if (question.kind !== "offer") {
    if (o) say.on[question.clause_index] = true;
    const overrides = {};
    say.questions.forEach((other, index) => {
      const option = chosen(say, index);
      // Only a different type needs the clause read again; a value answer keeps its type.
      if (other.kind !== "offer" && option.label && option.label !== say.firstLabels[other.clause_index]) {
        overrides[other.clause_index] = option.label;
      }
    });
    if (JSON.stringify(overrides) !== JSON.stringify(say.overrides)) {
      say.busy = true;
      renderSay();
      try {
        const data = await post("/api/parse", { text: say.text, overrides });
        if (!data.clauses || data.clauses.length !== say.clauses.length) {
          throw new Error(data.error || "The sentence could not be read again with that answer. Try again, or set it below.");
        }
        unapplySay();
        Object.assign(say, { clauses: data.clauses, mode: data.mode, overrides });
      } catch (error) {
        say.answers[q] = before;
        say.focus = `[data-q="${q}"][data-o="${before}"]`;
        setError("sayError", error.message);
      } finally {
        say.busy = false;
      }
    }
  }
  applySay();
  renderSay();
}

function renderOptions(say, question, q, labelledBy) {
  // The options of one question as a radio group; the first is what was already assumed.
  const group = el("div", "segmented");
  group.setAttribute("role", "radiogroup");
  group.setAttribute("aria-labelledby", labelledBy);
  question.options.forEach((option, o) => {
    const on = (say.answers[q] || 0) === o;
    const choice = el("button", "", keepUnits(option.text));
    choice.type = "button";
    choice.setAttribute("role", "radio");
    choice.setAttribute("aria-checked", String(on));
    choice.tabIndex = on ? 0 : -1;
    choice.dataset.q = String(q);
    choice.dataset.o = String(o);
    choice.disabled = Boolean(say.busy);
    choice.addEventListener("click", () => answer(q, o));
    group.append(choice);
  });
  radioKeys(group);
  return group;
}

function clauseNote(say, index, item) {
  // The note beside a clause: what it was read as, or what the chosen answer makes it.
  const question = say.questions.find((other) => other.kind !== "offer" && other.clause_index === index);
  const answerIndex = question ? say.answers[say.questions.indexOf(question)] || 0 : 0;
  const note = answerIndex && question.options[answerIndex].note ? question.options[answerIndex].note
    : say.clauses[index].note || "";
  if (!say.on[index] && (Object.keys(item.profile_fields).length || item.cares.length)) return keepUnits(`Left out: ${note}`);
  return keepUnits(note);
}

function renderSay() {
  // The student's own words, each clause underlined, with what was read written beside it.
  const box = $("sayResult");
  box.replaceChildren();
  const say = state.say;
  if (!say) {
    box.hidden = true;
    return;
  }
  box.append(el("p", "readback-head", "Read as"));
  if (say.mode?.simplified) {
    box.append(el("p", "readback-note", "The sentence reader is offline, so a simpler one was used. Check each line below."));
  }
  const items = sayItems(say);
  const list = el("ol", `clauses${say.animate ? "" : " drawn still"}`);
  say.clauses.forEach((clause, index) => {
    const item = items[index];
    const usable = Boolean(Object.keys(item.profile_fields).length || item.cares.length);
    const used = usable && say.on[index];
    const row = el("li", "clause");
    const said = el("p", "said");
    const mark = el("span", `mark${usable ? "" : " unread"}${usable && !used ? " left-out" : ""}`, clause.text);
    mark.style.setProperty("--i", String(index));
    said.append(mark);
    const note = el("div", "note");
    note.id = `clause-note-${index}`;
    said.setAttribute("aria-describedby", note.id);
    note.append(el("p", `note-text${used ? "" : " quiet"}`, clauseNote(say, index, item)));
    say.questions.forEach((question, q) => {
      if (question.kind === "offer" || question.clause_index !== index) return;
      const ask = el("div", "ask");
      const text = el("span", "ask-text", question.text);
      text.id = `ask-${q}`;
      ask.append(text, renderOptions(say, question, q, text.id));
      note.append(ask);
    });
    if (usable) {
      const toggle = button(say.on[index] ? "Leave this out" : "Use this again", () => {
        say.on[index] = !say.on[index];
        say.focus = `[data-toggle="${index}"]`;
        applySay();
        renderSay();
      }, { className: "button quiet toggle" });
      toggle.dataset.toggle = String(index);
      note.append(toggle);
    }
    row.append(said, note);
    list.append(row);
  });
  box.append(list);
  const offers = say.questions.map((question, q) => [question, q]).filter(([question]) => question.kind === "offer");
  if (offers.length) {
    const wrap = el("div", "offers");
    offers.forEach(([question, q]) => {
      const row = el("div", "offer");
      const text = el("p", "offer-text", question.text);
      text.id = `ask-${q}`;
      row.append(text, renderOptions(say, question, q, text.id));
      wrap.append(row);
    });
    box.append(wrap);
  }
  const used = items.filter((item) => item.on && (Object.keys(item.profile_fields).length || item.cares.length));
  box.append(el("p", "readback-foot", used.length
    ? "These are filled in below, and the priorities on the results page. Change anything that is wrong, then find timetables."
    : "Nothing in this sentence can be set for you. Use the settings below."));
  box.hidden = false;
  if (say.focus && !say.busy) {
    // Keep keyboard focus on the answer just chosen (the whole read-back was drawn again).
    box.querySelector(say.focus)?.focus();
    say.focus = null;
  }
  if (say.animate) {
    // The one animation on the site: the underlines are drawn once, when the sentence is read.
    say.animate = false;
    requestAnimationFrame(() => requestAnimationFrame(() => list.classList.add("drawn")));
  }
}

async function readSay() {
  const text = $("sayText").value.trim();
  setError("sayError", "");
  if (!text) {
    setError("sayError", "Write a sentence first, or leave it empty and use the settings below.");
    return false;
  }
  const button = $("sayRead");
  button.disabled = true;
  try {
    const data = await post("/api/parse", { text });
    if (!data.clauses) throw new Error(data.error || "The sentence could not be read. Set the conditions below by hand.");
    unapplySay();
    const clauses = data.clauses;
    state.say = {
      text, clauses, mode: data.mode, questions: data.questions || [], animate: true, focus: null,
      answers: {}, overrides: {}, busy: false, firstLabels: clauses.map((clause) => clause.label),
      on: clauses.map((clause) => Boolean(Object.keys(clause.profile_fields).length || clause.cares.length)),
      base: { settings: settingsSnapshot(), cares: [...state.cares], caresTouched: state.caresTouched },
    };
    applySay();
    renderSay();
    const asked = state.say.questions.length;
    announce(`Read ${plural(clauses.length, "part")} of your sentence${asked ? `, with ${plural(asked, "question")} to answer` : ""}.`);
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
    setError("unitError", "Add at least one unit.");
    collapseSetup(false);
    $("unitQuery").focus();
    return null;
  }
  const fail = (message, field) => {
    collapseSetup(false);
    $("moreSettings").open = true;
    setError("settingsError", message);
    $(field)?.focus();
    return null;
  };
  const start = minutes($("preferredStart").value);
  const end = minutes($("preferredEnd").value);
  if (start === null || end === null || start >= end) return fail("The preferred end time must be after the start time.", "preferredEnd");
  const settings = readSettings();
  if (settings.lunch) {
    const { start_min: from, end_min: to, minutes: length } = settings.lunch;
    if (from === null || to === null || from >= to || length > to - from) {
      return fail("The lunch break must fit between its earliest and latest times.", "lunchStart");
    }
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
  if (!response.ok && !data.status && response.status !== 422) throw new Error(data.error || "The request failed. Try again.");
  return data;
}

function defaultGroups(data) {
  return Object.fromEntries((data.units || []).map((unit) => [unit.unit_code,
    unit.groups.filter((group) => group.default_selected).map((group) => group.group_id)]));
}

function snapshot() {
  // Everything a re-plan may change, so "Undo" can put it back.
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
        showEmpty("No timetables yet", first.blockers?.[0]?.message || "There is no timetable data for these units.", []);
        return;
      }
      data = first.module_two_result;
      groups = defaultGroups(data);
      state.history = [];
    }
    const body = { profile, save: $("consent").checked, required_groups: groups, student_text: sayText(),
      cares: state.caresTouched ? [...state.cares] : [] };
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
    // Plans open on the recommended timetables; a re-plan keeps the list the student picked.
    const recommended = Boolean(result.ranking_result?.recommendation);
    if (!notice) state.viewPicked = false;
    if (!recommended) state.view = "all";
    else if (!state.viewPicked) state.view = state.sharedPlan ? "all" : "recommend";
    if (enrolled) state.enrolled = enrolled;
    else if (!notice) {
      state.enrolled = {};
      state.tab = "week";
    }
    writeShareHash();
    if (result.status === "invalid") showInvalid(result);
    else showResult(result);
  } catch (error) {
    showEmpty("The planner is not answering", `${error.message} Reload the page and try again.`, []);
  } finally {
    state.busy = false;
    submit.disabled = false;
    announce($("result").hidden ? "" : $("result").querySelector("h2")?.textContent);
    focusResult();
  }
}

function focusResult() {
  // The button that started the plan is often hidden or redrawn by now; carry keyboard focus
  // to the result heading instead of dropping it at the top of the page.
  const active = document.activeElement;
  if (active && active !== document.body && active.isConnected && active.offsetParent !== null) return;
  const heading = $("result").hidden ? null : $("result").querySelector("h2");
  if (!heading) return;
  heading.tabIndex = -1;
  heading.focus();
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
    notice: "Undid the last change", enrolled: previous.enrolled });
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
    const swatch = el("i", "swatch");
    paint(swatch, unit.code);
    chip.append(swatch, document.createTextNode(unit.code));
    chips.append(chip);
  });
  const said = sayText();
  if (said) chips.append(el("span", "", `“${said.length > 32 ? `${said.slice(0, 32)}…` : said}”`));
  state.blocks.forEach((block) => chips.append(el("span", "", `Not ${block.label}`)));
  const count = settingsCount();
  if (count) chips.append(el("span", "", plural(count, "setting")));
}

/* ===================== result states ===================== */

function resultBox() {
  const box = $("result");
  box.hidden = false;
  box.replaceChildren();
  return box;
}

function showLoading() {
  resultBox().append(el("p", "loading", "Checking every combination of classes…"));
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
    card.append(el("h3", "section-title", "Try one change"));
    const list = el("div", "fixes");
    fixes.forEach((fix) => list.append(fix));
    card.append(list);
  }
  if (state.history.length) card.append(button("Undo the last change", undo));
  resultBox().append(card);
}

function dataBadge(data) {
  const age = data?.snapshot_age_days;
  const time = data?.snapshot_time || "";
  const badge = el("span", `badge${age >= 1 ? " stale" : ""}`,
    time ? `Timetable data from ${dateText(time.slice(0, 10))}${age >= 1 ? ` (${plural(age, "day")} old)` : ""}`
      : "Local timetable data");
  if (age >= 1) badge.title = "Live data could not be fetched, so seats and times may have changed.";
  return badge;
}

function changeLabel(change) {
  if (change.kind === "group") return `Skip ${groupName(change.group_id)} (watch the recording)`;
  if (change.kind === "pin") return `Unpin ${groupName(change.group_id)}`;
  if (change.kind === "buffer") return "No time set aside to change buildings";
  if (change.kind !== "window") return change.label;
  return `Allow classes on ${windowsLabel([change.window])}`;
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
  replan(`Changed: ${changeLabel(change)}`, { groups, pinned, undoTo });
}

function hintLine(text, change, actionLabel = "Apply") {
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
      ? `${joinWords(core.group_ids.map((id) => `${groupName(id)} (${core.slots[id].join(", ")})`))} ${{
        time_overlap: "meet at the same times", limits: "don't fit within your daily or weekly limits",
        filters: "have no classes that meet your class settings" }[core.reason] || "leave too little time to change buildings"}.`
      : emptiedGroups().length
        ? `Every class of ${joinWords(emptiedGroups().map(groupName))} is marked as full.`
        : "No combination of the chosen activities avoids a clash.";
    // When a one-step loosening works as well as dropping the limit, only offer the smaller change.
    const changes = ranking.what_if?.changes || [];
    const fixes = changes.filter((change) => !(change.value == null && changes.some((other) =>
      other.kind === change.kind && other.value != null && other.count === change.count))).map((change) =>
      hintLine(`${changeLabel(change)}: ${plural(change.count, "timetable").replace(/^\d+/, change.count.toLocaleString("en-AU"))} would fit`, change));
    showEmpty("No timetable fits all of these", reason, fixes);
    $("result").append(renderAdjust(true));
    return;
  }
  if (!ranking?.feasible_count) {
    showEmpty("No timetables yet", (result.blockers || [])[0]?.message || "Change the units and try again.", []);
    if (state.data) $("result").append(renderAdjust(true));
    return;
  }
  renderPlans();
}

/* ===================== plans ===================== */

function courseIndex(code) {
  const index = state.units.findIndex((unit) => unit.code === code);
  return (index < 0 ? 0 : index) % COURSE_COLOURS;
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
  // The recommended picks for the features currently chosen under "What matters".
  const rec = state.result?.ranking_result?.recommendation;
  if (!rec) return null;
  const axes = ["gap", "campus_days", "outside_hours"].filter((axis) => state.cares.has(axis)).join(",");
  const menu = rec.menus[axes];
  return menu ? { axes, menu, token: rec.explain_token, key: `${rec.explain_token}|${axes}` } : null;
}

function reasonOf(index) {
  const rec = recommendation();
  const written = state.reasons[rec.key];
  return keepUnits(written?.reasons?.[index] || rec.menu.reasons[index]);
}

function reasonSource() {
  // Said only when a model really reworded the reasons (UNIPLAN_EXPLAIN_MODEL on the server);
  // by default the reasons are the templates and nothing is added.
  const written = state.reasons[recommendation().key];
  const status = written?.status;
  if (status !== "model" && status !== "partial") return "";
  return `Reworded by ${written.model}. Every sentence was checked against its timetable${
    status === "partial" ? "; sentences that failed the check keep their original wording" : ""}.`;
}

function updateReasons() {
  // In place, so a late answer does not reset what the student is doing on the page.
  if (state.view !== "recommend" || !recommendation()) return;
  document.querySelectorAll("[data-reason]").forEach((node) => { node.textContent = reasonOf(Number(node.dataset.reason)); });
  const source = document.querySelector(".reason-source");
  if (source) {
    source.textContent = reasonSource();
    source.hidden = !source.textContent;
  }
}

async function loadReasons() {
  const rec = recommendation();
  if (state.view !== "recommend" || !rec?.token || state.reasons[rec.key]) return;
  state.reasons[rec.key] = { status: "pending" };
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
  const focusKey = document.activeElement?.closest?.("#result [data-key]")?.dataset.key;
  const box = resultBox();
  const ranking = state.result.ranking_result;
  const rec = state.view === "recommend" ? recommendation() : null;
  if (state.view === "recommend" && !rec) state.view = "all";
  if (rec && state.caresTouched && rec.menu.cares && rec.menu.cares.join() !== [...state.cares].join() && !state.busy) {
    // The picks were ranked for another order of importance (e.g. a care ticked off and on again).
    replan("Ranked again in the new order of what matters");
    return;
  }
  const plans = rec ? rec.menu.picks.map((id) => ranking.shortlist.items[id]).filter(Boolean) : menu();
  pickSharedPlan(plans);
  if (!state.selected || !plans.some((item) => item.candidate_id === state.selected)) {
    state.selected = plans[0]?.candidate_id || null;
  }
  state.compare = state.compare.filter((id) => plans.some((item) => item.candidate_id === id));

  const head = el("div", "result-head");
  const fit = ranking.feasible_count.toLocaleString("en-AU");
  if (rec) {
    head.append(el("h2", "", `${plural(plans.length, "timetable")}, from ${fit} that fit`));
  } else {
    head.append(el("h2", "", plans.length === 1 ? `The best timetable, from ${fit} that fit` : `${plural(plans.length, "option")}, from ${fit} that fit`));
  }
  const meta = el("div", "result-meta");
  if (rec) meta.append(el("span", "", `${plural(rec.menu.candidates.length, "candidate")} ranked for what matters to you`));
  meta.append(dataBadge(state.data));
  if (ranking.recommendation) {
    const views = el("div", "segmented views");
    views.setAttribute("role", "radiogroup");
    views.setAttribute("aria-label", "Which timetables to show");
    [["recommend", "Picked for you"], ["all", `All options (${menu().length})`]].forEach(([key, text]) => {
      const choice = el("button", "", text);
      choice.type = "button";
      choice.dataset.key = `view-${key}`;
      choice.setAttribute("role", "radio");
      choice.setAttribute("aria-checked", String(state.view === key));
      choice.tabIndex = state.view === key ? 0 : -1;
      choice.addEventListener("click", () => {
        if (state.view === key) return;
        state.view = key;
        state.viewPicked = true;
        state.selected = null;
        state.compare = [];
        renderPlans();
      });
      views.append(choice);
    });
    radioKeys(views);
    meta.append(views);
  }
  // Otherwise the undo button sits in the notice inside the plan detail.
  if (state.history.length && state.compare.length === 2) meta.append(button("Undo", undo));
  head.append(meta);
  box.append(head);

  const cares = el("div", "cares");
  const caresLabel = el("span", "cares-label", "What matters");
  caresLabel.id = "caresLabel";
  const toggles = el("div", "segmented");
  toggles.setAttribute("role", "group");
  toggles.setAttribute("aria-labelledby", "caresLabel");
  cares.append(caresLabel, toggles);
  AXES.forEach((axis) => {
    const chip = el("button", "", AXIS_CHIP[axis]);
    chip.type = "button";
    chip.dataset.key = `care-${axis}`;
    chip.setAttribute("aria-pressed", String(state.cares.has(axis)));
    chip.addEventListener("click", () => {
      if (state.cares.has(axis) && state.cares.size === 1) {
        toast("Keep at least one.");
        return;
      }
      // A Set keeps its order: the rest stay as they were and a newly ticked one goes last.
      if (state.cares.has(axis)) state.cares.delete(axis); else state.cares.add(axis);
      state.caresTouched = true;
      writeShareHash();
      renderPlans();
    });
    toggles.append(chip);
  });
  if (plans.length > 1) cares.append(el("span", "cares-hint", "Use Compare on two options to see them side by side."));
  box.append(cares);

  const workspace = el("div", "workspace");
  const list = el("div", "plan-list");
  plans.forEach((item, index) => list.append(planCard(item, index, plans)));
  if (rec?.token) {
    const source = el("p", "reason-source", reasonSource());
    source.hidden = !source.textContent;
    list.append(source);
  }
  const side = el("div", "side");
  if (state.compare.length === 2) {
    const [a, b] = state.compare.map((id) => plans.find((item) => item.candidate_id === id));
    side.append(renderCompare(a, b, plans));
  } else {
    if (state.compare.length === 1) {
      const bar = el("div", "compare-bar");
      bar.append(document.createTextNode(`Option ${planLabel(plans.findIndex((item) => item.candidate_id === state.compare[0]))} chosen. Pick one more to compare.`),
        button("Cancel", () => { state.compare = []; renderPlans(); }, { className: "button quiet" }));
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
  if (focusKey) box.querySelector(`[data-key="${focusKey}"]`)?.focus();
  if (rec) loadReasons();
}

function planCard(base, index, plans) {
  const item = shownItem(base);
  const selected = base.candidate_id === state.selected && state.compare.length < 2;
  const compared = state.compare.includes(base.candidate_id);
  // The days are the button that shows this timetable; a click anywhere else on it does the same.
  const card = el("div", `plan${selected ? " selected" : ""}${compared ? " compared" : ""}`);
  card.addEventListener("click", (event) => {
    if (event.target.closest(".variants, .compare-toggle")) return;
    state.selected = base.candidate_id;
    if (state.compare.length === 2) state.compare = [];
    renderPlans();
  });

  const head = el("div", "plan-head");
  head.append(el("span", `rank${state.view === "recommend" && index === 0 ? " first" : ""}`, planLabel(index)));
  const title = el("div");
  const show = el("button", "plan-title", daysText(item.pattern));
  show.type = "button";
  show.dataset.key = `plan-${base.candidate_id}`;
  show.setAttribute("aria-pressed", String(selected));
  show.setAttribute("aria-label", `${state.view === "recommend" ? "Pick" : "Option"} ${planLabel(index)}: ${daysText(item.pattern)}`);
  title.append(show, el("div", "plan-sub", base.equivalent_count > 1
    ? `${base.equivalent_count.toLocaleString("en-AU")} ways to get this same week` : "The only way to get this week"));
  head.append(title);
  card.append(head);
  const best = [];
  if (plans.length > 1) {
    AXES.filter((axis) => state.cares.has(axis)).forEach((axis) => {
      const key = AXIS_FEATURE[axis];
      const values = plans.map((other) => other.features[key]);
      const lowest = Math.min(...values);
      if (Math.max(...values) - lowest > 1e-6 && Math.abs(base.features[key] - lowest) < 1e-6) best.push(AXIS_TAG[axis]);
    });
  }
  if (best.length) card.append(el("p", "tags", capital(`${joinWords(best)} of these`)));
  if (state.view === "recommend") {
    const reason = el("p", "reason", reasonOf(index));
    reason.dataset.reason = String(index);
    card.append(reason);
  }

  if (plans.length > 1) {
    const toggle = el("button", "compare-toggle", compared ? "Comparing" : "Compare");
    toggle.type = "button";
    toggle.dataset.key = `compare-${base.candidate_id}`;
    toggle.setAttribute("aria-label", `Compare option ${planLabel(index)}`);
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
    const label = el("span", "variants-label", "Just as good on");
    label.id = `variants-${base.candidate_id}`;
    const group = el("div", "segmented");
    group.setAttribute("role", "radiogroup");
    group.setAttribute("aria-labelledby", label.id);
    variants.forEach((variant) => {
      const active = (state.variant[base.candidate_id] || base.candidate_id) === variant.candidate_id;
      const chip = el("button", "", daysText(variant.pattern));
      chip.type = "button";
      chip.dataset.key = `variant-${variant.candidate_id}`;
      chip.setAttribute("role", "radio");
      chip.setAttribute("aria-checked", String(active));
      chip.tabIndex = active ? 0 : -1;
      chip.addEventListener("click", () => {
        if (active) return;
        state.variant[base.candidate_id] = variant.candidate_id;
        state.selected = base.candidate_id;
        renderPlans();
      });
      group.append(chip);
    });
    radioKeys(group);
    row.append(label, group);
    card.append(row);
  }
  return card;
}

function daysAmount(value) {
  const text = value.toFixed(1).replace(/\.0$/, "");
  return `${text} day${text === "1" ? "" : "s"}`;
}

function stats(features, compareTo = null) {
  // Three lines, as the reasons word them; the ones the student does not care about are dimmed.
  const box = el("ul", "stats");
  const values = [
    ["campus_days", daysAmount(features.campus_days), "on campus a week", "campus_days"],
    ["gap", durationText(features.gap_min), "waiting a week", "gap_min"],
    ["outside_hours", durationText(features.outside_min), "early or late class a week", "outside_min"],
  ];
  values.forEach(([axis, value, label, key]) => {
    const line = el("li", state.cares.has(axis) ? "" : "dim");
    line.append(el("strong", "", value), document.createTextNode(` ${label}`));
    if (compareTo) {
      const diff = features[key] - compareTo.features[key];
      if (Math.abs(diff) > (key === "campus_days" ? 0.05 : 1)) {
        const amount = key === "campus_days" ? Math.abs(diff).toFixed(1).replace(/\.0$/, "") : durationText(Math.abs(diff));
        line.append(document.createTextNode(" "), el("span", `delta ${diff < 0 ? "better" : "worse"}`, `${diff > 0 ? "+" : "−"}${amount}`));
      }
    }
    box.append(line);
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
      head.title = `Show the route for ${DAY_LONG[day - 1]}`;
      head.setAttribute("aria-pressed", String(activeDay === day));
      head.addEventListener("click", () => onDay(day));
    }
    head.append(el("b", "", DAY[day - 1]));
    if (dates) head.append(document.createTextNode(index === todayIndex ? "Today" : dates[index]));
    grid.append(head);
  });
  if (!thumb) {
    const hours = el("div", "hours");
    hours.style.height = `${height}px`;
    for (let hour = from; hour <= to; hour += 60) {
      const label = el("span", "", timeText(hour));
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
      paint(block, meeting.unit_code);
      block.style.top = `${((meeting.start_min - from) / 60) * hourHeight}px`;
      block.style.height = `${Math.max(((meeting.end_min - meeting.start_min) / 60) * hourHeight - 2, 3)}px`;
      if (layout && layout.get(meeting).lanes > 1) {
        const { lane, lanes: count } = layout.get(meeting);
        block.style.left = `calc(${(lane / count) * 100}% + 2px)`;
        block.style.right = "auto";
        block.style.width = `calc(${100 / count}% - 4px)`;
      }
      const activity = activityOf(meeting);
      const room = meeting.is_online ? "Online" : meeting.building_code || "";
      block.title = `${meeting.unit_code} ${activity} ${meeting.class_code || ""}, ${spanText(meeting.start_min, meeting.end_min)}, ${meeting.is_online ? "online" : meeting.location_raw || room}`;
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

const TABS = [["week", "Week"], ["term", "Semester"], ["time", "Hours"], ["enrol", "Enrolment"], ["friend", "With a friend"]];

function renderDetail(base, plans) {
  const item = shownItem(base);
  const index = plans.findIndex((other) => other.candidate_id === base.candidate_id);
  const letter = planLabel(index);
  const detail = el("section", "detail");

  const head = el("div", "detail-head");
  const title = el("h3");
  title.append(el("span", `rank${state.view === "recommend" && index === 0 ? " first" : ""}`, letter),
    document.createTextNode(daysText(item.pattern)));
  head.append(title);
  detail.append(head);
  const tools = el("div", "detail-actions");
  tools.append(
    button("Use this timetable", (node) => acceptPlan(item, index, plans, node), { className: "button primary" }),
    button("Download calendar (.ics)", () => { downloadIcs(item); toast("Calendar file downloaded. Import it into Google, Apple or Outlook calendar."); }),
    button("Share link", () => copyText(shareUrl(item), "Link copied. Anyone who opens it sees this timetable.")),
    button("Save", () => { saveFavourite(item, letter); toast("Saved on this device. It is listed on the first page."); }),
    button("Print", () => window.print()),
  );
  detail.append(tools);
  if (state.notice) {
    const notice = el("div", "notice", state.notice);
    if (state.history.length) notice.append(button("Undo", undo, { className: "button quiet" }));
    detail.append(notice);
  }
  const next = nextClass(item);
  if (next) detail.append(next);

  const bar = el("div", "tabs");
  bar.setAttribute("role", "tablist");
  bar.setAttribute("aria-label", "Views of this timetable");
  const panel = el("div", "tab-panel");
  panel.id = "tab-panel";
  panel.setAttribute("role", "tabpanel");
  TABS.forEach(([key, label]) => {
    const tab = el("button", "tab", label);
    tab.type = "button";
    tab.id = `tab-${key}`;
    tab.dataset.tab = key;
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-controls", panel.id);
    tab.setAttribute("aria-selected", String(state.tab === key));
    tab.tabIndex = state.tab === key ? 0 : -1;
    tab.addEventListener("click", () => {
      state.tab = key;
      bar.querySelectorAll(".tab").forEach((other) => {
        other.setAttribute("aria-selected", String(other === tab));
        other.tabIndex = other === tab ? 0 : -1;
      });
      panel.setAttribute("aria-labelledby", tab.id);
      panel.replaceChildren(TAB_VIEWS[key](item, base));
    });
    bar.append(tab);
  });
  bar.addEventListener("keydown", (event) => {
    // Arrow keys move between tabs (the ARIA tabs pattern); Tab moves into the panel.
    const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
    if (!step) return;
    event.preventDefault();
    event.stopPropagation();
    const tabs = [...bar.querySelectorAll(".tab")];
    const next = tabs[(tabs.indexOf(document.activeElement) + step + tabs.length) % tabs.length];
    next.focus();
    next.click();
  });
  panel.setAttribute("aria-labelledby", `tab-${state.tab}`);
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
  const when = days === 0 ? (upcoming.start_min <= NOW_MIN ? "On now" : `Today, ${timeText(upcoming.start_min)}`)
    : days === 1 ? `Tomorrow, ${timeText(upcoming.start_min)}` : `${dayDate(upcoming.date)}, ${timeText(upcoming.start_min)}`;
  const box = el("div", "next-class");
  box.append(el("span", "next-label", days === 0 && upcoming.start_min <= NOW_MIN ? "Now" : "Next class"),
    el("b", "", when), el("span", "", `${upcoming.unit_code} ${activityOf(upcoming)} ${upcoming.class_code || ""}`),
    el("span", "muted", upcoming.is_online ? "Online" : upcoming.location_raw && upcoming.location_raw !== "-" ? upcoming.location_raw : upcoming.building_code || ""));
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
  const prev = button("Previous", () => move(-1), { title: "Previous week" });
  const next = button("Next", () => move(1), { title: "Next week" });
  const label = el("span", "label");
  label.setAttribute("aria-live", "polite");
  const nowPill = el("span", "pill", "this week");
  const thisWeek = currentWeekIndex(weeks);
  const back = button("Back to this week", () => { state.week[base.candidate_id] = thisWeek; draw(); });
  nav.append(label, nowPill, prev, next, back, el("span", "hint", "Select a day to see its route. Left and right arrow keys change the week."));
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
    label.textContent = `Week ${position + 1}, ${rangeText(week, end)}`;
    nowPill.hidden = position !== thisWeek;
    back.hidden = thisWeek < 0 || position === thisWeek;
    prev.disabled = position === 0;
    next.disabled = position === weeks.length - 1;
    const used = new Set(meetings.map((meeting) => meeting.weekday));
    const dayList = [1, 2, 3, 4, 5, ...[6, 7].filter((day) => used.has(day))];
    const todayIndex = dayList.findIndex((day) => addDays(week, day - 1) === TODAY);
    const activeDay = state.routeDay[base.candidate_id] || null;
    holder.replaceChildren(weekGrid(meetings, {
      dates: dayList.map((day) => String(Number(addDays(week, day - 1).slice(8, 10)))), range, todayIndex, activeDay, nowLine: true,
      onDay: (day) => {
        state.routeDay[base.candidate_id] = state.routeDay[base.candidate_id] === day ? null : day;
        draw();
      },
    }));
    if (!meetings.length) holder.append(el("p", "week-empty", "No classes this week"));
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
    const swatch = el("i", "swatch");
    paint(swatch, unit.code);
    key.append(swatch, document.createTextNode(unit.code));
    legend.append(key);
  });
  legend.append(el("span", "", "Striped blocks are online"));
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
  head.append(el("b", "", `Route on ${dayDate(date)}`));
  box.append(head);
  const stops = [];
  meetings.filter((meeting) => !meeting.is_online && meeting.building_code)
    .sort((a, b) => a.start_min - b.start_min)
    .forEach((meeting) => {
      const last = stops[stops.length - 1];
      if (last && last.code === meeting.building_code) {
        last.until = meeting.end_min;
        last.what += `, ${meeting.unit_code} ${activityOf(meeting)}`;
        return;
      }
      stops.push({ code: meeting.building_code, location: meeting.building_location, from: meeting.start_min,
        until: meeting.end_min, what: `${meeting.unit_code} ${activityOf(meeting)}` });
    });
  if (!stops.length) {
    head.append(el("span", "meta", meetings.length ? "Only online classes this day" : "No classes this day"));
    return box;
  }
  const located = stops.filter((stop) => stop.location?.latitude != null);
  let metres = 0;
  for (let index = 1; index < located.length; index += 1) metres += distanceMetres(located[index - 1].location, located[index].location);
  head.append(el("span", "meta", stops.length === 1 ? `All day in ${stops[0].code}` :
    `${stops.length} stops, about ${Math.max(1, Math.round((metres * 1.3) / 80))} min on foot in all (from map distances)`));
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
    const svg = svgEl("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": "Map of the walk between buildings this day" });
    if (xy.length > 1) svg.append(svgEl("polyline", { class: "road", points: xy.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ") }));
    const byCode = new Map();
    located.forEach((stop, index) => {
      if (!byCode.has(stop.code)) byCode.set(stop.code, { at: xy[index], numbers: [] });
      byCode.get(stop.code).numbers.push(stops.indexOf(stop) + 1);
    });
    byCode.forEach(({ at: [x, y], numbers }, code) => {
      const text = numbers.join(",");
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
        `Then ${gap} min free${walk !== null ? `, about ${walk} min to walk there` : ""}`);
      list.append(leg);
    }
    const name = stop.location?.name ? ` ${stop.location.name}` : "";
    li.append(el("b", "", String(index + 1)), el("span", "stop-time", spanText(stop.from, stop.until)),
      el("strong", "", `${stop.code}${name}`), el("span", "muted", stop.what));
    if (stop.location?.map_url) {
      const link = el("a", "map-link", "Map");
      link.setAttribute("aria-label", `Map of ${stop.code}`);
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
  for (let day = 1; day <= 5; day += 1) heat.append(el("span", "heat-head", DAY[day - 1]));
  weeks.forEach((week, position) => {
    if (position && daysBetween(weeks[position - 1], week) > 7) heat.append(el("span", "heat-break", "Mid-semester break"));
    heat.append(el("span", `heat-week${position === now ? " now" : ""}`, `Week ${position + 1}`));
    for (let day = 1; day <= 5; day += 1) {
      const date = addDays(week, day - 1);
      const meetings = item.meetings.filter((meeting) => meeting.date === date);
      const onCampus = meetings.filter((meeting) => !meeting.is_online);
      const hours = onCampus.reduce((sum, meeting) => sum + meeting.end_min - meeting.start_min, 0) / 60;
      const cell = el("span", `heat-cell${onCampus.length ? "" : meetings.length ? " online" : " off"}${date === TODAY ? " now" : ""}${date < TODAY ? " past" : ""}`,
        onCampus.length ? `${Number(hours.toFixed(1))} h` : meetings.length ? "Online" : "");
      if (onCampus.length) cell.style.setProperty("--level", String(Math.min(1, hours / 6)));
      if (meetings.some((meeting) => meeting.is_fixed_assessment)) cell.classList.add("exam");
      cell.title = `${dayDate(date)}: ${meetings.map((meeting) => `${meeting.unit_code} ${activityOf(meeting)} ${timeText(meeting.start_min)}`).join(", ") || "no classes"}`;
      heat.append(cell);
    }
  });
  box.append(heat);
  const key = el("div", "legend");
  key.append(el("span", "", "Hours on campus each day; darker means longer"), el("span", "", "Amber outline: exam or fixed test"),
    el("span", "", "Purple outline: today"));
  box.append(key);
  const routine = new Set(slotsOf(item.meetings).map((slot) => `${slot.weekday}|${slot.start_min}|${slot.group_id}`));
  const oneOff = item.meetings.filter((meeting) => !routine.has(`${meeting.weekday}|${meeting.start_min}|${meeting.group_id}`))
    .sort((a, b) => a.date.localeCompare(b.date) || a.start_min - b.start_min);
  if (oneOff.length) {
    box.append(el("h4", "section-title", "Classes outside the weekly pattern"));
    const list = el("ul", "list");
    oneOff.forEach((meeting) => {
      const li = el("li", `${meeting.is_fixed_assessment ? "exam" : ""}${meeting.date < TODAY ? " past" : ""}`.trim());
      const days = daysBetween(TODAY, meeting.date);
      li.append(el("b", "", dayDate(meeting.date)),
        el("span", "", spanText(meeting.start_min, meeting.end_min)),
        el("span", "", `${meeting.unit_code} ${activityOf(meeting)} ${meeting.class_code || ""}`),
        el("span", "muted", meeting.is_online ? "Online" : meeting.building_code || ""));
      if (days >= 0 && days <= 21) li.append(el("span", "soon", days === 0 ? "Today" : `In ${plural(days, "day")}`));
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
  const rows = [["Class", classMinutes, "c2"], ["Waiting", f.gap_min, "c0"], ["Travel", commute, "c4"]];
  const total = rows.reduce((sum, [, value]) => sum + value, 0);
  const ledger = el("div", "ledger");
  const totalLine = el("div", "ledger-total", hoursText(total));
  totalLine.append(document.createTextNode(" "), el("small", "", `a week on average, about ${Math.round((total * weeks) / 60)} h over the semester`));
  const bar = el("div", "ledger-bar");
  rows.forEach(([label, value, color]) => {
    if (!value) return;
    const part = el("i");
    part.style.setProperty("--w", `${(value / total) * 100}%`);
    part.style.setProperty("--edge", `var(--${color}-edge)`);
    part.title = `${label}: ${hoursText(value)}`;
    bar.append(part);
  });
  const legend = el("div", "ledger-legend");
  rows.forEach(([label, value, color]) => {
    const key = el("span");
    const swatch = el("i", "swatch");
    swatch.style.setProperty("--fill", `var(--${color}-edge)`);
    swatch.style.setProperty("--edge", `var(--${color}-edge)`);
    key.append(swatch, document.createTextNode(`${label}: ${hoursText(value)}`));
    legend.append(key);
  });
  if (!commuteMinutes()) legend.append(el("span", "muted", "Set travel time each way under More settings to count it here."));
  ledger.append(totalLine, bar, legend);
  box.append(ledger);

  const routine = slotsOf(item.meetings);
  const table = el("table", "table");
  const header = el("tr");
  ["", "On campus", "Class", "Waiting"].forEach((text) => header.append(el("th", "", text)));
  table.append(header);
  const free = [];
  for (let day = 1; day <= 5; day += 1) {
    const daily = routine.filter((slot) => slot.weekday === day).sort((a, b) => a.start_min - b.start_min);
    const campus = daily.filter((slot) => !slot.is_online);
    const row = el("tr");
    row.append(el("td", "", DAY[day - 1]));
    if (!daily.length) {
      row.append(el("td", "muted", "No classes"), el("td"), el("td"));
    } else {
      const span = campus.length ? spanText(campus[0].start_min, Math.max(...campus.map((slot) => slot.end_min))) : "Online only";
      const taught = daily.reduce((sum, slot) => sum + slot.end_min - slot.start_min, 0);
      let waiting = 0;
      let latest = daily[0].end_min;
      daily.slice(1).forEach((slot) => {
        waiting += Math.max(0, slot.start_min - latest);
        latest = Math.max(latest, slot.end_min);
      });
      row.append(el("td", "", span), el("td", "", hoursText(taught)), el("td", "", waiting ? hoursText(waiting) : "None"));
    }
    table.append(row);
    let cursor = 9 * 60;
    [...daily, { start_min: 18 * 60, end_min: 18 * 60 }].forEach((slot) => {
      const start = Math.min(slot.start_min, 18 * 60);
      if (start - cursor >= 180) free.push(`${DAY[day - 1]} ${spanText(cursor, start)}`);
      cursor = Math.max(cursor, slot.end_min);
    });
  }
  box.append(el("h4", "section-title", "A usual week"), table);
  box.append(el("h4", "section-title", "Free blocks of 3 hours or more, for work or study"));
  if (free.length) {
    const chips = el("div", "free-blocks");
    free.forEach((text) => chips.append(el("span", "", text)));
    box.append(chips);
  } else {
    box.append(el("p", "muted", "No free block of 3 hours or more between 9 am and 6 pm."));
  }
  return box;
}

function optionOf(item, group) {
  return item.option_ids.find((id) => id.startsWith(`${group}|`));
}

function seatPill(info) {
  const seats = seatNumber(info.seats);
  return el("span", `seat${seats === null ? "" : seats <= 3 ? " low" : " ok"}`, info.seats || "unknown");
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
  progress.append(el("span", "", `${doneCount} of ${order.length} enrolled`), track);
  box.append(progress, el("p", "muted", "Enrol from the top: classes with few seats and no equal backup come first. Mark a class as full to keep what you have and plan the rest again."));
  const table = el("table", "table");
  const head = el("tr");
  ["", "Activity", "Class", "Seats", "Backup if full", ""].forEach((text) => head.append(el("th", "", text)));
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
    if (done) backup.textContent = "Enrolled";
    else if (!info.backups.length) backup.textContent = "No backup without a clash";
    else {
      backup.textContent = info.backups.slice(0, 2).map((entry) => `${entry.code} (${deltaShort(entry.delta)})`).join(", ");
      if (info.alternatives > 2) backup.textContent += `, ${info.alternatives - 2} more`;
    }
    row.append(backup);
    const actions = el("td", "row-actions");
    if (!done) {
      actions.append(
        button("Enrolled", () => { state.enrolled[group] = option; renderPlans(); toast(`${groupName(group)} ${info.code} marked as enrolled.`); },
          { title: `Mark ${groupName(group)} ${info.code} as enrolled` }),
        button("Full", () => markFull(group, option), { title: `Mark ${groupName(group)} ${info.code} as full` }),
      );
    } else if (state.enrolled[group] === option) {
      actions.append(button("Undo", () => { delete state.enrolled[group]; renderPlans(); }, { className: "button quiet" }));
    }
    row.append(actions);
    table.append(row);
  });
  const scroller = el("div", "table-scroll");
  scroller.append(table);
  box.append(scroller);
  const tools = el("div", "tool-row spaced");
  tools.append(button("Copy enrolment list", () => copyText(`UniPlan enrolment list\n${enrolmentText(item)}`, "Enrolment list copied.")));
  if (state.excluded.length) {
    tools.append(button(`Clear full marks (${state.excluded.length})`, () => replan("Full marks cleared", { excluded: [] })));
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
  replan(`${groupName(group)} ${option.split("|").pop()} is full. Your enrolled classes are kept and the rest is planned again.`,
    { pinned, excluded: [...new Set([...state.excluded, option])], undoTo });
}

function friendView(item) {
  const box = el("div");
  box.append(el("p", "muted", "Paste a friend's share link to see which classes you share and when you are both free for lunch, or to move into the same classes."));
  const row = el("div", "friend-row");
  const input = el("input", "input");
  input.type = "url";
  input.placeholder = "Your friend's share link";
  input.setAttribute("aria-label", "Your friend's share link");
  input.value = state.friend?.link || "";
  const result = el("div");
  const compare = () => {
    const shared = parseShare(input.value.split("#")[1] || "");
    if (!shared?.plan) {
      result.replaceChildren(el("p", "field-error", "That link has no timetable in it. Ask your friend to press Share link on a timetable."));
      return;
    }
    state.friend = { link: input.value, plan: shared.plan, slots: shared.slots || null };
    result.replaceChildren(friendCompare(item));
  };
  input.addEventListener("keydown", (event) => { if (event.key === "Enter") compare(); });
  row.append(input, button("Compare", compare, { className: "button primary" }));
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
      if (start - cursor >= 45) out.push(`${DAY[day - 1]} ${spanText(cursor, start)}`);
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
    box.append(el("h4", "section-title", "Both on campus and free, 11 am to 3 pm"));
    if (together.length) {
      const chips = el("div", "free-blocks");
      together.forEach((text) => chips.append(el("span", "", text)));
      box.append(chips);
    } else {
      box.append(el("p", "muted", "No 45 min gap you share between 11 am and 3 pm."));
    }
  }
  if (!shared.length) {
    box.append(el("p", "muted", "You have no activities in common."));
    return box;
  }
  box.append(el("h4", "section-title", `Shared activities: same class in ${shared.filter((group) => mine.get(group) === theirs.get(group)).length} of ${shared.length}`));
  const list = el("ul", "list");
  shared.forEach((group) => {
    const same = mine.get(group) === theirs.get(group);
    const li = el("li", same ? "same" : "");
    li.append(el("b", "", groupName(group)),
      el("span", "", same ? `Same class, ${mine.get(group).split("|").pop()}` : `You ${mine.get(group).split("|").pop()}, your friend ${theirs.get(group).split("|").pop()}`));
    list.append(li);
  });
  box.append(list);
  const different = shared.filter((group) => mine.get(group) !== theirs.get(group));
  if (different.length) {
    const join = button("Move into your friend's classes where possible", () => {
      const undoTo = snapshot();
      const pinned = { ...state.pinned };
      different.forEach((group) => { pinned[group] = [theirs.get(group)]; });
      state.tab = "friend";
      replan("Planned again with your friend's classes. If they don't fit, the page says what to loosen.", { pinned, undoTo });
    }, { className: "button primary" });
    box.append(join);
  }
  return box;
}

const TAB_VIEWS = { week: weekView, term: termView, time: timeView, enrol: enrolView, friend: friendView };

function renderCompare(a, b, plans) {
  const box = el("section", "detail compare");
  const head = el("div", "detail-head");
  const title = el("h3");
  title.append(document.createTextNode(`Options ${planLabel(plans.indexOf(a))} and ${planLabel(plans.indexOf(b))}`));
  head.append(title, el("span", "spacer"),
    button("Stop comparing", () => { state.compare = []; renderPlans(); }, { className: "button quiet" }));
  box.append(head);
  const itemA = shownItem(a);
  const itemB = shownItem(b);
  const range = hourRange([...slotsOf(itemA.meetings), ...slotsOf(itemB.meetings)]);
  const grid = el("div", "compare-grid");
  [[a, b], [b, a]].forEach(([own, other]) => {
    const item = shownItem(own);
    const col = el("div", "compare-col");
    const title = el("div", "plan-head");
    title.append(el("span", "rank", planLabel(plans.indexOf(own))), el("div", "plan-title", daysText(item.pattern)));
    col.append(title, stats(own.features, other), weekGrid(slotsOf(item.meetings), { range, compact: true }));
    col.append(button("See this option", () => { state.selected = own.candidate_id; state.compare = []; renderPlans(); }));
    grid.append(col);
  });
  box.append(grid);
  const byGroup = (item) => new Map(item.option_ids.map((id) => [id.split("|").slice(0, 2).join("|"), id]));
  const groupsA = byGroup(itemA);
  const groupsB = byGroup(itemB);
  const differing = [...groupsA.keys()].filter((group) => groupsA.get(group) !== groupsB.get(group));
  box.append(el("h4", "section-title", differing.length ? `${plural(differing.length, "activity").replace("activitys", "activities")} differ` : "Both options use the same classes"));
  if (differing.length) {
    const slot = (item, group) => {
      const meeting = slotsOf(item.meetings).find((entry) => entry.option_id.startsWith(group)) ||
        item.meetings.find((entry) => entry.option_id.startsWith(group));
      return meeting ? `${DAY[meeting.weekday - 1]} ${timeText(meeting.start_min)}` : "";
    };
    const list = el("ul", "list");
    differing.forEach((group) => {
      const li = el("li");
      li.append(el("b", "", groupName(group)),
        el("span", "", `${planLabel(plans.indexOf(a))}: ${groupsA.get(group).split("|").pop()} ${slot(itemA, group)}`),
        el("span", "", `${planLabel(plans.indexOf(b))}: ${groupsB.get(group).split("|").pop()} ${slot(itemB, group)}`));
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
  if (Math.abs(delta.campus_days) >= 0.05) {
    parts.push(`${Math.abs(delta.campus_days).toFixed(1).replace(/\.0$/, "")} ${delta.campus_days > 0 ? "more" : "fewer"} days on campus`);
  }
  if (Math.abs(delta.gap_min) >= 1) parts.push(`${durationText(Math.abs(delta.gap_min))} ${delta.gap_min > 0 ? "more" : "less"} waiting`);
  if (Math.abs(delta.outside_min) >= 1) {
    parts.push(`${durationText(Math.abs(delta.outside_min))} ${delta.outside_min > 0 ? "more" : "less"} early or late`);
  }
  return parts.length ? parts.join(", ") : "no change";
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
    const backups = info.backups.slice(0, 2).map((backup) => `${backup.code} (${deltaShort(backup.delta)})`).join(", ");
    return `${index + 1}. ${groupName(group)} ${info.code}${info.seats ? `, ${info.seats} seats left` : ""}${backups ? `; if full: ${backups}` : ""}`;
  }).join("\n");
}

async function acceptPlan(item, index, plans, node) {
  node.disabled = true;
  node.textContent = "Chosen";
  state.tab = "enrol";
  toast("Chosen. Enrol in the order shown under Enrolment.");
  const tab = document.querySelector('.tab[data-tab="enrol"]');
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
      ? el("p", "muted hints-ok", "None of your limits makes the best timetable worse, so loosening one would not help.") : null;
  }
  const box = el("div", "hints");
  box.append(el("h3", "section-title", "Loosening one limit would help"));
  useful.forEach((change) => {
    const gains = [];
    if (change.gain.campus_days > 0.05) gains.push(`${change.gain.campus_days.toFixed(1).replace(/\.0$/, "")} fewer days on campus a week`);
    if (change.gain.gap_min > 15) gains.push(`${hoursText(change.gain.gap_min)} less waiting a week`);
    if (change.gain.outside_min > 15) gains.push(`${durationText(change.gain.outside_min)} less early or late class a week`);
    box.append(hintLine(`${changeLabel(change)}: up to ${joinWords(gains)}`, change, "Try it"));
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
          block.style.removeProperty("--fill");
          block.style.removeProperty("--edge");
        } else {
          const hue = seats !== null && seats <= 3 ? "c4" : "c1";
          block.style.setProperty("--fill", `var(--${hue}-fill)`);
          block.style.setProperty("--edge", `var(--${hue}-edge)`);
        }
        if (blocked && !full) block.classList.add("avoid");
        if (pinSelect.value === meeting.option_id) block.classList.add("picked");
        if (current && current === meeting.option_id) block.classList.add("current");
        const note = full ? "Full" : blocked ? "During times you can't make"
          : clash && current !== meeting.option_id ? `Clashes with ${clash.unit_code} ${activityOf(clash)}`
            : meeting.seats ? `${meeting.seats} seats left` : "Seats unknown";
        block.title = `${meeting.class_code}, ${DAY[meeting.weekday - 1]} ${spanText(meeting.start_min, meeting.end_min)}, ${meeting.building_code || "online"}: ${note}`;
        block.setAttribute("aria-label", block.title);
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
    }), el("p", "muted", "Green has seats, red has 3 or fewer, striped is full, faded is during times you can't make, and the dashed outline is the class in this option. Select a class to pin it, then press Plan again."));
  };
  draw();
  return box;
}

function renderAdjust(open) {
  const details = el("details", "adjust");
  details.open = open;
  const summary = el("summary");
  summary.append(el("span", "", "Activities and classes"));
  const pinnedCount = Object.keys(state.pinned).length;
  if (pinnedCount) summary.append(el("span", "count", `${pinnedCount} pinned`));
  details.append(summary);
  const data = state.data;
  if (!data) return details;
  const conflict = new Set(state.result?.ranking_result?.conflict_core?.group_ids || []);
  const current = state.result?.ranking_result?.shortlist && state.selected
    ? shownItem(state.result.ranking_result.shortlist.items[state.selected] || {}) : null;
  const container = el("div", "groups");
  container.append(el("p", "muted", "Untick an activity to leave it out, for example a lecture you watch as a recording. Choose a class to pin it."));
  (data.units || []).forEach((unit) => {
    const fieldset = el("fieldset", "unit-groups");
    const legend = el("legend");
    const swatch = el("i", "swatch");
    paint(swatch, unit.unit_code);
    legend.append(swatch, document.createTextNode(unit.unit_code));
    fieldset.append(legend);
    unit.groups.forEach((group) => {
      const row = el("div", `group-row${conflict.has(group.group_id) ? " conflict" : ""}`);
      const label = el("label");
      const checkbox = el("input");
      checkbox.type = "checkbox";
      checkbox.value = group.group_id;
      checkbox.dataset.unit = unit.unit_code;
      checkbox.checked = (state.groups?.[unit.unit_code] || []).includes(group.group_id);
      label.append(checkbox, document.createTextNode(`${group.group_id.split("|").pop()}${conflict.has(group.group_id) ? " (clash)" : ""}`));
      row.append(label);
      if (!group.default_selected && group.default_reason) row.append(el("span", "muted", group.default_reason));
      fieldset.append(row);
      if ((group.options || []).length > 1) {
        const pin = el("select", "select");
        pin.dataset.group = group.group_id;
        pin.setAttribute("aria-label", `${unit.unit_code} ${group.group_id.split("|").pop()} class`);
        const any = el("option", "", `Any class (${group.options.length})`);
        any.value = "";
        pin.append(any);
        group.options.forEach((option) => {
          const seats = option.status === "full" ? ", full" : option.available_seats ? `, ${option.available_seats} seats left` : "";
          const start = minutes(option.start_time);
          const choice = el("option", "", `${option.class_code}, ${DAY[option.weekday - 1]} ${start === null ? option.start_time : timeText(start)}${seats}`);
          choice.value = option.option_id;
          pin.append(choice);
        });
        pin.value = (state.pinned[group.group_id] || [""])[0];
        pin.addEventListener("change", () => { if (pin.value) checkbox.checked = true; });
        const explorerHolder = el("div");
        const browse = button("See all classes", (node) => {
          const open = !explorerHolder.childElementCount;
          explorerHolder.replaceChildren(...(open ? [renderExplorer(unit, group, pin, current)] : []));
          node.setAttribute("aria-expanded", String(open));
          node.textContent = open ? "Hide classes" : "See all classes";
        });
        browse.setAttribute("aria-expanded", "false");
        row.append(pin, browse);
        fieldset.append(explorerHolder);
      }
    });
    container.append(fieldset);
  });
  const actions = el("div", "groups-actions");
  const error = el("p", "field-error");
  actions.append(button("Plan again", () => {
    const groups = {};
    container.querySelectorAll("input[type=checkbox]").forEach((input) => {
      groups[input.dataset.unit] = groups[input.dataset.unit] || [];
      if (input.checked) groups[input.dataset.unit].push(input.value);
    });
    const empty = Object.entries(groups).find(([, ids]) => !ids.length);
    if (empty) {
      error.textContent = `Keep at least one activity for ${empty[0]}.`;
      return;
    }
    const chosen = Object.values(groups).flat();
    const pinned = {};
    container.querySelectorAll("select[data-group]").forEach((pin) => {
      if (pin.value && chosen.includes(pin.dataset.group)) pinned[pin.dataset.group] = [pin.value];
    });
    replan("Planned again with your changes", { groups, pinned });
  }, { className: "button primary" }), button("Watch every lecture as a recording", () => {
    container.querySelectorAll("input[type=checkbox]").forEach((input) => {
      if (/lecture/i.test(input.value.split("|").pop())) input.checked = false;
    });
    toast("Every lecture is unticked. Press Plan again.");
  }), button("Clear pins", () => {
    container.querySelectorAll("select[data-group]").forEach((pin) => { pin.value = ""; });
    toast("All pins cleared. Press Plan again.");
  }, { className: "button quiet" }));
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
  const lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//UniPlan//Timetable//EN",
    "CALSCALE:GREGORIAN", "X-WR-CALNAME:UniPlan timetable", ...SYDNEY_VTIMEZONE];
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
        ? `, about ${Math.max(1, Math.round((distanceMetres(a, b) * 1.3) / 80))} min on foot` : "";
      seen.set(key, `Tight change on ${DAY[next.weekday - 1]} at ${timeText(prev.end_min)}: ${prev.building_code} to ${next.building_code} in ${gap} min${walk}`);
    });
  });
  return [...seen.values()];
}

/* ===================== preference study (?study=1, for the pilot) ===================== */

function renderStudy(study) {
  const box = el("section", "study");
  box.append(el("h3", "", "Preference comparison"));
  if (!study.available) {
    box.append(el("p", "muted", study.reason));
    return box;
  }
  box.append(button(`Start (${study.pairs.length} pairs)`, () => runStudy(study, box)));
  return box;
}

function studyCard(card, letter) {
  const box = el("div", "plan");
  const head = el("div", "plan-head");
  head.append(el("span", "rank", letter));
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
  box.replaceChildren(el("h3", "", "Preference comparison"), stage);
  const choose = (choice) => {
    answers.set(study.pairs[index].pair_id, choice);
    index += 1;
    if (index < study.pairs.length) draw(); else submit();
  };
  function draw() {
    const pair = study.pairs[index];
    stage.replaceChildren(el("p", "muted", `${index + 1} of ${study.pairs.length}: which would you rather have?`));
    const grid = el("div", "pair");
    grid.append(studyCard(study.schedules[pair.left], "A"), studyCard(study.schedules[pair.right], "B"));
    const row = el("div", "choice-row");
    row.append(button("A", () => choose("left"), { className: "button primary" }),
      button("About the same", () => choose("tie")), button("B", () => choose("right"), { className: "button primary" }));
    stage.append(grid, row);
  }
  async function submit() {
    stage.replaceChildren(el("p", "muted", "Working it out…"));
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
      const percent = (value) => (value == null ? "not available" : `${Math.round(value * 100)}%`);
      stage.append(el("p", "muted", "What your choices show"), bars,
        el("p", "muted", `Held-out check: learned ${percent(result.learned?.accuracy)}, equal weights ${percent(result.equal_weight?.accuracy)}, chance 50%`));
    } catch (error) {
      stage.replaceChildren(el("p", "", `This could not finish: ${error.message}`));
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
  state.caresTouched = Array.isArray(shared.cares) && shared.cares.length > 0;
  state.sharedPlan = Array.isArray(shared.plan) ? shared.plan : null;
  state.say = null;
  $("sayText").value = "";
  renderSay();
  document.querySelectorAll(".setting.from-sentence").forEach((row) => row.classList.remove("from-sentence"));
}

async function copyText(text, done) {
  try {
    await navigator.clipboard.writeText(text);
    toast(done);
  } catch {
    window.prompt("Copy this text", text);
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
  const title = `${state.units.map((unit) => unit.code).join(", ")}: ${state.view === "recommend" ? "pick" : "option"} ${letter}, ${daysText(item.pattern)}`;
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
  box.append(el("span", "field-label", "Saved timetables"));
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
    remove.setAttribute("aria-label", `Remove ${entry.title}`);
    remove.addEventListener("click", () => storeFavourites(loadFavourites().filter((_, position) => position !== index)));
    row.append(link, el("span", "muted", /^\d{4}-\d{2}-\d{2}$/.test(entry.at || "") ? dateText(entry.at) : entry.at || ""), remove);
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
    message.textContent = "Enter the full 32-character participant code.";
    return;
  }
  if (state.confirmWithdraw !== code) {
    state.confirmWithdraw = code;
    message.textContent = "This deletes the saved answers for good. Press Delete saved answers again to confirm.";
    return;
  }
  state.confirmWithdraw = null;
  try {
    const response = await fetch(`/api/profiles/${code}`, { method: "DELETE" });
    const data = await response.json();
    message.textContent = data.removed ? "Deleted." : "No saved answers match that code.";
  } catch {
    message.textContent = "The server is not answering. Try again later.";
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
      group.closest(".setting")?.classList.remove("from-sentence");
      updateSettingsCount();
    });
    radioKeys(group);
  });

  try {
    const response = await fetch("/api/catalog");
    const data = await response.json();
    const seen = new Set();
    (data.snapshots || []).forEach((snap) => {
      const value = `${snap.year}|${snap.session_code}`;
      if (seen.has(value)) return;
      seen.add(value);
      const option = el("option", "", termName(snap.year, snap.session_code));
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
  $("customToggle").addEventListener("click", () => {
    $("customBlock").hidden = !$("customBlock").hidden;
    $("customToggle").setAttribute("aria-expanded", String(!$("customBlock").hidden));
    if (!$("customBlock").hidden) $("customDay").focus();
  });
  $("customAdd").addEventListener("click", addCustomBlock);
  [...SETTING_FIELDS, ...SETTING_CHECKS].forEach((id) => $(id).addEventListener("change", () => {
    $(id).closest(".setting")?.classList.remove("from-sentence");
    updateSettingsCount();
  }));
  updateSettingsCount();
  renderFavourites();
  $("profileForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = $("sayText").value.trim();
    if (text && text !== state.say?.text) {
      // Show what was understood first; the student confirms by pressing the button again.
      if (await readSay()) toast("The sentence is read and filled in. Check it, then press Find timetables.");
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
    $("profileForm").scrollIntoView({ block: "start" });
    $("unitQuery").focus({ preventScroll: true });
  });
  $("withdrawToggle").addEventListener("click", () => {
    $("withdrawForm").hidden = !$("withdrawForm").hidden;
    $("withdrawToggle").setAttribute("aria-expanded", String(!$("withdrawForm").hidden));
    if (!$("withdrawForm").hidden) $("withdrawCode").focus();
  });
  $("withdrawForm").addEventListener("submit", withdrawSaved);
  $("withdrawCode").addEventListener("input", () => {
    state.confirmWithdraw = null;
    $("withdrawMessage").textContent = "";
  });
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
