// The five schemes. Sizes in pt. See SPECS.md.
const HN = '"Helvetica Neue", Helvetica, Arial, sans-serif';
const LM = '"Latin Modern Roman", "Times New Roman", serif';
const AV = '"Avenir Next", Avenir, "Helvetica Neue", sans-serif';
const PA = 'Palatino, "Palatino Linotype", "Book Antiqua", Georgia, serif';

const LM_CSS = `
@font-face { font-family: "Latin Modern Roman"; src: url("fonts/lmroman10-regular.otf"); font-weight: 400; font-style: normal; }
@font-face { font-family: "Latin Modern Roman"; src: url("fonts/lmroman10-italic.otf"); font-weight: 400; font-style: italic; }
@font-face { font-family: "Latin Modern Roman"; src: url("fonts/lmroman10-bold.otf"); font-weight: 700; font-style: normal; }
@font-face { font-family: "Latin Modern Caps"; src: url("fonts/lmromancaps10-regular.otf"); font-weight: 400; font-style: normal; }
`;

const THEMES = {
  journal: {
    key: "journal", name: "Journal",
    font: { family: HN, load: [`400 10px "Helvetica Neue"`, `700 10px "Helvetica Neue"`] },
    color: { ink: "#000", grey: "#8c8c8c", light: "#c8c8c8", accent: "#0072b2", accent2: "#d55e00",
             band: "rgba(0,114,178,0.15)", bar: "#7a7a7a", ref: "#000" },
    text: { tick: { size: 6.5 }, title: { size: 7 }, method: { size: 6.5 },
            panel: { size: 8, weight: 700 }, pick: { size: 6.5, weight: 700, color: "#fff" } },
    axis: { style: "L", color: "#000", width: 0.5, tick: { len: 2.5, dir: "out" } },
    mark: {
      other: { r: 1.5, fill: "#8c8c8c", stroke: "#fff", sw: 0.4 },
      front: { r: 2.8, fill: "#d55e00", stroke: "#fff", sw: 0.6 },
      pick: { r: 4.6, fill: "#0072b2", stroke: "#fff", sw: 0.7 },
      pickFront: { r: 4.6, fill: "#d55e00", stroke: "#fff", sw: 0.7 },
      frontLine: { width: 0.6, color: "#d55e00" },
      dotDeployed: { r: 2.6, fill: "#0072b2" }, dotBaseline: { r: 2.4, fill: "#000" }, dotOther: { r: 2.0, fill: "#8c8c8c" },
      ci: { width: 0.8, cap: 0 },
      curve: { width: 1.0 }, curveDot: { r: 2.0 },
      bar: { fill: "#7a7a7a" }, ref: { width: 0.5, dash: null },
    },
    pipeline: { style: "boxes", height: 0.72, box: { stroke: "#000", sw: 0.5, learned: "#e3e3e3", code: "#fff", radius: 0 },
                arrow: { width: 0.5, head: "small", gap: 2 }, text: { size: 7.5, weight: 400 }, io: { size: 7, style: "normal" } },
    shot: { frame: { stroke: "#9a9a9a", sw: 0.5, radius: 0 }, rule: null, letter: { size: 8, weight: 700 } },
  },

  document: {
    key: "document", name: "Document",
    font: { family: LM, css: LM_CSS, load: [`400 10px "Latin Modern Roman"`, `italic 400 10px "Latin Modern Roman"`,
                                             `700 10px "Latin Modern Roman"`, `400 10px "Latin Modern Caps"`] },
    color: { ink: "#000", grey: "#7d7d7d", light: "#bdbdbd", accent: "#7b1e2b", accent2: "#000",
             band: "rgba(123,30,43,0.14)", bar: "#6e6e6e", ref: "#000" },
    text: { tick: { size: 7.5 }, title: { size: 8, style: "italic" }, method: { size: 7.5 },
            panel: { size: 8, family: '"Latin Modern Caps", serif', format: l => `(${l})` }, pick: { size: 7, weight: 700, color: "#fff" } },
    axis: { style: "L", color: "#000", width: 0.4, tick: { len: 2, dir: "out" } },
    mark: {
      other: { r: 1.5, fill: "none", stroke: "#7d7d7d", sw: 0.45 },
      front: { r: 2.6, fill: "#000" },
      pick: { r: 4.6, fill: "#7b1e2b" },
      pickFront: { r: 4.6, fill: "#7b1e2b", stroke: "#000", sw: 0.8 },
      frontLine: { width: 0.5, color: "#000" },
      dotDeployed: { r: 2.7, fill: "#7b1e2b" }, dotBaseline: { r: 2.5, fill: "#fff", stroke: "#000", sw: 0.8 }, dotOther: { r: 2.0, fill: "none", stroke: "#7d7d7d", sw: 0.5 },
      ci: { width: 0.6, cap: 0 },
      curve: { width: 0.8 }, curveDot: { r: 1.8 },
      bar: { fill: "#6e6e6e" }, ref: { width: 0.4, dash: [2, 1.5] },
    },
    pipeline: { style: "boxes", height: 0.72, box: { stroke: "#000", sw: 0.4, learned: "#e8e8e8", code: "#fff", radius: 0 },
                arrow: { width: 0.4, head: "small", gap: 2 }, text: { size: 8.5, family: '"Latin Modern Caps", serif' }, io: { size: 8, style: "italic" } },
    shot: { frame: { stroke: "#000", sw: 0.4, radius: 0 }, rule: null, letter: { size: 8, family: '"Latin Modern Caps", serif', format: l => `(${l})` } },
  },

  swiss: {
    key: "swiss", name: "Swiss",
    font: { family: HN, load: [`300 10px "Helvetica Neue"`, `400 10px "Helvetica Neue"`, `500 10px "Helvetica Neue"`, `700 10px "Helvetica Neue"`] },
    color: { ink: "#000", grey: "#9b9b9b", light: "#d9d9d9", accent: "#e2001a", accent2: "#000",
             band: "rgba(226,0,26,0.12)", bar: "#000", ref: "#000" },
    text: { tick: { size: 6.5, weight: 300 }, title: { size: 7, weight: 500 }, method: { size: 6.5, weight: 400 },
            panel: { size: 8, weight: 700 }, pick: { size: 6.5, weight: 700, color: "#fff" } },
    axis: { style: "grid", color: "#000", width: 0.6, tick: { len: 0, dir: "out" }, grid: { color: "#d9d9d9", width: 0.4 },
            baseline: { color: "#000", width: 0.6 } },
    mark: {
      other: { r: 1.5, fill: "#9b9b9b" },
      front: { r: 2.8, fill: "#000" },
      pick: { r: 4.6, fill: "#e2001a" },
      pickFront: { r: 4.6, fill: "#000" },
      frontLine: { width: 0.6, color: "#000" },
      dotDeployed: { r: 2.6, fill: "#e2001a" }, dotBaseline: { r: 2.4, fill: "#000" }, dotOther: { r: 2.0, fill: "#9b9b9b" },
      ci: { width: 0.8, cap: 0 },
      curve: { width: 1.2 }, curveDot: { r: 2.0 },
      bar: { fill: "#000" }, ref: { width: 0.6, dash: null, color: "#000" },
    },
    pipeline: { style: "boxes", height: 0.72, box: { stroke: "#000", sw: 0.6, learned: "#000", code: "#fff", radius: 0, learnedText: "#fff" },
                arrow: { width: 0.6, head: "none", gap: 3 }, text: { size: 7.5, weight: 500, anchor: "start" }, io: { size: 7, weight: 300 } },
    shot: { frame: null, rule: { stroke: "#000", sw: 1.0 }, letter: { size: 8, weight: 700 } },
  },

  mono: {
    key: "mono", name: "Monochrome",
    font: { family: AV, load: [`400 10px "Avenir Next"`, `500 10px "Avenir Next"`, `600 10px "Avenir Next"`] },
    color: { ink: "#000", grey: "#8a8a8a", light: "#cfcfcf", accent: "#000", accent2: "#000",
             band: "rgba(0,0,0,0.10)", bar: "#8a8a8a", ref: "#000" },
    text: { tick: { size: 6.5 }, title: { size: 7, weight: 500 }, method: { size: 6.5 },
            panel: { size: 7, weight: 500, format: l => `(${l})` }, pick: { size: 6.5, weight: 600, color: "#fff" } },
    axis: { style: "box", color: "#000", width: 0.5, tick: { len: 2.5, dir: "in" }, mirror: true },
    mark: {
      other: { r: 1.4, fill: "#8a8a8a" },
      front: { r: 3.0, fill: "#fff", stroke: "#000", sw: 0.8 },
      pick: { r: 4.6, fill: "#000" },
      pickFront: { r: 4.6, fill: "#000", stroke: "#fff", sw: 0 },
      frontLine: { width: 0.6, color: "#000", dash: [2, 1.6] },
      dotDeployed: { r: 2.6, fill: "#000" }, dotBaseline: { r: 2.4, fill: "#fff", stroke: "#000", sw: 0.7 }, dotOther: { r: 2.0, fill: "#8a8a8a" },
      ci: { width: 0.6, cap: 2 },
      curve: { width: 0.9 }, curveDot: { r: 2.0, fill: "#000" },
      bar: { fill: "#8a8a8a", stroke: "#000", sw: 0.4 }, ref: { width: 0.5, dash: [3, 2] },
    },
    pipeline: { style: "boxes", height: 0.72, box: { stroke: "#000", sw: 0.5, learned: "#fff", code: "#fff", radius: 0, double: true },
                arrow: { width: 0.5, head: "triangle", gap: 2 }, text: { size: 7.5, weight: 500 }, io: { size: 7 } },
    shot: { frame: { stroke: "#000", sw: 0.6, radius: 0 }, rule: null, letter: { size: 7, weight: 500, format: l => `(${l})` } },
  },

  tufte: {
    key: "tufte", name: "Tufte",
    font: { family: PA, load: [`400 10px Palatino`, `italic 400 10px Palatino`] },
    color: { ink: "#3b3836", grey: "#9a9591", light: "#d8d4cf", accent: "#b5451b", accent2: "#3b3836",
             band: "rgba(181,69,27,0.12)", bar: "#8c8782", ref: "#9a9591" },
    text: { tick: { size: 6.5, color: "#5a5753" }, title: { size: 7, style: "italic" }, method: { size: 6.5 },
            panel: { size: 7, style: "italic" }, pick: { size: 6.5, weight: 400, color: "#fff" } },
    axis: { style: "range", color: "#5a5753", width: 0.5, tick: { len: 2, dir: "out" } },
    mark: {
      other: { r: 1.3, fill: "#9a9591" },
      front: { r: 2.6, fill: "#3b3836" },
      pick: { r: 4.4, fill: "#b5451b" },
      pickFront: { r: 4.4, fill: "#b5451b" },
      frontLine: { width: 0.5, color: "#3b3836" },
      dotDeployed: { r: 2.4, fill: "#b5451b" }, dotBaseline: { r: 2.2, fill: "#3b3836" }, dotOther: { r: 1.8, fill: "#9a9591" },
      ci: { width: 0.5, cap: 0 },
      curve: { width: 0.8 }, curveDot: { r: 1.8 },
      bar: { fill: "#8c8782" }, ref: { width: 0.5, dash: [1, 2] },
      tufteBars: true,
    },
    pipeline: { style: "words", height: 0.5, text: { size: 8 }, io: { size: 7.5, style: "italic" }, arrow: { width: 0.5, head: "small" } },
    shot: { frame: null, rule: null, letter: { size: 7, style: "italic" } },
  },
};
