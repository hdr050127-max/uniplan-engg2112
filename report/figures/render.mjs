// Render each figure page to a vector PDF at its print size (and a PNG preview) with headless Chrome.
//   node report/figures/render.mjs [preview_dir] [name ...]
// Pages are report/figures/fig_<name>.html; PDFs go to report/latex/figures/fig_<name>.pdf.
// Uses only Node's built-ins: it speaks the Chrome DevTools Protocol over WebSocket.
import { spawn } from "node:child_process";
import { mkdtempSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(HERE, "../latex/figures");
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

const [previewDir, ...wanted] = process.argv.slice(2);
const names = wanted.length ? wanted : readdirSync(HERE).filter(f => /^fig_.*\.html$/.test(f)).map(f => f.slice(4, -5));

const profile = mkdtempSync(join(tmpdir(), "uniplan-figures-"));
const chrome = spawn(CHROME, ["--headless=new", "--remote-debugging-port=0", `--user-data-dir=${profile}`,
  "--no-first-run", "--no-default-browser-check", "--hide-scrollbars", "--allow-file-access-from-files",
  "about:blank"], { stdio: ["ignore", "ignore", "pipe"] });

const endpoint = await new Promise((done, fail) => {
  let log = "";
  chrome.stderr.on("data", chunk => {
    log += chunk;
    const match = log.match(/DevTools listening on (ws:\/\/\S+)/);
    if (match) done(match[1]);
  });
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

async function evaluate(session, expression) {
  const { result } = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true }, session);
  return result.value;
}

try {
  for (const name of names) {
    const { targetId } = await send("Target.createTarget", { url: "about:blank" });
    const { sessionId: session } = await send("Target.attachToTarget", { targetId, flatten: true });
    await send("Page.enable", {}, session);
    await send("Emulation.setDeviceMetricsOverride", { width: 1200, height: 900, deviceScaleFactor: 1, mobile: false }, session);
    await send("Page.navigate", { url: pathToFileURL(join(HERE, `fig_${name}.html`)).href }, session);
    let ready = false;
    for (let i = 0; i < 300 && !ready; i++) {
      await sleep(100);
      ready = await evaluate(session, "window.__ready === true").catch(() => false);
    }
    if (!ready) throw new Error(`fig_${name}.html never set window.__ready`);
    const size = await evaluate(session, "({ w: +document.body.dataset.w, h: +document.body.dataset.h })");
    const pdf = await send("Page.printToPDF", {
      paperWidth: size.w, paperHeight: size.h, marginTop: 0, marginBottom: 0, marginLeft: 0, marginRight: 0,
      printBackground: true, pageRanges: "1", preferCSSPageSize: false,
    }, session);
    writeFileSync(join(OUT, `fig_${name}.pdf`), Buffer.from(pdf.data, "base64"));
    if (previewDir) {
      await send("Emulation.setDeviceMetricsOverride", {
        width: Math.round(size.w * 96), height: Math.round(size.h * 96), deviceScaleFactor: 3, mobile: false,
      }, session);
      await sleep(200);
      const shot = await send("Page.captureScreenshot", { format: "png" }, session);
      writeFileSync(join(previewDir, `fig_${name}.png`), Buffer.from(shot.data, "base64"));
    }
    await send("Target.closeTarget", { targetId });
    console.log(`fig_${name}: ${size.w} x ${size.h} in`);
  }
} finally {
  socket.close();
  chrome.kill();
  await sleep(300);
  rmSync(profile, { recursive: true, force: true });
}
