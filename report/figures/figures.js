// The five figures. Each takes a theme T (themes.js) and draws into the page at its print size.
// Data comes from data.js (generated); nothing on a figure beyond axes, ticks, panel letters,
// method names and the pick numbers. Meaning goes in the captions.

// ---------------------------------------------------------------- Figure 2: the Pareto example
function figPareto(T) {
  const { W, H } = page(2.95, 2.4);
  const svg = svgCanvas(W, H);
  const ex = DATA.pareto;
  const pts = Object.entries(ex.points).map(([id, v]) => ({ id, x: v[0], y: v[1] }));
  const isPick = p => ex.picks.includes(p.id), isFront = p => ex.front.includes(p.id);
  const X = [5.3, 7.3], Y = [2.8, 5.0];
  const shown = pts.filter(p => p.x <= X[1]);   // 7 dominated types beyond 7.3 h are left to the caption
  const xData = d3.extent(shown, p => p.x), yData = d3.extent(shown, p => p.y);
  const box = { l: pt(22), t: pt(7), r: W - pt(7), b: H - pt(26) };
  const x = d3.scaleLinear(X, [box.l, box.r]), y = d3.scaleLinear(Y, [box.b, box.t]);
  axes(svg, T, { x, y, box, xTicks: [5.5, 6, 6.5, 7], yTicks: [3, 4, 5], xFmt: d3.format(".1f"), yFmt: d3.format("d"),
    xTitle: "Waiting between classes (hours per week)", yTitle: "Days on campus per week",
    xData, yData, grid: "y", yTitleX: pt(7.5), xEndFmt: d3.format(".1f"), yEndFmt: d3.format(".1f") });

  // The front as a staircase: every type to its upper right is dominated by one of its points.
  const range = T.axis.style === "range";
  const stairs = ex.front.map(id => pts.find(p => p.id === id)).sort((a, b) => a.x - b.x);
  const path = [[stairs[0].x, range ? yData[1] : Y[1]]];
  stairs.forEach((p, i) => { const n = stairs[i + 1]; path.push([p.x, p.y], [n ? n.x : (range ? xData[1] : X[1]), p.y]); });
  const fl = T.mark.frontLine;
  const sp = svg.append("path").attr("d", d3.line(d => x(d[0]), d => y(d[1]))(path))
    .attr("fill", "none").attr("stroke", fl.color).attr("stroke-width", pt(fl.width)).attr("stroke-linejoin", "round");
  if (fl.dash) sp.attr("stroke-dasharray", fl.dash.map(pt).join(" "));

  shown.filter(p => !isPick(p) && !isFront(p)).forEach(p => dot(svg, x(p.x), y(p.y), T.mark.other));
  shown.filter(p => isFront(p) && !isPick(p)).forEach(p => dot(svg, x(p.x), y(p.y), T.mark.front));
  ex.picks.forEach((id, i) => {
    const p = pts.find(q => q.id === id);
    dot(svg, x(p.x), y(p.y), isFront(p) ? T.mark.pickFront : T.mark.pick);
    text(svg, T, T.text.pick, x(p.x), y(p.y) + pt(0.3), String(i + 1), "middle", "middle");
  });
}

