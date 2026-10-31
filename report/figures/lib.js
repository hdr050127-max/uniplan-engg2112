// Drawing helpers shared by the figure pages. Sizes are given in points (print) and converted to CSS px.
const PT = 96 / 72;
const pt = v => v * PT;

// Fix the page to the figure's print size; render.mjs reads data-w / data-h (inches).
function page(wIn, hIn) {
  document.body.dataset.w = wIn;
  document.body.dataset.h = hIn;
  document.body.style.width = `${wIn}in`;
  document.body.style.height = `${hIn}in`;
  return { W: wIn * 96, H: hIn * 96 };
}

// Install the theme's fonts (an optional @font-face block) and draw once they are usable,
// so measured text widths are the printed ones.
function start(T, draw) {
  if (T.font.css) {
    const style = document.createElement("style");
    style.textContent = T.font.css;
    document.head.append(style);
  }
  document.body.style.fontFamily = T.font.family;
  const loads = (T.font.load || []).map(spec => document.fonts.load(spec));
  Promise.all(loads).then(() => document.fonts.ready).then(() => draw()).then(() => { window.__ready = true; });
}

function svgCanvas(W, H) {
  return d3.select(document.body).append("svg").attr("width", W).attr("height", H)
    .style("display", "block").style("overflow", "visible");
}

// Apply a text spec {size (pt), weight, style, color, family?, caps?, tracking?} to a selection.
function styleText(sel, s, T) {
  sel.style("font-family", s.family || T.font.family)
    .style("font-size", `${s.size}pt`).style("font-weight", s.weight || 400)
    .style("font-style", s.style || "normal").attr("fill", s.color || T.color.ink);
  if (s.caps) sel.style("font-variant", "small-caps");
  if (s.tracking) sel.style("letter-spacing", s.tracking);
  return sel;
}

function text(svg, T, spec, x, y, str, anchor = "start", baseline = "auto") {
  return styleText(svg.append("text").attr("x", x).attr("y", y).attr("text-anchor", anchor)
    .attr("dominant-baseline", baseline).text(str), spec, T);
}

function measure(svg, T, spec, str) {
  const t = text(svg, T, spec, -1000, -1000, str);
  const w = t.node().getComputedTextLength();
  t.remove();
  return w;
}

function line(svg, x1, y1, x2, y2, color, width, dash) {
  const l = svg.append("line").attr("x1", x1).attr("y1", y1).attr("x2", x2).attr("y2", y2)
    .attr("stroke", color).attr("stroke-width", pt(width)).attr("stroke-linecap", "butt");
  if (dash) l.attr("stroke-dasharray", dash.map(pt).join(" "));
  return l;
}

