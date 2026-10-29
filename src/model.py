"""Finite retrospective count-policy comparison with explicit scenario assumptions."""

import csv, gzip, io, json, math, time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from fractions import Fraction as Q
from pathlib import Path


def facts(root):
    rows = list(
        csv.DictReader(
            io.StringIO(
                gzip.decompress(
                    (Path(root) / "data/source/hourly_counts.csv.gz").read_bytes()
                ).decode()
            )
        )
    )
    return {
        (date.fromisoformat(r["date"]), int(r["zone"]), int(r["hour"])): int(
            r["published_records"]
        )
        for r in rows
        if r["scope"] == "IN_SCOPE"
    }


def empirical(values, q):
    rank = (q.numerator * len(values) + q.denominator - 1) // q.denominator
    return sorted(values)[rank - 1], rank


def history(data, target, zone, hour, window, group):
    out = []
    for offset in range(1, window + 1):
        d = target - timedelta(days=offset)
        same = (
            d.weekday() == target.weekday()
            if group == "weekday_hour"
            else (d.weekday() >= 5) == (target.weekday() >= 5)
        )
        if same and (d, zone, hour) in data:
            out.append((d, data[d, zone, hour]))
    return sorted(out)


def predict(data, target, zone, hour, policy):
    if policy["id"] == "previous_available_week":
        h = history(data, target, zone, hour, 28, "weekday_hour")
        if not h:
            return None, [], "NO_BASELINE_HISTORY", None
        h = h[-1:]
        return h[0][1], h, "OK", 1
    h = history(data, target, zone, hour, policy["window"], policy["group"])
    if len(h) < 3:
        return None, h, "INSUFFICIENT_HISTORY", None
    value, rank = empirical([n for d, n in h], Q(policy["q"]))
    return value, h, "OK", rank


def candidates(cfg):
    out = []
    for q in cfg["quantiles"]:
        for group in cfg["calendar_groups"]:
            for w in cfg["windows_days"]:
                out.append(
                    dict(
                        id=f'{group}-w{w}-q{q.replace("/","_")}',
                        group=group,
                        window=w,
                        q=q,
                    )
                )
    return out


def scenario(d, p, cap, under):
    a = min(p, cap)
    unmet = max(d - a, 0)
    excess = max(a - d, 0)
    return a, unmet, excess, under * unmet + excess


def groups(row, phase, cfg):
    d = row["date"]
    z = str(row["zone"])
    m = d[:7]
    out = [
        ("all", "ALL", "ALL"),
        ("airport", "ALL", z),
        ("month", m, "ALL"),
        ("airport_month", m, z),
    ]
    if phase == "held" and d in cfg["stress_dates"]:
        out += [("stress_date", d, "ALL"), ("stress_combined", "STRESS", "ALL")]
    return out


def metrics(predictions, phase, cfg):
    bags = defaultdict(list)
    for r in predictions:
        for scope, period, zone in groups(r, phase, cfg):
            bags[r["policy"], scope, period, zone].append(r)
    out = []
    for (policy, scope, period, zone), rr in sorted(bags.items()):
        assert all(r["status"] == "OK" for r in rr)
        n = len(rr)
        sa = sum(abs(r["prediction"] - r["observed"]) for r in rr)
        ss = sum((r["prediction"] - r["observed"]) ** 2 for r in rr)
        exceed = sum(r["observed"] > r["prediction"] for r in rr)
        for cap in cfg["capacity_caps"]:
            for under in cfg["underage_costs"]:
                values = [
                    scenario(r["observed"], r["prediction"], cap, under) for r in rr
                ]
                slots = sum(v[0] for v in values)
                unmet = sum(v[1] for v in values)
                excess = sum(v[2] for v in values)
                cost = sum(v[3] for v in values)
                shortage = sum(v[1] > 0 for v in values)
                observed = sum(r["observed"] for r in rr)
                out.append(
                    dict(
                        phase=phase,
                        policy=policy,
                        scope=scope,
                        period=period,
                        zone=zone,
                        cap=cap,
                        under_cost=under,
                        n=n,
                        observed=observed,
                        raw_abs_error=sa,
                        raw_squared_error=ss,
                        mae_exact=str(Q(sa, n)),
                        mse_exact=str(Q(ss, n)),
                        rmse=math.sqrt(ss / n),
                        raw_exceed_hours=exceed,
                        raw_exceed_fraction=str(Q(exceed, n)),
                        capacity_slots=slots,
                        unmet=unmet,
                        excess=excess,
                        served=observed - unmet,
                        shortage_hours=shortage,
                        shortage_fraction=str(Q(shortage, n)),
                        cost=cost,
                        mean_cost_exact=str(Q(cost, n)),
                    )
                )
    return out


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def tie_key(policy, cost):
    return (
        cost,
        0 if policy["group"] == "daytype_hour" else 1,
        policy["window"],
        Q(policy["q"]),
    )