// ---------------------------------------------------------------- Figure 3: both final exams
function figResults(T) {
  const { W, H } = page(6.27, 1.6);
  const svg = svgCanvas(W, H);
  const short = {
    "Keyword rules": "Keyword rules", "TF-IDF + logistic regression": "TF-IDF classifier",
    "Qwen2.5-7B zero-shot (prompt v1)": "Qwen2.5-7B, prompt v1", "Qwen2.5-7B zero-shot (prompt v2)": "Qwen2.5-7B, prompt v2",
    "Qwen2.5-7B QLoRA round 1": "QLoRA round 1", "Qwen2.5-7B QLoRA round 2 (deployed)": "QLoRA round 2 (deployed)",
    "Qwen2.5-14B judging each pair (once, as shown)": "Qwen2.5-14B as judge", "Cares-only rule": "Cares-only rule",
    "Equal weights": "Equal weights", "Trained logistic regression (deployed)": "Trained ranker (deployed)",
  };
  const role = d => d.deployed ? "deployed" : (d.method === "Keyword rules" || d.method === "Equal weights") ? "baseline" : "other";
  const parse = DATA.parse, rank = DATA.rank.filter(d => d.pairs);
  const chance = DATA.rank.find(d => d.reference !== undefined).reference;
  const labelW = rows => d3.max(rows, d => measure(svg, T, T.text.method, short[d.method])) + pt(5);
  const L = labelW(parse), RL = labelW(rank);
  const rowH = pt(12.5), top = pt(13), gap = pt(20), gap2 = pt(22), right = pt(5);
  const avail = W - L - RL - 2 * gap - gap2 - right;
  const P = avail * 0.3, P3 = avail - 2 * P;
  const b = top + 6 * rowH;
  const noY = T.axis.style === "range";

  function panel(x0, w, rows, metric, domain, ticks, title, letterX, letter, chanceLine) {
    const box = { l: x0, t: top - pt(2), r: x0 + w, b };
    const x = d3.scaleLinear(domain, [box.l, box.r]);
    const xData = [d3.min(rows, d => d[metric].low), d3.max(rows, d => d[metric].high)];
    axes(svg, T, { x, y: null, box, xTicks: ticks, yTicks: [], xFmt: d3.format("d"), yFmt: () => "", xTitle: title,
      xData, yData: [0, 0], grid: "x", noY, xEndFmt: d3.format("d") });
    if (chanceLine !== undefined) {
      const r = T.mark.ref;
      line(svg, x(chanceLine), box.t, x(chanceLine), box.b, r.color || T.color.ref, r.width, r.dash);
    }
    rows.forEach((d, i) => {
      const cy = top + i * rowH + rowH / 2, v = d[metric], rl = role(d);
      const m = rl === "deployed" ? T.mark.dotDeployed : rl === "baseline" ? T.mark.dotBaseline : T.mark.dotOther;
      const color = rl === "deployed" ? T.color.accent : rl === "baseline" ? T.color.ink : T.color.grey;
      const ci = T.mark.ci;
      line(svg, x(v.low), cy, x(v.high), cy, color, ci.width);
      if (ci.cap) [v.low, v.high].forEach(e => line(svg, x(e), cy - pt(ci.cap) / 2, x(e), cy + pt(ci.cap) / 2, color, ci.width));
      dot(svg, x(v.value), cy, m.stroke ? m : { ...m, stroke: "#fff", sw: 0.6 });
    });
    panelLetter(svg, T, letterX, pt(1), letter);
  }
  function labels(x1, rows) {
    rows.forEach((d, i) => text(svg, T, T.text.method, x1, top + i * rowH + rowH / 2 + pt(0.3), short[d.method], "end", "middle"));
  }
  labels(L - pt(4), parse);
  panel(L, P, parse, "clauses", [78, 100], [80, 90, 100], "Clauses right (%)", pt(1), "a");
  panel(L + P + gap, P, parse, "sentences", [60, 86], [60, 70, 80], "Whole sentences (%)", L + P + gap - pt(2), "b");
  const c0 = L + 2 * P + gap + gap2;
  labels(c0 + RL - pt(4), rank);
  panel(c0 + RL, P3, rank, "pairs", [45, 95], [50, 70, 90], "Pairs agreed (%)", c0, "c", chance);
}