// Axes in the theme's style.
//   x, y: d3 scales (px).  box: {l, t, r, b} px.  xTicks/yTicks: values.  xFmt/yFmt: formatters.
//   xTitle/yTitle: strings.  xData/yData: [min, max] in data units (range frames).
//   grid: "y" | "x" | null, which ticks the grid lines follow in the grid style.
//   noY: true when the vertical axis is categorical and drawn by the caller.
function axes(svg, T, o) {
  const A = T.axis, w = A.width, tl = pt(A.tick.len), out = A.tick.dir === "out";
  const { l, t, r, b } = o.box;
  const xTicks = o.xTicks.filter(v => A.style !== "range" || (v >= o.xData[0] - 1e-9 && v <= o.xData[1] + 1e-9));
  const yTicks = o.noY ? [] : o.yTicks.filter(v => A.style !== "range" || (v >= o.yData[0] - 1e-9 && v <= o.yData[1] + 1e-9));
  const gap = pt(2.5);

  if (A.style === "grid") {
    const g = A.grid;
    if (o.grid === "y") yTicks.forEach(v => line(svg, l, o.y(v), r, o.y(v), g.color, g.width));
    if (o.grid === "x") xTicks.forEach(v => line(svg, o.x(v), t, o.x(v), b, g.color, g.width));
    if (A.baseline) line(svg, l, b, r, b, A.baseline.color, A.baseline.width);
    if (!o.noY && A.leftRule) line(svg, l, t, l, b, A.leftRule.color, A.leftRule.width);
  } else if (A.style === "range") {
    line(svg, o.x(o.xData[0]), b, o.x(o.xData[1]), b, A.color, w);
    if (!o.noY) line(svg, l, o.y(o.yData[0]), l, o.y(o.yData[1]), A.color, w);
    xTicks.forEach(v => line(svg, o.x(v), b, o.x(v), b + tl, A.color, w));
    yTicks.forEach(v => line(svg, l, o.y(v), l - tl, o.y(v), A.color, w));
  } else {  // L or box
    line(svg, l, b, r, b, A.color, w);
    if (!o.noY || A.style === "box") line(svg, l, t, l, b, A.color, w);
    if (A.style === "box") { line(svg, l, t, r, t, A.color, w); line(svg, r, t, r, b, A.color, w); }
    const d = out ? 1 : -1;
    xTicks.forEach(v => line(svg, o.x(v), b, o.x(v), b + d * tl, A.color, w));
    yTicks.forEach(v => line(svg, l, o.y(v), l - d * tl, o.y(v), A.color, w));
    if (A.style === "box" && A.mirror) {
      xTicks.forEach(v => line(svg, o.x(v), t, o.x(v), t + tl, A.color, w));
      (o.noY ? [] : o.yTicks).forEach(v => line(svg, r, o.y(v), r - tl, o.y(v), A.color, w));
    }
  }
  const tickOut = (A.style === "L" || A.style === "box" || A.style === "range") && (out || A.style === "range") ? tl : 0;
  let xLabels = xTicks.map(v => [v, o.xFmt(v)]), yLabels = yTicks.map(v => [v, o.yFmt(v)]);
  if (A.style === "range") {
    // Range frames label the data extremes at the frame ends; interior ticks too close to an end are dropped.
    const ends = (data, scale, fmt) => {
      const e = data.map(v => [v, fmt(v)]);
      return [...e, ...data.length ? [] : []];
    };
    const near = (v, data, scale) => data.some(d => Math.abs(scale(d) - scale(v)) < pt(9));
    const xEnds = o.xEndFmt ? o.xData.map(v => [v, o.xEndFmt(v)]) : [];
    const yEnds = !o.noY && o.yEndFmt ? o.yData.map(v => [v, o.yEndFmt(v)]) : [];
    if (xEnds.length) xLabels = [...xEnds, ...xLabels.filter(([v]) => !near(v, o.xData, o.x))];
    if (yEnds.length) yLabels = [...yEnds, ...yLabels.filter(([v]) => !near(v, o.yData, o.y))];
    xEnds.forEach(([v]) => line(svg, o.x(v), b, o.x(v), b + tl, A.color, w));
    yEnds.forEach(([v]) => line(svg, l, o.y(v), l - tl, o.y(v), A.color, w));
  }
  xLabels.forEach(([v, s]) => text(svg, T, T.text.tick, o.x(v), b + tickOut + gap, s, "middle", "hanging"));
  yLabels.forEach(([v, s]) => text(svg, T, T.text.tick, l - tickOut - gap, o.y(v), s, "end", "middle"));
  if (o.xTitle) text(svg, T, T.text.title, (l + r) / 2, o.xTitleY ?? (b + tickOut + gap + pt(T.text.tick.size) + pt(4)), o.xTitle, "middle", "hanging");
  if (o.yTitle) {
    const yx = o.yTitleX ?? (l - tickOut - gap - pt(T.text.tick.size) * 1.9 - pt(2));
    styleText(svg.append("text").attr("transform", `translate(${yx},${(t + b) / 2}) rotate(-90)`)
      .attr("text-anchor", "middle").attr("dominant-baseline", "auto").text(o.yTitle), T.text.title, T);
  }
}

// A filled or hollow circle from a mark spec {r (pt), fill, stroke, sw (pt)}.
function dot(svg, cx, cy, m) {
  return svg.append("circle").attr("cx", cx).attr("cy", cy).attr("r", pt(m.r))
    .attr("fill", m.fill || "none").attr("stroke", m.stroke || "none").attr("stroke-width", pt(m.sw || 0));
}

function panelLetter(svg, T, x, y, letter) {
  const s = T.text.panel;
  return text(svg, T, s, x, y, s.format ? s.format(letter) : letter, "start", "hanging");
}
