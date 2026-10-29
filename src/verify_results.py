"""Independently reconstruct histories via SQL ranking and all integer scenario metrics."""

import argparse, csv, gzip, io, json, math
from fractions import Fraction as Q
from pathlib import Path
from verify_source import verify as verify_source


def expected_forecasts(db, phase, policies):
    start, end = (
        ("2024-07-01", "2024-10-01")
        if phase == "validation"
        else ("2024-10-01", "2025-01-01")
    )
    out = {}
    for policy in policies:
        baseline = policy["id"] == "previous_available_week"
        w = 28 if baseline else policy["window"]
        group = "dow" if baseline or policy["group"] == "weekday_hour" else "daytype"
        order = "h.ordinal DESC" if baseline else "h.n,h.ordinal"
        sql = f"""WITH ranked AS (
          SELECT t.day,t.zone,t.hour,t.n AS observed,h.n AS prediction,
          ROW_NUMBER() OVER (PARTITION BY t.day,t.zone,t.hour ORDER BY {order}) AS rank,
          COUNT(*) OVER (PARTITION BY t.day,t.zone,t.hour) AS history_n,
          MIN(h.day) OVER (PARTITION BY t.day,t.zone,t.hour) AS history_start,
          MAX(h.day) OVER (PARTITION BY t.day,t.zone,t.hour) AS history_end
          FROM source t JOIN source h ON h.zone=t.zone AND h.hour=t.hour AND h.ordinal<t.ordinal AND h.ordinal>=t.ordinal-? AND h.{group}=t.{group}
          WHERE t.scope='IN_SCOPE' AND h.scope='IN_SCOPE' AND t.day>=? AND t.day<?)
          SELECT * FROM ranked"""
        q = Q(1) if baseline else Q(policy["q"])
        for day, zone, hour, observed, prediction, rank, n, first, last in db.execute(
            sql, (w, start, end)
        ):
            target = (
                1
                if baseline
                else (q.numerator * n + q.denominator - 1) // q.denominator
            )
            if rank != target:
                continue
            assert baseline or n >= 3
            if baseline:
                n, first, last = 1, last, last
            out[policy["id"], day, zone, hour] = (
                observed,
                prediction,
                n,
                first,
                last,
                rank,
            )
    return out


