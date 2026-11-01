"""Draw the report's five figures from report/data/figures.json and the two app screenshots.

Run from anywhere: /usr/local/bin/python3 report/scripts/make_figures.py  (needs matplotlib and fontTools)
Writes report/latex/figures/fig_{pipeline,pareto,results,app,appendix}.pdf at their printed size, with text
in the report's Latin Modern, and a 300 dpi PNG preview of each to report/figures/preview/.
Run report/scripts/figure_data.py first when the results change; no number here is typed by hand.
All evaluation data is AI-written (synthetic), not real students; see the report's Appendix B.
"""
import json
import math
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.patches import ArrowStyle, FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle

ROOT = Path(__file__).resolve().parents[2]
DATA = json.loads((ROOT / "report/data/figures.json").read_text())
OUT = ROOT / "report/latex/figures"
PREVIEW = ROOT / "report/figures/preview"
FONTS = ROOT / "report/figures/fonts"

# One palette for every figure: purple marks what was learned (and deployed), greys everything else.
ACCENT = "#5B4E9E"  # the report's accent colour (main.tex) and the app's
TINT = "#ECE9F6"    # learned-model boxes, the deployed rows
BAND = "#DCD7EE"    # spread of the learning curve
INK = "#222222"
AXIS = "#333333"
SOFT = "#5C5C5C"    # annotations
GREY = "#9C9C9C"    # other methods, dominated timetables, bars
RULE = "#C4C4C4"    # reference lines
FAINT = "#EBEBEB"   # row guides
SHADE = "#F0F0F0"   # region the Pareto front dominates
CAPS = "Latin Modern Roman Caps"
NOTE = dict(fontsize=8, style="italic", color=SOFT)
ARROW = ArrowStyle("-|>", head_length=0.45, head_width=0.22)

# Short names for the methods on the result axes, keyed by the names in the report's tables.
PARSE_NAMES = {
    "Keyword rules": "Keyword rules",
    "TF-IDF + logistic regression": "TF-IDF + logistic reg.",
    "Qwen2.5-7B zero-shot (prompt v1)": "Qwen 7B zero-shot v1",
    "Qwen2.5-7B zero-shot (prompt v2)": "Qwen 7B zero-shot v2",
    "Qwen2.5-7B QLoRA round 1": "Qwen 7B QLoRA round 1",
    "Qwen2.5-7B QLoRA round 2 (deployed)": "Qwen 7B QLoRA round 2",
}
RANK_NAMES = {
    "Qwen2.5-14B judging each pair (once, as shown)": "Qwen 14B judging pairs",
    "Cares-only rule": "Cares-only rule",
    "Equal weights": "Equal weights",
    "Trained logistic regression (deployed)": "Logistic regression",
}
BASELINES = {"Keyword rules", "Equal weights"}


def truetype(otf: Path, folder: Path) -> Path:
    """Latin Modern ships as CFF OpenType, which matplotlib cannot embed cleanly; redraw it as TrueType."""
    font = TTFont(otf)
    order = font.getGlyphOrder()
    source = font.getGlyphSet()
    glyf = newTable("glyf")
    glyf.glyphOrder = order
    glyf.glyphs = {}
    for name in order:
        pen = TTGlyphPen(source)
        source[name].draw(Cu2QuPen(pen, 1.0, reverse_direction=True))
        glyf.glyphs[name] = pen.glyph()
    del font["CFF "]
    font["loca"] = newTable("loca")
    font["glyf"] = glyf
    glyf.compile(font)
    for name, glyph in glyf.glyphs.items():
        font["hmtx"][name] = (font["hmtx"][name][0], getattr(glyph, "xMin", 0))
    maxp = font["maxp"] = newTable("maxp")
    maxp.tableVersion = 0x00010000
    maxp.maxZones = 1
    for field in ("maxTwilightPoints", "maxStorage", "maxFunctionDefs", "maxInstructionDefs",
                  "maxStackElements", "maxSizeOfInstructions", "maxComponentElements"):
        setattr(maxp, field, 0)
    post = font["post"]
    post.formatType, post.extraNames, post.mapping, post.glyphOrder = 2.0, [], {}, order
    font.sfntVersion = "\0\1\0\0"
    out = folder / (otf.stem + ".ttf")
    font.save(out)
    return out


