"""Original figures of conditional costs; no queue, money or real-time claim."""

import csv, hashlib, json
from fractions import Fraction as Q
from pathlib import Path
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

IDS = [
    "previous_available_week",
    "weekday_hour-w84-q1_2",
    "weekday_hour-w84-q3_4",
    "weekday_hour-w84-q9_10",
]
LABELS = ["Prior weekday", "Median", "75th percentile", "90th percentile"]
COLORS = ["#666666", "#176888", "#ad5b26", "#647d35"]


def data(root):
    return list(
        csv.DictReader(
            (Path(root) / "results/held-metrics.csv").open(encoding="utf-8", newline="")
        )
    )


def build(root="."):
    rows = data(root)
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "pdf.fonttype": 42,
            "svg.fonttype": "none",
        }
    )
    primary = {
        (r["policy"], r["zone"]): r
        for r in rows
        if r["scope"] == "airport" and r["cap"] == "250" and r["under_cost"] == "3"
    }
    figs = {}
    artists = {}
    fig, axes = plt.subplots(1, 2, figsize=(9, 4.4))
    points = []
    for ax, z, title in zip(
        axes, ["132", "138"], ["JFK airport zone", "LaGuardia airport zone"]
    ):
        for policy, label, color, marker in zip(
            IDS, LABELS, COLORS, ["s", "o", "D", "^"]
        ):
            r = primary[policy, z]
            n = int(r["n"])
            x = int(r["unmet"]) / n
            y = int(r["excess"]) / n
            art = ax.scatter(
                [x], [y], s=65, color=color, marker=marker, label=label, zorder=3
            )
            points.append((policy, z, art))
        ax.set_title(title, loc="left", fontweight="bold")
        ax.set_xlim(left=0)
        ax.set_ylim(bottom=0)
        ax.grid(alpha=0.15)
        ax.set_xlabel("Unmet recorded services per hour")
    axes[0].set_ylabel("Excess hypothetical capacity per hour")
    fig.legend(
        *axes[1].get_legend_handles_labels(),
        frameon=False,
        fontsize=9,
        loc="lower center",
        ncol=4,
        bbox_to_anchor=(0.5, 0.065),
    )
    fig.suptitle(
        "Higher quantiles exchange unmet records for excess capacity",
        x=0.07,
        ha="left",
        fontsize=13,
        fontweight="bold",
    )
    fig.text(
        0.03,
        0.015,
        "Held retrospective simulation | cap 250 services/hour, underage cost 3, excess cost 1 | no physical queue model",
        fontsize=8,
    )
    fig.tight_layout(rect=[0, 0.16, 1, 0.92])
    figs["capacity_tradeoff"] = fig
    artists["capacity_tradeoff"] = points
    fig, ax = plt.subplots(figsize=(8.5, 4.5))
    bars = []
    months = ["2024-10", "2024-11", "2024-12"]
    x = np.arange(3)
    for i, (policy, label, color) in enumerate(zip(IDS, LABELS, COLORS)):
        values = [
            float(
                Q(
                    next(
                        r["mean_cost_exact"]
                        for r in rows
                        if r["policy"] == policy
                        and r["scope"] == "month"
                        and r["period"] == m
                        and r["cap"] == "250"
                        and r["under_cost"] == "3"
                    )
                )
            )
            for m in months
        ]
        container = ax.bar(
            x + (i - 1.5) * 0.19, values, width=0.18, color=color, label=label
        )
        bars.append((policy, container))
    ax.set_xticks(x, ["October", "November", "December"])
    ax.set_ylim(bottom=0)
    ax.set_ylabel("Modeled cost units per retained zone-hour")
    ax.set_title(
        "Primary cost comparison retains every held month",
        loc="left",
        fontweight="bold",
        pad=15,
    )
    ax.grid(axis="y", alpha=0.15)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, ncol=2, fontsize=9)
    fig.text(
        0.03,
        0.015,
        "Same hypothetical cap/cost setting; source vintages and real-time dispatcher availability are not validated.",
        fontsize=8,
    )
    fig.tight_layout(rect=[0, 0.05, 1, 1])
    figs["monthly_costs"] = fig
    artists["monthly_costs"] = bars
    fig, ax = plt.subplots(figsize=(7.8, 4.7))
    matrix = []
    for under in [1, 3, 9]:
        line = []
        for cap in [100, 250, 500]:
            a = next(
                r
                for r in rows
                if r["policy"] == IDS[2]
                and r["scope"] == "all"
                and int(r["cap"]) == cap
                and int(r["under_cost"]) == under
            )
            b = next(
                r
                for r in rows
                if r["policy"] == IDS[1]
                and r["scope"] == "all"
                and int(r["cap"]) == cap
                and int(r["under_cost"]) == under
            )
            line.append(float(Q(a["mean_cost_exact"]) - Q(b["mean_cost_exact"])))
        matrix.append(line)
    array = np.array(matrix)
    bound = max(abs(array.min()), abs(array.max()))
    im = ax.imshow(array, cmap="RdBu_r", vmin=-bound, vmax=bound, aspect="auto")
    texts = []
    for i in range(3):
        for j in range(3):
            rgb = im.cmap(im.norm(array[i, j]))[:3]
            linear = [
                v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb
            ]
            lum = sum(a * b for a, b in zip(linear, [0.2126, 0.7152, 0.0722]))
            white = 1.05 / (lum + 0.05)
            black = (lum + 0.05) / 0.05
            texts.append(
                ax.text(
                    j,
                    i,
                    f"{array[i,j]:+.2f}",
                    ha="center",
                    va="center",
                    color="white" if white >= black else "black",
                    fontsize=12,
                )
            )
    ax.set_xticks(range(3), [100, 250, 500])
    ax.set_yticks(range(3), [1, 3, 9])
    ax.set_xlabel("Hypothetical service cap per zone-hour")
    ax.set_ylabel("Underage cost (excess cost = 1)")
    ax.set_title(
        "The cost assumptions change the policy comparison",
        loc="left",
        fontweight="bold",
        pad=15,
    )
    fig.colorbar(im, ax=ax, label="75th minus median modeled cost units / hour")
    fig.text(
        0.03,
        0.015,
        "Negative values favor the frozen 75th-percentile policy. Neither policy is reselected for these sensitivities.",
        fontsize=8,
    )
    fig.tight_layout(rect=[0, 0.06, 1, 1])
    figs["cost_assumptions"] = fig
    artists["cost_assumptions"] = (im, texts)
    return figs, artists


def main():
    root = Path(__file__).resolve().parents[1]
    out = root / "figures"
    out.mkdir(exist_ok=True)
    figs, _ = build(root)
    hashes = {}
    for name, fig in figs.items():
        for suffix in ["pdf", "svg", "png"]:
            p = out / (name + "." + suffix)
            fig.savefig(p, dpi=160, bbox_inches="tight")
            if suffix == "svg":
                p.write_bytes(
                    (
                        "\n".join(
                            line.rstrip()
                            for line in p.read_text(encoding="utf-8").splitlines()
                        )
                        + "\n"
                    ).encode()
                )
            hashes[p.relative_to(root).as_posix()] = hashlib.sha256(
                p.read_bytes()
            ).hexdigest()
        plt.close(fig)
    (out / "MANIFEST.json").write_text(
        json.dumps(hashes, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(dict(original_figures=3, exports=9)))


if __name__ == "__main__":
    main()