def verify(root=".", phase="validation", results=None):
    root = Path(root)
    results = Path(results) if results else root / "results"
    source, db = verify_source(root)
    cfg = json.loads((root / "protocol.json").read_text(encoding="utf-8"))
    if phase == "validation":
        policies = [
            dict(id=f'{g}-w{w}-q{q.replace("/","_")}', group=g, window=w, q=q)
            for q in ["1/2", "3/4", "9/10"]
            for g in ["weekday_hour", "daytype_hour"]
            for w in [28, 56, 84]
        ]
    else:
        policies = json.loads((root / "SELECTION.json").read_text(encoding="utf-8"))[
            "selected_policies"
        ]
    policies = [*policies, dict(id="previous_available_week")]
    expected = expected_forecasts(db, phase, policies)
    rows = list(
        csv.DictReader(
            io.StringIO(
                gzip.decompress(
                    (results / (phase + "-predictions.csv.gz")).read_bytes()
                ).decode()
            )
        )
    )
    assert (
        len(rows)
        == len(expected)
        == len(policies) * (4416 if phase == "validation" else 4368)
    )
    checks = 0
    seen = set()
    db.execute(
        "CREATE TABLE predictions(policy TEXT,day TEXT,zone INT,hour INT,d INT,p INT,PRIMARY KEY(policy,day,zone,hour))"
    )
    for r in rows:
        key = (r["policy"], r["date"], int(r["zone"]), int(r["hour"]))
        assert key in expected and key not in seen
        seen.add(key)
        actual = (
            int(r["observed"]),
            int(r["prediction"]),
            int(r["history_n"]),
            r["history_start"],
            r["history_end"],
            int(r["order_rank"]),
        )
        assert actual == expected[key] and r["status"] == "OK"
        checks += 8
        assert r["history_end"] < r["date"]
        checks += 1
        db.execute(
            "INSERT INTO predictions VALUES (?,?,?,?,?,?)", (*key, actual[0], actual[1])
        )
    metrics = list(
        csv.DictReader(
            (results / (phase + "-metrics.csv")).open(encoding="utf-8", newline="")
        )
    )
    identities = set()
    primary = {}
    group_defs = {("all", "ALL", "ALL")}
    group_defs |= {("airport", "ALL", str(z)) for z in [132, 138]}
    months = (
        ["2024-07", "2024-08", "2024-09"]
        if phase == "validation"
        else ["2024-10", "2024-11", "2024-12"]
    )
    group_defs |= {("month", m, "ALL") for m in months}
    group_defs |= {("airport_month", m, str(z)) for m in months for z in [132, 138]}
    if phase == "held":
        group_defs |= {("stress_date", d, "ALL") for d in ["2024-11-28", "2024-12-25"]}
        (
            group_defs.add(("stress_combined", "STRESS", "ALL"))
            if phase == "held"
            else None
        )
    for r in metrics:
        identity = (
            r["policy"],
            r["scope"],
            r["period"],
            r["zone"],
            int(r["cap"]),
            int(r["under_cost"]),
        )
        assert identity not in identities
        identities.add(identity)
        assert (
            (r["scope"], r["period"], r["zone"]) in group_defs
            and int(r["cap"]) in [100, 250, 500]
            and int(r["under_cost"]) in [1, 3, 9]
        )
        where = ["policy=?"]
        params = [r["policy"]]
        if r["zone"] != "ALL":
            where.append("zone=?")
            params.append(int(r["zone"]))
        if r["scope"] in ["month", "airport_month"]:
            where.append("substr(day,1,7)=?")
            params.append(r["period"])
        if r["scope"] == "stress_date":
            where.append("day=?")
            params.append(r["period"])
        if r["scope"] == "stress_combined":
            where.append("day IN ('2024-11-28','2024-12-25')")
        data = db.execute(
            "SELECT d,p FROM predictions WHERE " + " AND ".join(where), params
        ).fetchall()
        assert data
        cap, under = int(r["cap"]), int(r["under_cost"])
        n = len(data)
        sa = sum(abs(p - d) for d, p in data)
        ss = sum((p - d) ** 2 for d, p in data)
        observed = sum(d for d, p in data)
        unmet = sum(max(d - min(p, cap), 0) for d, p in data)
        excess = sum(max(min(p, cap) - d, 0) for d, p in data)
        raw_exceed = sum(d > p for d, p in data)
        shortage = sum(d > min(p, cap) for d, p in data)
        slots = sum(min(p, cap) for d, p in data)
        cost = under * unmet + excess
        numeric = dict(
            n=n,
            observed=observed,
            raw_abs_error=sa,
            raw_squared_error=ss,
            raw_exceed_hours=raw_exceed,
            capacity_slots=slots,
            unmet=unmet,
            excess=excess,
            served=observed - unmet,
            shortage_hours=shortage,
            cost=cost,
        )
        for k, v in numeric.items():
            assert int(r[k]) == v, (identity, k)
            checks += 1
        exact = dict(
            mae_exact=Q(sa, n),
            mse_exact=Q(ss, n),
            raw_exceed_fraction=Q(raw_exceed, n),
            shortage_fraction=Q(shortage, n),
            mean_cost_exact=Q(cost, n),
        )
        for k, v in exact.items():
            assert Q(r[k]) == v, (identity, k)
            checks += 1
        assert math.isclose(
            float(r["rmse"]), math.sqrt(ss / n), rel_tol=0, abs_tol=1e-12
        )
        checks += 1
        if r["scope"] == "all" and cap == 250 and under == 3:
            primary[r["policy"]] = cost
    assert len(identities) == len(policies) * len(group_defs) * 9
    selection = json.loads((root / "SELECTION.json").read_text(encoding="utf-8"))
    if phase == "validation":

        def order(p):
            return (
                primary[p["id"]],
                0 if p["group"] == "daytype_hour" else 1,
                p["window"],
                Q(p["q"]),
            )

        chosen = [
            min([p for p in policies[:-1] if p["q"] == q], key=order)
            for q in ["1/2", "3/4", "9/10"]
        ]
        assert (
            selection["selected_policies"] == chosen
            and selection["primary_winner"] == min(chosen, key=order)["id"]
        )
        checks += 4
        assert selection["candidate_primary_costs"] == primary
        checks += len(primary)
    else:
        winner = selection["primary_winner"]
        median = next(
            p["id"] for p in selection["selected_policies"] if p["q"] == "1/2"
        )
        pairs = list(
            csv.DictReader(
                (results / "held-temporal-sensitivity.csv").open(
                    encoding="utf-8", newline=""
                )
            )
        )
        assert len(pairs) == 6
        for r in pairs:
            op = "=" if r["kind"] == "month" else "!="
            a = db.execute(
                f"SELECT d,p FROM predictions WHERE policy=? AND substr(day,1,7){op}?",
                (winner, r["period"]),
            ).fetchall()
            b = db.execute(
                f"SELECT d,p FROM predictions WHERE policy=? AND substr(day,1,7){op}?",
                (median, r["period"]),
            ).fetchall()

            def total(rr):
                return sum(
                    3 * max(d - min(p, 250), 0) + max(min(p, 250) - d, 0) for d, p in rr
                )

            delta = total(a) - total(b)
            assert (
                len(a) == len(b) == int(r["n"])
                and int(r["cost_difference"]) == delta
                and Q(r["mean_difference_exact"]) == Q(delta, len(a))
            )
            checks += 3
    return dict(
        status="PASS",
        phase=phase,
        policies=len(policies),
        prediction_rows=len(rows),
        scenario_metric_rows=len(metrics),
        exact_and_tolerance_checks=checks,
        source_grid_checks=source["source_grid_checks"],
        availability="Past-only date indices checked under fixed idealized prior-day availability; actual historical vintages and prospective telemetry not established.",
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("phase", choices=["validation", "held"])
    p.add_argument("--output")
    a = p.parse_args()
    result = verify(phase=a.phase)
    if a.output:
        Path(a.output).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