def setup(folder: Path) -> None:
    for name in ("lmroman10-regular", "lmroman10-bold", "lmroman10-italic", "lmromancaps10-regular"):
        font_manager.fontManager.addfont(str(truetype(FONTS / f"{name}.otf", folder)))
    plt.rcParams.update({
        "font.family": "Latin Modern Roman", "font.size": 8.5, "text.color": INK,
        "axes.linewidth": 0.6, "axes.edgecolor": AXIS, "axes.labelsize": 9, "axes.labelcolor": INK,
        "axes.labelpad": 3, "axes.spines.top": False, "axes.spines.right": False,
        "xtick.labelsize": 8.5, "ytick.labelsize": 8.5, "xtick.color": AXIS, "ytick.color": AXIS,
        "xtick.labelcolor": INK, "ytick.labelcolor": INK,
        "xtick.major.width": 0.6, "ytick.major.width": 0.6, "xtick.major.size": 2.5, "ytick.major.size": 2.5,
        "xtick.major.pad": 2, "ytick.major.pad": 2,
        "pdf.fonttype": 42, "axes.unicode_minus": True, "lines.solid_capstyle": "butt",
    })


def axes_at(fig, left, bottom, width, height):
    """Axes placed in inches from the figure's bottom-left corner."""
    w, h = fig.get_size_inches()
    return fig.add_axes((left / w, bottom / h, width / w, height / h))


def text_width(fig, text, **style) -> float:
    """Printed width of a string in inches."""
    t = fig.text(0, 0, text, **style)
    width = t.get_window_extent(fig.canvas.get_renderer()).width / fig.dpi
    t.remove()
    return width


def inches(fig, ax, x, y, coords="data"):
    """Where a point of an axes lands on the figure, in inches."""
    transform = ax.transData if coords == "data" else ax.transAxes
    return fig.dpi_scale_trans.inverted().transform(transform.transform((x, y)))


def letter(fig, x, y, text, title=None):
    """Panel letter (and an optional heading after it), top-left at (x, y) inches."""
    fig.text(x, y, text, fontsize=10, weight="bold", ha="left", va="top", transform=fig.dpi_scale_trans)
    if title:
        fig.text(x + 0.17, y - 0.01, title, fontsize=9, ha="left", va="top", transform=fig.dpi_scale_trans)


def save(fig, name):
    fig.savefig(OUT / f"{name}.pdf", metadata={"CreationDate": None})
    fig.savefig(PREVIEW / f"{name}.png", dpi=300)
    plt.close(fig)


def fig_pipeline():
    """Figure 1: the five stages, learned ones filled in the accent colour."""
    W, H = 6.27, 0.81
    fig = plt.figure(figsize=(W, H))
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set(xlim=(0, W), ylim=(0, H))
    ax.axis("off")
    stages = [  # name, what it does, who does it: "learned model", "student" or "program"
        ("Parse", "reads the\nsentence as\nconditions", "learned model"),
        ("Confirm", "the student\nchecks the\nconditions", "student"),
        ("Schedule", "lists every\nvalid timetable,\nkeeps a short list", "program"),
        ("Rank", "scores them,\nkeeps the\nbest three", "learned model"),
        ("Explain", "writes a\nreason for\neach pick", "program"),
    ]
    source, result = "Courses and\none sentence", "Three\ntimetables,\neach with\na reason"
    name_style = dict(fontsize=9.5, weight="bold")
    desc_style = dict(fontsize=8, linespacing=1.08)
    end_style = dict(fontsize=8, linespacing=1.08)
    pad = 0.08
    widths = [max(text_width(fig, n, **name_style), text_width(fig, d, **desc_style)) + 2 * pad for n, d, _ in stages]
    src_w, res_w = text_width(fig, source, **end_style), text_width(fig, result, **end_style)
    gap = (W - 0.04 - src_w - res_w - sum(widths)) / 6
    assert gap > 0.17, f"pipeline too crowded: {gap:.2f} in between boxes"
    bottom, height = 0.15, 0.63
    top, mid = bottom + height, bottom + height / 2

    def arrow(x0, x1):
        ax.add_patch(FancyArrowPatch((x0 + 0.025, mid), (x1 - 0.025, mid), arrowstyle=ARROW, mutation_scale=9,
                                     lw=0.7, color=INK, shrinkA=0, shrinkB=0))

    x = 0.02
    ax.text(x, mid, source, ha="left", va="center", **end_style)
    x += src_w
    for (name, desc, who), w in zip(stages, widths):
        learned = who == "learned model"
        arrow(x, x + gap)
        x += gap
        ax.add_patch(FancyBboxPatch((x, bottom), w, height, boxstyle="round,pad=0,rounding_size=0.05",
                                    fc=TINT if learned else "white", ec=ACCENT if learned else AXIS,
                                    lw=0.9 if learned else 0.6))
        ax.text(x + w / 2, top - 0.055, name, ha="center", va="top", **name_style)
        ax.text(x + w / 2, top - 0.23, desc, ha="center", va="top", **desc_style)
        ax.text(x + w / 2, bottom - 0.03, who, ha="center", va="top",
                fontsize=7.5, family=CAPS, color=ACCENT if learned else SOFT)
        x += w
    arrow(x, x + gap)
    ax.text(x + gap, mid, result, ha="left", va="center", **end_style)
    save(fig, "fig_pipeline")