// ---------------------------------------------------------------- Figure 5: front sizes and the learning curve
function figAppendix(T) {
  const { W, H } = page(6.27, 2.0);
  const svg = svgCanvas(W, H);
  const mid = pt(26);
  const Wp = (W - mid) / 2;
  const tufte = !!T.mark.tufteBars;

  // (a) front sizes
  {
    const x0 = 0;
    const box = { l: x0 + pt(24), t: pt(14), r: x0 + Wp - pt(4), b: H - pt(26) };
    const sizes = Object.fromEntries(Object.entries(DATA.front_sizes).map(([k, v]) => [+k, v]));
    const ns = d3.range(1, DATA.candidate_min + 1);
    const x = d3.scaleBand(ns, [box.l, box.r]).paddingInner(0.45).paddingOuter(0.3);
    const xc = n => x(n) + x.bandwidth() / 2;
    const y = d3.scaleLinear([0, 80], [box.b, box.t]);
    const yTicks = [0, 20, 40, 60, 80];
    if (!tufte) {
      axes(svg, T, { x: xc, y, box, xTicks: ns, yTicks, xFmt: d3.format("d"), yFmt: d3.format("d"),
        xTitle: "Non-dominated types per student", yTitle: "Exam students", xData: [1, 10], yData: [0, 80], grid: "y", yTitleX: pt(7.5) });
    }
    ns.forEach(n => {
      const c = sizes[n] || 0;
      if (!c) return;
      const m = T.mark.bar;
      svg.append("rect").attr("x", x(n)).attr("y", y(c)).attr("width", x.bandwidth()).attr("height", y(0) - y(c))
        .attr("fill", m.fill).attr("stroke", m.stroke || "none").attr("stroke-width", pt(m.sw || 0));
    });
    if (tufte) {
      // Tufte bars: no axes; white gridlines cut through the bars at the tick values.
      yTicks.slice(1).forEach(v => line(svg, box.l, y(v), box.r, y(v), "#fff", 0.9));
      yTicks.forEach(v => text(svg, T, T.text.tick, box.l - pt(4), y(v), String(v), "end", "middle"));
      ns.forEach(n => text(svg, T, T.text.tick, xc(n), box.b + pt(3), String(n), "middle", "hanging"));
      text(svg, T, T.text.title, (box.l + box.r) / 2, box.b + pt(3) + pt(6.5) + pt(4), "Non-dominated types per student", "middle", "hanging");
      styleText(svg.append("text").attr("transform", `translate(${pt(7.5)},${(box.t + box.b) / 2}) rotate(-90)`)
        .attr("text-anchor", "middle").text("Exam students"), T.text.title, T);
    }
    const r = T.mark.ref;
    line(svg, xc(DATA.candidate_min), box.t, xc(DATA.candidate_min), box.b, r.color || T.color.ref, r.width, r.dash);
    panelLetter(svg, T, x0 + pt(1), pt(1), "a");
  }
  // (b) learning curve
  {
    const x0 = Wp + mid;
    const box = { l: x0 + pt(24), t: pt(14), r: W - pt(5), b: H - pt(26) };
    const curve = DATA.curve;
    const x = d3.scaleLinear([0, 125], [box.l, box.r]);
    const y = d3.scaleLinear([75, 95], [box.b, box.t]);
    axes(svg, T, { x, y, box, xTicks: [0, 30, 60, 90, 120], yTicks: [75, 80, 85, 90, 95], xFmt: d3.format("d"), yFmt: d3.format("d"),
      xTitle: "Training personas", yTitle: "Held-out pairs agreed (%)",
      xData: d3.extent(curve, d => d.personas), yData: [d3.min(curve, d => d.accuracy - d.sd), d3.max(curve, d => d.accuracy + d.sd)],
      grid: "y", yTitleX: x0 + pt(7.5), xEndFmt: d3.format("d"), yEndFmt: d3.format("d") });
    svg.append("path").attr("d", d3.area(d => x(d.personas), d => y(d.accuracy - d.sd), d => y(d.accuracy + d.sd))(curve))
      .attr("fill", T.color.band);
    const r = T.mark.ref;
    line(svg, x(60), box.t, x(60), box.b, r.color || T.color.ref, r.width, r.dash);
    svg.append("path").attr("d", d3.line(d => x(d.personas), d => y(d.accuracy))(curve))
      .attr("fill", "none").attr("stroke", T.color.accent).attr("stroke-width", pt(T.mark.curve.width)).attr("stroke-linejoin", "round");
    curve.forEach(d => dot(svg, x(d.personas), y(d.accuracy), { r: T.mark.curveDot.r, fill: T.mark.curveDot.fill || T.color.accent, stroke: "#fff", sw: 0.6 }));
    panelLetter(svg, T, x0 + pt(1), pt(1), "b");
  }
}

// ---------------------------------------------------------------- Figure 1: the pipeline
function figPipeline(T) {
  const P = T.pipeline;
  const { W, H } = page(6.27, P.height);
  const svg = svgCanvas(W, H);
  const stages = [{ n: "Parse", learned: true }, { n: "Confirm" }, { n: "Schedule" }, { n: "Rank", learned: true }, { n: "Explain" }];
  const IN = ["Units and", "one sentence"], OUT = ["Three timetables,", "each with a reason"];
  const mid = H / 2;

  function arrow(x1, x2, yy) {
    const a = P.arrow, c = T.color.ink;
    const headL = a.head === "none" ? 0 : a.head === "triangle" ? pt(4) : pt(3);
    line(svg, x1, yy, x2 - headL, yy, c, a.width);
    if (a.head === "triangle") {
      svg.append("path").attr("d", `M${x2},${yy} L${x2 - headL},${yy - pt(1.8)} L${x2 - headL},${yy + pt(1.8)} Z`).attr("fill", c);
    } else if (a.head === "small") {
      svg.append("path").attr("d", `M${x2 - headL},${yy - pt(2)} L${x2},${yy} L${x2 - headL},${yy + pt(2)}`)
        .attr("fill", "none").attr("stroke", c).attr("stroke-width", pt(a.width)).attr("stroke-linejoin", "round").attr("stroke-linecap", "round");
    }
  }

  if (P.style === "words") {
    // A single typeset line: input, the five stage names and the output, joined by thin arrows.
    const specs = [{ s: IN.join(" "), t: P.io }, ...stages.map(st => ({ s: st.n, t: { ...P.text, color: st.learned ? T.color.accent : T.color.ink } })),
      { s: OUT.join(" "), t: P.io }];
    const widths = specs.map(sp => measure(svg, T, sp.t, sp.s));
    const arrowW = pt(14), padA = pt(5);
    const total = d3.sum(widths) + (specs.length - 1) * (arrowW + 2 * padA);
    let cx = (W - total) / 2;
    specs.forEach((sp, i) => {
      text(svg, T, sp.t, cx, mid + pt(0.5), sp.s, "start", "middle");
      cx += widths[i];
      if (i < specs.length - 1) { arrow(cx + padA, cx + padA + arrowW, mid); cx += arrowW + 2 * padA; }
    });
    return;
  }

  const B = P.box;
  const inW = pt(50), outW = pt(66), slot = pt(16), edge = pt(2);
  const boxW = (W - inW - outW - 6 * slot - 2 * edge) / 5;
  const boxH = pt(30);
  // input
  IN.forEach((s, i) => text(svg, T, P.io, edge, mid + (i - 0.5) * pt(9) + pt(0.5), s, "start", "middle"));
  let cx = edge + inW;
  stages.forEach(st => {
    arrow(cx + pt(P.arrow.gap), cx + slot - pt(P.arrow.gap), mid);
    cx += slot;
    const fill = st.learned ? B.learned : B.code;
    svg.append("rect").attr("x", cx).attr("y", mid - boxH / 2).attr("width", boxW).attr("height", boxH)
      .attr("fill", fill).attr("stroke", B.stroke).attr("stroke-width", pt(B.sw)).attr("rx", pt(B.radius || 0));
    if (B.double && st.learned) {
      const d = pt(2);
      svg.append("rect").attr("x", cx + d).attr("y", mid - boxH / 2 + d).attr("width", boxW - 2 * d).attr("height", boxH - 2 * d)
        .attr("fill", "none").attr("stroke", B.stroke).attr("stroke-width", pt(B.sw));
    }
    const tt = { ...P.text, color: st.learned && B.learnedText ? B.learnedText : T.color.ink };
    if (P.text.anchor === "start") text(svg, T, tt, cx + pt(5), mid + pt(0.5), st.n, "start", "middle");
    else text(svg, T, tt, cx + boxW / 2, mid + pt(0.5), st.n, "middle", "middle");
    cx += boxW;
  });
  arrow(cx + pt(P.arrow.gap), cx + slot - pt(P.arrow.gap), mid);
  cx += slot;
  OUT.forEach((s, i) => text(svg, T, P.io, cx, mid + (i - 0.5) * pt(9) + pt(0.5), s, "start", "middle"));
}

