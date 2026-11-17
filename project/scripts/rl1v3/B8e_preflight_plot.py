#!/usr/bin/env python3
"""Plot B8e-preflight learning curves (dev greedy return) from curves.jsonl.

Left: supervised epochs (OneShot, Seq-BC, Seq-BC-NoText). Right: PPO rounds
(PPO from Seq-BC, PPO-NoText from Seq-BC-NoText, PPO-scratch). Thin lines are
the three seeds, the thick line their mean. Dashed references: Bayes-optimal
(observation-limited optimum), Fixed-best and OFF on the same dev set.
Requires matplotlib (run with the report environment).
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e0"
COLOR = {"OneShot": "#eda100", "Seq-BC": "#e87ba4", "Seq-BC-NoText": "#008300",
         "PPO": "#2a78d6", "PPO-NoText": "#eb6834", "PPO-scratch": "#1baf7a"}


def main(out: Path) -> None:
    summary = json.loads((out / "summary.json").read_text())
    seeds = sorted(int(p.name.split("_")[1]) for p in out.glob("seed_*") if p.is_dir())
    curves = defaultdict(lambda: defaultdict(dict))
    for s in seeds:
        for line in (out / f"seed_{s}" / "curves.jsonl").open():
            r = json.loads(line)
            if "dev_return" in r and r["method"] in COLOR:
                x = r.get("epoch", r.get("round"))
                curves[r["method"]][s][x] = r["dev_return"]
    ref = summary["references"]["sets"]["dev"]
    refs = [("Bayes-optimal (observation-limited optimum)", ref["Bayes-optimal"]["mean_return"],
             (0, (5, 3)))]
    below = (f"OFF {ref['OFF']['mean_return']:.3f} and Fixed-best "
             f"{ref['Fixed-best']['mean_return']:.3f} lie below the axis; epoch-1 points clipped")
    ylo, yhi = 0.595, 0.652
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                         "xtick.color": INK2, "ytick.color": INK2, "text.color": INK})
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), facecolor=SURFACE, sharey=True)
    panels = [("Supervised (epoch)", ("OneShot", "Seq-BC", "Seq-BC-NoText")),
              ("PPO (round of 2,048 env steps)", ("PPO", "PPO-NoText", "PPO-scratch"))]
    for ax, (title, methods) in zip(axes, panels):
        ax.set_facecolor(SURFACE)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        xmax, ends = 0, []
        for m in methods:
            per = curves[m]
            xs = sorted(set.intersection(*(set(per[s]) for s in seeds)))
            for s in seeds:
                ax.plot(xs, [per[s][x] for x in xs], color=COLOR[m], lw=0.8, alpha=0.35)
            mean = [sum(per[s][x] for s in seeds) / len(seeds) for x in xs]
            ax.plot(xs, mean, color=COLOR[m], lw=2.0, label=f"{m} (mean of {len(seeds)} seeds)")
            ends.append([mean[-1], m, xs[-1]])
            xmax = max(xmax, xs[-1])
        ends.sort()
        gap = (yhi - ylo) * 0.045
        for k in range(1, len(ends)):
            ends[k][0] = max(ends[k][0], ends[k - 1][0] + gap)
        for y, m, x in ends:
            ax.annotate(m, (x, y), xytext=(5, 0), textcoords="offset points",
                        va="center", fontsize=8, color=INK)
        for name, y, ls in refs:
            ax.axhline(y, color=INK2, lw=1.0, ls=ls)
            ax.annotate(f"{name} {y:.3f}", (0, y), xytext=(2, 3), textcoords="offset points",
                        fontsize=7.5, color=INK2, xycoords=("axes fraction", "data"))
        ax.set_xlim(0, xmax * 1.22)
        ax.set_ylim(ylo, yhi)
        ax.set_title(title, fontsize=10, color=INK, loc="left")
        ax.legend(loc="lower right", frameon=False, fontsize=7.5)
        ax.text(0.01, 0.01, below, transform=ax.transAxes, fontsize=7, color=INK2)
    axes[0].set_ylabel("dev greedy return (synthetic task)")
    fig.suptitle("B8e-preflight learning curves - engineering_only, synthetic programmatic task",
                 fontsize=10.5, x=0.01, ha="left", color=INK)
    fig.tight_layout()
    fig.savefig(out / "learning_curves.png", dpi=150, facecolor=SURFACE)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