def fig_pareto():
    """Figure 2: every type of valid timetable for one exam student, its Pareto front and the ranker's picks.

    Half width, so it sits beside the text; the plot carries only marks and the picks' numbers, and the legend
    below it says what they are. The x axis is broken: one cluster of dominated types sits far right, and a
    continuous axis would pile the other types on top of each other."""
    p = DATA["pareto"]
    points = {k: (v[0], v[1]) for k, v in p["points"].items()}  # waiting hours, campus days
    assert len(points) == p["profiles"]
    front = {k for k, a in points.items() if not any(b[0] <= a[0] and b[1] <= a[1] and b != a for b in points.values())}
    assert front == set(p["front"]), "the front on these two measures must be the data's front"

    xs = sorted(g for g, _ in points.values())
    split = max(range(1, len(xs)), key=lambda i: xs[i] - xs[i - 1])  # the widest empty stretch of waiting time
    near, far = (xs[0] - 0.17, xs[split - 1] + 0.13), (xs[split] - 0.08, xs[-1] + 0.08)
    y0, y1 = 2.84, 4.92
    W, H = 2.95, 2.4
    left, bottom, right, top, gap = 0.47, 0.89, 0.05, 0.04, 0.07
    scale = (W - left - right - gap) / (near[1] - near[0] + far[1] - far[0])
    fig = plt.figure(figsize=(W, H))
    a = axes_at(fig, left, bottom, scale * (near[1] - near[0]), H - bottom - top)
    b = axes_at(fig, W - right - scale * (far[1] - far[0]), bottom, scale * (far[1] - far[0]), H - bottom - top)

    stair = sorted(points[k] for k in front)
    edge = [(stair[0][0], y1)]
    for (g, d), nxt in zip(stair, stair[1:] + [(far[1], None)]):
        edge += [(g, d), (nxt[0], d)]
    rest = [v for k, v in points.items() if k not in front]
    picks = [points[k] for k in p["picks"]]
    for ax, lim in ((a, near), (b, far)):
        ax.set(xlim=lim, ylim=(y0, y1))
        ax.add_patch(Polygon(edge + [(far[1], y1)], closed=True, fc=SHADE, ec="none", zorder=0))
        ax.plot(*zip(*edge), color=INK, lw=0.9, zorder=2)
        ax.scatter(*zip(*rest), s=8, fc="white", ec=GREY, lw=0.6, zorder=3)
        ax.scatter(*zip(*(points[k] for k in front)), s=15, fc=INK, ec=INK, lw=0.4, zorder=4)
        ax.scatter(*zip(*picks), s=62, fc="none", ec=ACCENT, lw=1.1, zorder=5)
    offsets = [((-7, 0), "right", "center"), ((-5, 5), "right", "bottom"), ((0, -7), "center", "top")]
    for rank, (xy, (off, ha, va)) in enumerate(zip(picks, offsets), 1):
        a.annotate(str(rank), xy, xytext=off, textcoords="offset points", ha=ha, va=va, fontsize=9, weight="bold",
                   color=ACCENT)

    b.spines["left"].set_visible(False)
    b.tick_params(axis="y", left=False, labelleft=False)
    cut = dict(marker=[(-0.5, -1), (0.5, 1)], ms=5, ls="none", color=AXIS, mew=0.6, clip_on=False)
    a.plot([1], [0], transform=a.transAxes, **cut)
    b.plot([0], [0], transform=b.transAxes, **cut)
    a.set_xticks([t / 2 for t in range(math.floor(near[0] * 2) + 1, math.floor(near[1] * 2) + 1)])
    b.set_xticks([t / 2 for t in range(math.floor(far[0] * 2) + 1, math.floor(far[1] * 2) + 1)])
    for ax in (a, b):
        ax.xaxis.set_major_formatter("{x:.1f}")
    a.set_yticks([3.0, 3.5, 4.0, 4.5])
    a.set_ylabel("Campus days a week")
    fig.text((left + W - right) / 2 / W, 0.55 / H, "Waiting time (hours a week)", ha="center", va="bottom",
             fontsize=9)

    # The legend, drawn in inches under the plot: two columns, read down.
    columns = [["Pareto front", "dominated type", "dominated region"], ["ranker's top three", "better"]]
    handle, gutter, pitch = 0.29, 0.16, 0.16
    widths = [handle + max(text_width(fig, t, fontsize=8) for t in col) for col in columns]
    key = fig.add_axes((0, 0, 1, 1))
    key.set(xlim=(0, W), ylim=(0, H))
    key.axis("off")
    x = (W - sum(widths) - gutter) / 2
    for col, width in zip(columns, widths):
        for i, text in enumerate(col):
            y, hx = 0.4 - pitch * i, x + 0.13
            if text == "Pareto front":
                key.plot([x, x + 0.26], [y, y], color=INK, lw=0.9)
                key.plot(hx, y, "o", ms=3.9, mfc=INK, mec=INK)
            elif text == "dominated type":
                key.plot(hx, y, "o", ms=2.8, mfc="white", mec=GREY, mew=0.6)
            elif text == "dominated region":
                key.add_patch(Rectangle((x + 0.01, y - 0.05), 0.24, 0.1, fc=SHADE, ec=RULE, lw=0.4))
            elif text == "ranker's top three":
                key.plot(hx, y, "o", ms=7.9, mfc="none", mec=ACCENT, mew=1.1)
            else:
                key.add_patch(FancyArrowPatch((x + 0.23, y + 0.055), (x + 0.03, y - 0.055), arrowstyle=ARROW,
                                              mutation_scale=8, lw=0.7, color=SOFT, shrinkA=0, shrinkB=0))
            key.text(x + handle, y, text, ha="left", va="center", fontsize=8)
        x += width + gutter
    save(fig, "fig_pareto")


