import csv, hashlib, json, math
from fractions import Fraction as Q
from pathlib import Path
import matplotlib.pyplot as plt
from make_figures import build


def verify():
    root = Path(__file__).resolve().parents[1]
    rows = list(
        csv.DictReader(
            (root / "results/held-metrics.csv").open(encoding="utf-8", newline="")
        )
    )
    figs, artists = build(root)
    checks = 0
    for policy, z, artist in artists["capacity_tradeoff"]:
        r = next(
            r
            for r in rows
            if r["policy"] == policy
            and r["scope"] == "airport"
            and r["zone"] == z
            and r["cap"] == "250"
            and r["under_cost"] == "3"
        )
        expected = [int(r["unmet"]) / int(r["n"]), int(r["excess"]) / int(r["n"])]
        for a, b in zip(artist.get_offsets()[0], expected):
            assert math.isclose(float(a), b, rel_tol=0, abs_tol=1e-12)
            checks += 1
    for policy, bars in artists["monthly_costs"]:
        for bar, month in zip(bars, ["2024-10", "2024-11", "2024-12"]):
            r = next(
                r
                for r in rows
                if r["policy"] == policy
                and r["scope"] == "month"
                and r["period"] == month
                and r["cap"] == "250"
                and r["under_cost"] == "3"
            )
            assert math.isclose(
                bar.get_height(),
                float(Q(r["mean_cost_exact"])),
                rel_tol=0,
                abs_tol=1e-12,
            )
            checks += 1
    image, texts = artists["cost_assumptions"]
    contrast_checks = 0
    for i, under in enumerate([1, 3, 9]):
        for j, cap in enumerate([100, 250, 500]):
            a = next(
                r
                for r in rows
                if r["policy"] == "weekday_hour-w84-q3_4"
                and r["scope"] == "all"
                and int(r["cap"]) == cap
                and int(r["under_cost"]) == under
            )
            b = next(
                r
                for r in rows
                if r["policy"] == "weekday_hour-w84-q1_2"
                and r["scope"] == "all"
                and int(r["cap"]) == cap
                and int(r["under_cost"]) == under
            )
            value = float(Q(a["mean_cost_exact"]) - Q(b["mean_cost_exact"]))
            assert math.isclose(
                float(image.get_array()[i, j]), value, rel_tol=0, abs_tol=1e-12
            )
            checks += 1
            t = texts[3 * i + j]
            assert t.get_text() == f"{value:+.2f}" and t.get_position() == (j, i)
            rgb = image.cmap(image.norm(value))[:3]
            linear = [
                v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb
            ]
            lum = sum(a * b for a, b in zip(linear, [0.2126, 0.7152, 0.0722]))
            ratio = (
                1.05 / (lum + 0.05) if t.get_color() == "white" else (lum + 0.05) / 0.05
            )
            assert ratio >= 4.5
            contrast_checks += 1
    for name, digest in json.loads(
        (root / "figures/MANIFEST.json").read_text(encoding="utf-8")
    ).items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
    for fig in figs.values():
        plt.close(fig)
    return dict(
        status="PASS",
        actual_artist_values=checks,
        annotation_and_contrast_checks=contrast_checks,
        export_hashes=9,
    )


if __name__ == "__main__":
    result = verify()
    Path("figures/VERIFICATION.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result))