def run(root=".", phase="validation", output="results"):
    root = Path(root)
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    cfg = json.loads((root / "protocol.json").read_text(encoding="utf-8"))
    data = facts(root)
    if phase == "held":
        from verify_freeze import verify

        verify(root)
        selection = json.loads((root / "SELECTION.json").read_text(encoding="utf-8"))
        policies = selection["selected_policies"]
    else:
        policies = candidates(cfg)
    policies = [*policies, dict(id="previous_available_week")]
    predictions = []
    execution = []
    start = date.fromisoformat(
        cfg["validation_start"] if phase == "validation" else cfg["held_start"]
    )
    stop = date.fromisoformat(
        cfg["held_start"] if phase == "validation" else cfg["end_exclusive"]
    )
    targets = sorted((d, z, h) for d, z, h in data if start <= d < stop)
    expected = 4416 if phase == "validation" else 4368
    assert len(targets) == expected
    for policy in policies:
        clock = time.perf_counter()
        begun = datetime.now(timezone.utc).isoformat()
        for target, zone, hour in targets:
            value, h, status, rank = predict(data, target, zone, hour, policy)
            predictions.append(
                dict(
                    policy=policy["id"],
                    date=target.isoformat(),
                    zone=zone,
                    hour=hour,
                    observed=data[target, zone, hour],
                    prediction=value,
                    status=status,
                    history_n=len(h),
                    history_start=h[0][0].isoformat() if h else "",
                    history_end=h[-1][0].isoformat() if h else "",
                    order_rank=rank,
                )
            )
        execution.append(
            dict(
                policy=policy["id"],
                started_utc=begun,
                elapsed_seconds=time.perf_counter() - clock,
                status="COMPUTED",
                seed=None,
            )
        )
    assert all(r["status"] == "OK" for r in predictions)
    buffer = io.StringIO(newline="")
    w = csv.DictWriter(buffer, fieldnames=list(predictions[0]), lineterminator="\n")
    w.writeheader()
    w.writerows(predictions)
    (out / (phase + "-predictions.csv.gz")).write_bytes(
        gzip.compress(buffer.getvalue().encode(), mtime=0)
    )
    scores = metrics(predictions, phase, cfg)
    write_csv(out / (phase + "-metrics.csv"), scores)
    (out / (phase + "-execution.json")).write_text(
        json.dumps(execution, indent=2) + "\n", encoding="utf-8"
    )
    if phase == "validation":
        costs = {
            r["policy"]: r["cost"]
            for r in scores
            if r["scope"] == "all"
            and r["cap"] == cfg["primary_capacity_cap"]
            and r["under_cost"] == cfg["primary_underage_cost"]
        }
        pool = candidates(cfg)
        chosen = [
            min(
                (p for p in pool if p["q"] == q),
                key=lambda p: tie_key(p, costs[p["id"]]),
            )
            for q in cfg["quantiles"]
        ]
        winner = min(chosen, key=lambda p: tie_key(p, costs[p["id"]]))
        selection = dict(
            primary_winner=winner["id"],
            selected_policies=chosen,
            primary_cap=250,
            primary_under_cost=3,
            validation_targets_per_policy=expected,
            candidate_primary_costs=costs,
            selection="Fixed exact pooled validation cost and declared tie order; no held summaries used.",
        )
        (root / "SELECTION.json").write_text(
            json.dumps(selection, indent=2) + "\n", encoding="utf-8"
        )
    else:
        winner = selection["primary_winner"]
        median = next(
            p["id"] for p in selection["selected_policies"] if p["q"] == "1/2"
        )
        paired = []
        month = {
            (r["policy"], r["period"]): r
            for r in scores
            if r["scope"] == "month" and r["cap"] == 250 and r["under_cost"] == 3
        }
        periods = ["2024-10", "2024-11", "2024-12"]
        delta = {
            m: month[winner, m]["cost"] - month[median, m]["cost"] for m in periods
        }
        nn = {m: month[winner, m]["n"] for m in periods}
        for m in periods:
            paired.append(
                dict(
                    comparison="winner_minus_median",
                    kind="month",
                    period=m,
                    cost_difference=delta[m],
                    n=nn[m],
                    mean_difference_exact=str(Q(delta[m], nn[m])),
                )
            )
        for m in periods:
            difference = sum(delta[x] for x in periods if x != m)
            n = sum(nn[x] for x in periods if x != m)
            paired.append(
                dict(
                    comparison="winner_minus_median",
                    kind="leave_one_month_out",
                    period=m,
                    cost_difference=difference,
                    n=n,
                    mean_difference_exact=str(Q(difference, n)),
                )
            )
        write_csv(out / "held-temporal-sensitivity.csv", paired)
    return dict(
        phase=phase,
        policies=len(policies),
        targets_per_policy=expected,
        predictions=len(predictions),
        metrics=len(scores),
        claim="Conditional retrospective simulation; prospective source availability and physical queues not validated",
    )