def fig_results():
    """Figure 3: both exams as small multiples, each method's score with its 95% confidence interval."""
    parse = DATA["parse"]
    rank = [r for r in DATA["rank"] if r.get("pairs")]
    random_level = next(r["reference"] for r in DATA["rank"] if "reference" in r)

    def role(r):
        return "deployed" if r["deployed"] else "baseline" if r["method"] in BASELINES else "other"

    colors = {"deployed": ACCENT, "baseline": INK, "other": GREY}

    def span(cells, extra=()):
        lows = [c["low"] for c in cells] + list(extra)
        highs = [c["high"] for c in cells] + list(extra)
        return 5 * math.floor((min(lows) - 1) / 5), 5 * math.ceil((max(highs) + 1) / 5)

    W, H = 6.27, 1.62
    fig = plt.figure(figsize=(W, H))
    labels_a = [PARSE_NAMES[r["method"]] for r in parse]
    labels_b = [RANK_NAMES[r["method"]] for r in rank]
    lab_a = max(text_width(fig, s, fontsize=8.5, weight="bold") for s in labels_a) + 0.14
    lab_b = max(text_width(fig, s, fontsize=8.5, weight="bold") for s in labels_b) + 0.14
    bottom, top, inner, outer, right = 0.2, 0.25, 0.3, 0.3, 0.06
    panel = (W - lab_a - inner - outer - lab_b - right) / 3.3  # the ranking panel spans twice the range
    x_b = lab_a + 2 * panel + inner + outer
    x_c = x_b + lab_b
    panels = [  # (axes, rows, cell key, title)
        (axes_at(fig, lab_a, bottom, panel, H - bottom - top), parse, "clauses", "Clauses (%)"),
        (axes_at(fig, lab_a + panel + inner, bottom, panel, H - bottom - top), parse, "sentences",
         "Whole sentences (%)"),
        (axes_at(fig, x_c, bottom, W - right - x_c, H - bottom - top), rank, "pairs", "Pairs agreeing (%)"),
    ]
    for i, (ax, rows, key, title) in enumerate(panels):
        ys = list(range(len(rows)))[::-1]
        extra = [random_level] if key == "pairs" else []
        lo, hi = span([r[key] for r in rows], extra)
        ax.set(xlim=(lo, hi), ylim=(-0.6, ys[0] + (0.95 if key == "pairs" else 0.6)))
        ax.set_xticks(range(lo + (-lo) % 10, hi + 1, 10))
        ax.set_facecolor("none")
        ax.spines["left"].set_visible(False)
        ax.tick_params(axis="y", length=0, pad=5)
        ax.set_yticks(ys, [""] * len(ys))
        if i != 1:
            ax.set_yticklabels(labels_a if rows is parse else labels_b)
            for tick, r in zip(ax.get_yticklabels(), rows):
                tick.set_fontweight("bold" if r["deployed"] else "normal")
        ax.hlines(ys, lo, hi, color=FAINT, lw=0.5, zorder=0)
        base = next(r for r in rows if role(r) == "baseline")[key]["value"]
        ax.vlines(base, -0.5, ys[0] + 0.4, color=RULE, lw=0.6, ls=(0, (2, 2)), zorder=1)
        if key == "pairs":
            ax.vlines(random_level, -0.5, ys[0] + 0.4, color=SOFT, lw=0.7, ls=(0, (4, 2)), zorder=1)
            ax.text(random_level, ys[0] + 0.5, "random", ha="center", va="bottom", **NOTE)
        for r, y in zip(rows, ys):
            cell, c = r[key], colors[role(r)]
            ax.plot([cell["low"], cell["high"]], [y, y], color=c, lw=1.2, zorder=2)
            ax.plot(cell["value"], y, "o", ms=4.6, mfc=c, mec="white", mew=0.5, zorder=3)
        centre = inches(fig, ax, 0.5, 1, "axes")
        fig.text(centre[0], H - 0.03, title, ha="center", va="top", fontsize=8.5, transform=fig.dpi_scale_trans)

    # A light band behind each deployed row, from its name across its panels, as tall in both exams.
    half = 0.42 * (inches(fig, panels[0][0], 0, 1)[1] - inches(fig, panels[0][0], 0, 0)[1])
    for first, last, rows, x0 in ((panels[0][0], panels[1][0], parse, 0.0), (panels[2][0], panels[2][0], rank, x_b)):
        y = len(rows) - 1 - next(i for i, r in enumerate(rows) if r["deployed"])
        centre = inches(fig, first, 0, y)[1]
        x1 = inches(fig, last, 1, 0, "axes")[0]
        fig.patches.append(Rectangle((x0, centre - half), x1 - x0, 2 * half, transform=fig.dpi_scale_trans, fc=TINT,
                                     ec="none", zorder=-1))

    letter(fig, 0.0, H - 0.02, "a", "Parsing exam")
    letter(fig, x_b, H - 0.02, "b", "Ranking exam")
    handles = [Line2D([], [], ls="-", lw=1.2, marker="o", ms=4.6, mec="white", mew=0.5, color=colors[k], label=k)
               for k in ("deployed", "baseline")]
    fig.legend(handles=handles, loc="lower left", bbox_to_anchor=(0.0, 0.0), bbox_transform=fig.dpi_scale_trans,
               ncol=2, fontsize=8, frameon=False, handlelength=1.4, handletextpad=0.4, columnspacing=1.0,
               borderaxespad=0.02, borderpad=0)
    save(fig, "fig_results")


