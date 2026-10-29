"""Recompute displayed results and verify scoped manuscript bytes and PDF actions."""

import csv
import hashlib
import json
import re
import unicodedata
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction as Q
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]


def display(value, places=3):
    value = Q(value)
    with localcontext() as context:
        context.prec = 60
        number = (Decimal(value.numerator) / Decimal(value.denominator)).quantize(
            Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN
        )
        return format(number, ",." + str(places) + "f")


def verify():
    tex = (ROOT / "paper/main.tex").read_text(encoding="utf-8")
    summary = (ROOT / "DECISION_SUMMARY.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    with (ROOT / "results/held-metrics.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        rows = list(csv.DictReader(stream))
    primary = [
        row
        for row in rows
        if row["scope"] in {"airport", "all"}
        and row["cap"] == "250"
        and row["under_cost"] == "3"
    ]
    assert len(primary) == 12
    checks = 1
    names = {
        "previous_available_week": "Prior weekday",
        "weekday_hour-w84-q1_2": "Median",
        "weekday_hour-w84-q3_4": "75th percentile",
        "weekday_hour-w84-q9_10": "90th percentile",
    }
    zones = {"132": "JFK", "138": "LGA", "ALL": "Pooled"}
    pooled = {}
    for row in primary:
        fields = [
            zones[row["zone"]],
            names[row["policy"]],
            display(row["mae_exact"]),
            format(int(row["unmet"]), ","),
            format(int(row["excess"]), ","),
            display(row["mean_cost_exact"]),
        ]
        assert " & ".join(fields) + " " + chr(92) * 2 in tex, fields
        assert "| " + " | ".join(fields) + " |" in summary, fields
        assert int(row["n"]) == (4368 if row["zone"] == "ALL" else 2184)
        assert int(row["cost"]) == 3 * int(row["unmet"]) + int(row["excess"])
        checks += 14
        if row["zone"] == "ALL":
            pooled[names[row["policy"]]] = row
    median, winner = pooled["Median"], pooled["75th percentile"]
    difference = int(median["cost"]) - int(winner["cost"])
    assert difference == 29851
    assert display(100 * Q(difference, int(median["cost"])), 1) == "4.5"
    assert Q(winner["mae_exact"]) > Q(median["mae_exact"])
    checks += 3
    for row in (median, winner):
        for key in ["unmet", "excess", "cost"]:
            shown = format(int(row[key]), ",")
            assert shown in tex and shown in summary
            checks += 2
        assert display(row["mae_exact"]) in tex and display(row["mae_exact"]) in summary
        checks += 2
    stress = [
        row
        for row in rows
        if row["scope"] == "stress_combined"
        and row["cap"] == "250"
        and row["under_cost"] == "3"
    ]
    assert len(stress) == 4
    checks += 1
    stress_cost = {}
    for row in stress:
        fields = [
            names[row["policy"]],
            *[format(int(row[key]), ",") for key in ["unmet", "excess", "cost"]],
        ]
        assert " & ".join(fields) + " " + chr(92) * 2 in tex, fields
        assert int(row["n"]) == 96
        assert int(row["cost"]) == 3 * int(row["unmet"]) + int(row["excess"])
        stress_cost[names[row["policy"]]] = int(row["cost"])
        checks += 6
    stress_difference = stress_cost["75th percentile"] - stress_cost["Median"]
    assert stress_difference == 1067
    assert display(100 * Q(stress_difference, stress_cost["Median"]), 1) == "15.1"
    checks += 2
    for cap in ["100", "250", "500"]:
        subset = {
            names[row["policy"]]: int(row["cost"])
            for row in rows
            if row["scope"] == "all" and row["cap"] == cap and row["under_cost"] == "1"
        }
        assert subset["75th percentile"] > subset["Median"]
        checks += 1
    expected_month = {"2024-10": -12409, "2024-11": -6080, "2024-12": -11362}
    for month, expected in expected_month.items():
        costs = {
            names[row["policy"]]: int(row["cost"])
            for row in rows
            if row["scope"] == "month"
            and row["period"] == month
            and row["cap"] == "250"
            and row["under_cost"] == "3"
        }
        assert costs["75th percentile"] - costs["Median"] == expected
        assert format(expected, ",") in tex
        checks += 2
    source = json.loads(
        (ROOT / "data/source/VERIFICATION.json").read_text(encoding="utf-8")
    )
    for key in [
        "source_records",
        "grid_rows",
        "excluded_dst_records",
        "source_grid_checks",
    ]:
        assert format(source[key], ",") in tex
        checks += 1
    freeze = json.loads((ROOT / "FREEZE.json").read_text(encoding="utf-8"))
    replay = json.loads((ROOT / "REPRODUCTION_CHECK.json").read_text(encoding="utf-8"))
    assert len(freeze["dependencies"]) == replay["protected_dependencies"] == 21
    assert replay["exact_csv_fields_and_selection_documents"] == 1177457
    checks += 2
    for phrase in [
        "idealized prior-day availability assumption",
        "not peer reviewed",
        "no genuine prospective availability clearance",
        "no future target date",
        "neither operational readiness nor realized savings",
        "15.1\\% higher",
        "two named days",
        "not a confidence interval",
        "source minimization correction",
        "initial all-city quality query included exact minimum/maximum timestamp extrema",
        "that response remains private",
        "corrected diagnostics use day-only extrema",
        "individual trip rows",
        "1,177,457",
        "956,489",
        "578",
        "4,368",
        "Square-root RMSE checks use absolute tolerance",
        "one service per vehicle-hour",
        "Formal-publication projects, including Azure optimization, remain private",
    ]:
        assert phrase.lower() in tex.lower(), phrase
        checks += 1
    for document in [summary, readme]:
        for phrase in ["4.5%", "15.1%", "idealized", "real-time", "private"]:
            assert phrase in document, phrase
            checks += 1
    scope = json.loads(
        (ROOT / "paper/PUBLICATION_SCOPE.json").read_text(encoding="utf-8")
    )
    assert (
        scope["scope"] == "independent-program-study"
        and scope["formal_submission_target"] is False
    )
    assert len(scope["public_files"]) == 5
    checks += 3
    for name, digest in scope["public_files"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
        checks += 1
    reader = PdfReader(ROOT / "paper/manuscript.pdf")
    assert len(reader.pages) == 5
    checks += 1
    normal = re.sub(
        r"\s+",
        " ",
        unicodedata.normalize(
            "NFKC", " ".join(page.extract_text() for page in reader.pages)
        ),
    )
    for phrase in [
        "Decision brief",
        "633,760",
        "663,611",
        "8,153",
        "7,086",
        "1,177,457",
        "956,489",
        "not peer reviewed",
        "Reproduction",
        "Source minimization correction",
    ]:
        assert phrase.lower() in normal.lower(), phrase
        checks += 1
    for command in [
        "python -m pip install -r requirements.txt",
        "python -m unittest discover -s tests -v",
        "python src/check_reproduction.py",
        "python src/verify_figures.py",
        "python src/verify_paper.py",
        "python src/verify_public_package.py",
    ]:
        assert command in normal, command
        checks += 1
    forbidden = [
        "/JavaScript",
        "/JS",
        "/Launch",
        "/EmbeddedFiles",
        "/RichMedia",
        "/AcroForm",
        "/AA",
    ]
    pdfs = [
        ROOT / "paper/manuscript.pdf",
        *sorted((ROOT / "paper/images").glob("*.pdf")),
    ]
    assert len(pdfs) == 4
    for path in pdfs:
        doc = PdfReader(path)
        catalog = doc.trailer["/Root"]
        assert not any(key in catalog for key in forbidden)
        assert "/EmbeddedFiles" not in catalog.get("/Names", {})
        action = catalog.get("/OpenAction")
        if hasattr(action, "get"):
            assert action.get("/S") not in ["/JavaScript", "/Launch"]
        for page in doc.pages:
            assert not any(key in page for key in forbidden)
            for annotation in page.get("/Annots", []):
                item = annotation.get_object()
                assert not any(key in item for key in ["/AA", "/RichMedia"])
                if "/A" in item:
                    assert item["/A"].get("/S") == "/URI"
        checks += 1
    return dict(
        status="PASS",
        independent_paper_checks=checks,
        displayed_primary_rows=12,
        displayed_stress_rows=4,
        pdf_pages=5,
        pdf_active_content_checks=len(pdfs),
        scope="Bounded numeric, claim, approved-hash and action checks; source rights and rendered-page review recorded separately.",
    )


if __name__ == "__main__":
    result = verify()
    (ROOT / "paper/VERIFICATION.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result))
