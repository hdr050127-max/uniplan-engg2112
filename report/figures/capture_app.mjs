// Screenshot the running web app for the report: the sentence read back with its question, then the picks.
//   node report/figures/capture_app.mjs http://127.0.0.1:8768/
// Start the app first (python3 main.py). The sentence is final-exam item e121, written by a Claude agent
// (synthetic, not a real student); the units are the ones the pipeline evaluation planned it with.
// Writes report/figures/app_read.png (the read-back) and app_picks.png (the first pick) at twice the CSS resolution.
import { spawn } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const URL_ = process.argv[2] || "http://127.0.0.1:8768/";
const UNITS = ["ENGG2112", "AMME2301"];
const SENTENCE = "No 9ams please, and I'd like to be finished by 4 if possible";
const ANSWER = /can.?t/i;  // the hard-or-soft question: "Can't" makes "no 9ams" a limit
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

const profile = mkdtempSync(join(tmpdir(), "uniplan-app-"));
const chrome = spawn(CHROME, ["--headless=new", "--remote-debugging-port=0", `--user-data-dir=${profile}`,
  "--no-first-run", "--no-default-browser-check", "--hide-scrollbars", "about:blank"], { stdio: ["ignore", "ignore", "pipe"] });
const endpoint = await new Promise((done, fail) => {
  let log = "";
  chrome.stderr.on("data", chunk => { log += chunk; const m = log.match(/DevTools listening on (ws:\/\/\S+)/); if (m) done(m[1]); });
  setTimeout(() => fail(new Error("Chrome did not start")), 15000);
});
const socket = new WebSocket(endpoint);
await new Promise(done => socket.addEventListener("open", done, { once: true }));
let nextId = 0;
const pending = new Map();
socket.addEventListener("message", event => {
  const message = JSON.parse(event.data);
  if (message.id && pending.has(message.id)) {
    const { done, fail } = pending.get(message.id);
    pending.delete(message.id);
    message.error ? fail(new Error(JSON.stringify(message.error))) : done(message.result);
  }
});
const send = (method, params = {}, sessionId) => new Promise((done, fail) => {
  const id = ++nextId;
  pending.set(id, { done, fail });
  socket.send(JSON.stringify({ id, method, params, sessionId }));
});
const sleep = ms => new Promise(done => setTimeout(done, ms));
let session;
const js = async expression => {
  const { result, exceptionDetails } = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true }, session);
  if (exceptionDetails) throw new Error(exceptionDetails.exception?.description || exceptionDetails.text);
  return result.value;
};
const until = async (expression, what, ms = 60000) => {
  for (let waited = 0; waited < ms; waited += 150) {
    if (await js(expression).catch(() => false)) return;
    await sleep(150);
  }
  throw new Error(`timed out waiting for ${what}`);
};
// Screenshot from the top of one element to the bottom of another, page coordinates, 2x.
const shot = async (file, fromSelector, toSelector, pad = 12, maxHeight = 2000) => {
  // The right edge is where the content ends, not the (wider) container, so no empty band is kept.
  const box = await js(`(() => { const first = document.querySelector(${JSON.stringify(fromSelector)});
    const last = document.querySelector(${JSON.stringify(toSelector)});
    const a = first.getBoundingClientRect(), b = last.getBoundingClientRect();
    const inside = [];
    for (const root of [first, last]) {
      const walk = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      while (walk.nextNode()) if (walk.currentNode.textContent.trim()) {
        const range = document.createRange(); range.selectNodeContents(walk.currentNode); inside.push(range.getBoundingClientRect());
      }
      root.querySelectorAll('button, .segmented').forEach(el => inside.push(el.getBoundingClientRect()));
    }
    const left = Math.min(a.left, b.left), right = Math.max(...inside.map(r => r.right));
    return { x: left + scrollX, y: a.top + scrollY, w: right - left, h: b.bottom - a.top }; })()`);
  const clip = { x: box.x - pad, y: box.y - pad, width: box.w + 2 * pad, height: Math.min(box.h + 2 * pad, maxHeight), scale: 2 };
  const { data } = await send("Page.captureScreenshot", { format: "png", clip, captureBeyondViewport: true }, session);
  writeFileSync(join(HERE, file), Buffer.from(data, "base64"));
  console.log(`${file}: ${Math.round(clip.width)} x ${Math.round(clip.height)} CSS px`);
};

try {
  const { targetId } = await send("Target.createTarget", { url: "about:blank" });
  ({ sessionId: session } = await send("Target.attachToTarget", { targetId, flatten: true }));
  await send("Page.enable", {}, session);
  await send("Emulation.setDeviceMetricsOverride", { width: 1280, height: 900, deviceScaleFactor: 2, mobile: false }, session);
  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: "light" }] }, session);
  await send("Page.navigate", { url: URL_ }, session);
  await until("!!document.getElementById('unitQuery') && document.readyState === 'complete'", "the page");
  for (const code of UNITS) {
    await js(`(() => { const q = document.getElementById('unitQuery'); q.focus(); q.value = ${JSON.stringify(code)};
      q.dispatchEvent(new Event('input', { bubbles: true })); })()`);
    await until(`[...document.querySelectorAll('#suggestions li .suggest-code')].some(s => s.textContent.trim() === ${JSON.stringify(code)})`, `suggestion ${code}`);
    await js(`[...document.querySelectorAll('#suggestions li')].find(li => li.querySelector('.suggest-code').textContent.trim() === ${JSON.stringify(code)}).click()`);
    await sleep(400);
  }
  await js(`(() => { const t = document.getElementById('sayText'); t.value = ${JSON.stringify(SENTENCE)};
    t.dispatchEvent(new Event('input', { bubbles: true })); document.getElementById('sayRead').click(); })()`);
  await until("!document.getElementById('sayResult').hidden && !!document.querySelector('#sayResult .ask')", "the read-back and its question");
  await sleep(1500);  // the underline animation
  await js("document.activeElement && document.activeElement.blur()");
  await shot("app_read.png", "#sayResult", "#sayResult", 10);
  await js(`[...document.querySelectorAll('#sayResult .ask button')].find(b => ${ANSWER}.test(b.textContent)).click()`);
  await sleep(600);
  await js("document.getElementById('submitButton').click()");
  await until("!document.getElementById('result').hidden && document.querySelectorAll('#result .plan').length >= 3", "three picks");
  await sleep(2500);
  await js("document.activeElement && document.activeElement.blur(); window.scrollTo(0, 0)");
  // The first pick's card (the list beside the week view); its reason compares it with the second pick.
  await js("document.querySelector('#result .plan').id = 'shot-first'");
  await shot("app_picks.png", "#shot-first", "#shot-first", 10);
} finally {
  socket.close();
  chrome.kill();
  await sleep(300);
  rmSync(profile, { recursive: true, force: true });
}