def fig_app():
    """Figure 4: the two screenshots side by side, unchanged, each in a hairline frame, letters at their left."""
    shots = [plt.imread(ROOT / "report/figures/app_read.png"), plt.imread(ROOT / "report/figures/app_picks.png")]
    W, mark, gap = 6.27, 0.17, 0.2
    h = (W - 2 * mark - gap - 0.02) / sum(s.shape[1] / s.shape[0] for s in shots)
    H = h + 0.02
    fig = plt.figure(figsize=(W, H))
    x = 0.0
    for shot, name in zip(shots, "ab"):
        w = h * shot.shape[1] / shot.shape[0]
        letter(fig, x, H - 0.01, name)
        ax = axes_at(fig, x + mark, 0.01, w, h)
        ax.imshow(shot, interpolation="none", aspect="auto")
        ax.set_axis_off()
        ax.add_patch(Rectangle((0, 0), 1, 1, transform=ax.transAxes, fill=False, ec=RULE, lw=0.5, clip_on=False))
        x += mark + w + gap
    save(fig, "fig_app")


def fig_appendix():
    """Figure 5: (a) how many types each exam student's front had; (b) the ranker's learning curve."""
    sizes = {int(k): v for k, v in DATA["front_sizes"].items()}
    n = len(DATA["students"])
    assert sum(sizes.values()) == n
    cmin = DATA["candidate_min"]
    W, H = 6.27, 2.05
    fig = plt.figure(figsize=(W, H))
    bottom, top = 0.4, 0.14

    a = axes_at(fig, 0.5, bottom, 2.4, H - bottom - top)
    xs = list(range(1, cmin + 1))
    counts = [sizes.get(x, 0) for x in xs]
    a.bar(xs, counts, width=0.68, color=GREY, zorder=2)
    for x, c in zip(xs, counts):
        if c:
            a.text(x, c + 1.5, str(c), ha="center", va="bottom", fontsize=8)
    ceiling = 10 * math.ceil(max(counts) * 1.15 / 10)
    a.vlines(cmin, 0, ceiling, color=INK, lw=0.8, ls=(0, (3, 2)), zorder=1)
    a.text(cmin - 0.3, ceiling * 0.98, "candidate list\nminimum", ha="right", va="top", linespacing=1.1, **NOTE)
    a.set(xlim=(0.4, cmin + 0.6), ylim=(0, ceiling))
    a.set_xticks(xs)
    a.tick_params(axis="x", length=0)
    a.set_yticks(range(0, ceiling + 1, 20))
    a.set_xlabel("Timetable types on the Pareto front")
    a.set_ylabel(f"Exam students (of {n})")

    curve = DATA["curve"]
    px = [c["personas"] for c in curve]
    acc = [c["accuracy"] for c in curve]
    sd = [c["sd"] for c in curve]
    b = axes_at(fig, 3.67, bottom, W - 3.67 - 0.08, H - bottom - top)
    b.fill_between(px, [m - s for m, s in zip(acc, sd)], [m + s for m, s in zip(acc, sd)], color=BAND, lw=0, zorder=1)
    b.plot(px, acc, color=ACCENT, lw=1.2, marker="o", ms=3.8, mec="white", mew=0.5, zorder=3)
    deployed = 60  # the deployed ranker was trained on 60 simulated students
    d = next(c for c in curve if c["personas"] == deployed)
    b.plot(deployed, d["accuracy"], "o", ms=8.5, mfc="none", mec=INK, mew=0.9, zorder=4)
    b.annotate("deployed", (deployed, d["accuracy"]), xytext=(0, -13), textcoords="offset points", ha="center",
               va="top", **NOTE)
    low = min(m - s for m, s in zip(acc, sd))
    high = max(m + s for m, s in zip(acc, sd))
    b.set(xlim=(0, max(px) + 6), ylim=(5 * math.floor((low - 1) / 5), 5 * math.ceil((high + 1) / 5)))
    b.set_xticks(range(0, max(px) + 1, 30))
    b.set_xlabel("Training personas")
    b.set_ylabel("Held-out agreement (%)")

    letter(fig, 0.0, H, "a")
    letter(fig, 3.2, H, "b")
    save(fig, "fig_appendix")


def main():
    PREVIEW.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        setup(Path(folder))
        for draw in (fig_pipeline, fig_pareto, fig_results, fig_app, fig_appendix):
            draw()
            print("drew", draw.__name__)


if __name__ == "__main__":
    main()