// ---------------------------------------------------------------- Figure 4: the web page
function figApp(T) {
  const { W, H } = page(6.27, 1.7);
  const S = T.shot;
  const root = document.createElement("div");
  root.style.cssText = `position:relative;width:${W}px;height:${H}px;`;
  document.body.append(root);
  const imgs = [["a", "app_read.png"], ["b", "app_picks.png"]].map(([letter, src]) => {
    const img = new Image(); img.src = src; return { letter, img };
  });
  return Promise.all(imgs.map(i => i.img.decode())).then(() => {
    const letterH = pt(S.letter.size) * 1.25, gapL = pt(S.rule ? 4 : 3), gapX = pt(16);
    const frame = S.frame ? pt(S.frame.sw) : 0;
    const ratio = i => i.img.naturalWidth / i.img.naturalHeight;
    const hMax = H - letterH - gapL - 2 * frame - pt(2);  // keep the bottom edge clear of the page edge
    const h = Math.min(hMax, (W - gapX - 4 * frame) / (ratio(imgs[0]) + ratio(imgs[1])));
    const widths = imgs.map(i => h * ratio(i));
    const total = d3.sum(widths) + gapX + 4 * frame;
    let cx = (W - total) / 2;
    const fmt = S.letter.format || (l => l);
    imgs.forEach((it, k) => {
      const w = widths[k];
      const fig = document.createElement("div");
      fig.style.cssText = `position:absolute;left:${cx}px;top:0;width:${w + 2 * frame}px;`;
      const lab = document.createElement("div");
      lab.textContent = fmt(it.letter);
      lab.style.cssText = `font-family:${S.letter.family || T.font.family};font-size:${S.letter.size}pt;font-weight:${S.letter.weight || 400};` +
        `font-style:${S.letter.style || "normal"};color:${T.color.ink};height:${letterH}px;line-height:${letterH}px;`;
      if (S.letter.caps) lab.style.fontVariant = "small-caps";
      if (S.rule) lab.style.cssText += `border-top:${S.rule.sw}pt solid ${S.rule.stroke};padding-top:${pt(1.5)}px;`;
      fig.append(lab);
      const box = document.createElement("div");
      box.style.cssText = `margin-top:${gapL}px;width:${w}px;height:${h}px;overflow:hidden;background:#fff;` +
        (S.frame ? `border:${S.frame.sw}pt solid ${S.frame.stroke};border-radius:${S.frame.radius || 0}pt;` : "");
      it.img.style.cssText = `display:block;width:${w}px;height:${h}px;`;
      box.append(it.img);
      fig.append(box);
      root.append(fig);
      cx += w + 2 * frame + gapX;
    });
  });
}
