// Helpers shared by the figure pages. Loaded after D3 and data.js.
const PX = 96;          // CSS pixels per inch
const PT = 96 / 72;     // CSS pixels per point

// Fix the page to the figure's print size; render.mjs reads data-w / data-h (inches).
function page(widthIn, heightIn) {
  document.body.dataset.w = widthIn;
  document.body.dataset.h = heightIn;
  document.body.style.width = `${widthIn}in`;
  document.body.style.height = `${heightIn}in`;
}

// An HTML legend row; items are {kind: "dot" | "line" | "ring", color, size, dash, label}.
function legend(items, parent = document.body) {
  const row = document.createElement("div");
  row.className = "legend";
  for (const item of items) {
    const key = document.createElement("span");
    key.className = "key";
    const swatch = document.createElement("span");
    swatch.className = `swatch ${item.kind === "line" ? "line" : "dot"}`;
    if (item.kind === "line") {
      swatch.style.borderTopColor = item.color;
      if (item.dash) swatch.style.borderTopStyle = "dotted";
      if (item.width) swatch.style.borderTopWidth = item.width;
    } else {
      const size = item.size || 6;
      swatch.style.width = swatch.style.height = `${size}pt`;
      swatch.style.background = item.kind === "ring" ? "#fff" : item.color;
      if (item.kind === "ring") swatch.style.boxShadow = `inset 0 0 0 1pt ${item.color}`;
    }
    key.append(swatch, document.createTextNode(item.label));
    row.append(key);
  }
  parent.append(row);
  return row;
}

// An SVG that fills what is left of the page under any legend.
function canvas(parent = document.body) {
  const used = [...parent.children].reduce((sum, el) => {
    const style = getComputedStyle(el);
    return sum + el.getBoundingClientRect().height + parseFloat(style.marginTop) + parseFloat(style.marginBottom);
  }, 0);
  const width = parent.clientWidth;
  const height = parent.clientHeight - used;
  const svg = d3.select(parent).append("svg").attr("width", width).attr("height", height);
  return { svg, width, height };
}

// Quiet axes: hairline grid, no tick marks, optional baseline.
function styleAxis(g, { grid = 0, baseline = false } = {}) {
  g.call(sel => sel.select(".domain").attr("stroke", baseline ? "var(--rule)" : "none").attr("stroke-width", 0.8));
  g.selectAll(".tick line").attr("stroke", grid ? "var(--grid)" : "none").attr("stroke-width", 0.7);
  if (grid) g.selectAll(".tick line").attr(grid.attr, grid.length);
  return g;
}

// Draw only once Inter is loaded, so measured text widths are the printed ones.
function whenFonts(draw) {
  const faces = ["400", "500", "600"].map(weight => document.fonts.load(`${weight} 10px Inter`));
  Promise.all(faces).then(() => document.fonts.ready).then(() => { draw(); ready(); });
}

function ready() {
  document.fonts.ready.then(() => { window.__ready = true; });
}
