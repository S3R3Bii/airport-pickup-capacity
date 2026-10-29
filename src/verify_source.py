"""Independent SQL control totals and complete civil-grid construction."""

import csv, gzip, hashlib, io, json, sqlite3
from datetime import date, timedelta
from pathlib import Path


def verify(root="."):
    root = Path(root)
    cfg = json.loads((root / "protocol.json").read_text(encoding="utf-8"))
    manifest = json.loads(
        (root / "data/source/manifest.json").read_text(encoding="utf-8")
    )
    raw = (root / "data/source/hourly_counts.csv.gz").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == manifest["selected_sha256"]
    rows = list(csv.DictReader(io.StringIO(gzip.decompress(raw).decode())))
    db = sqlite3.connect(":memory:")
    db.execute(
        "CREATE TABLE source(day TEXT,ordinal INT,zone INT,hour INT,n INT,scope TEXT,dow INT,daytype INT,PRIMARY KEY(day,zone,hour))"
    )
    checks = 0
    for r in rows:
        d = date.fromisoformat(r["date"])
        z, h, n = int(r["zone"]), int(r["hour"]), int(r["published_records"])
        assert (
            date(2024, 1, 1) <= d < date(2025, 1, 1)
            and z in [132, 138]
            and 0 <= h <= 23
            and n >= 0
        )
        checks += 4
        assert r["scope"] == (
            "EXCLUDED_DST_DATE"
            if r["date"] in cfg["excluded_civil_dates"]
            else "IN_SCOPE"
        )
        checks += 1
        db.execute(
            "INSERT INTO source VALUES (?,?,?,?,?,?,?,?)",
            (
                r["date"],
                d.toordinal(),
                z,
                h,
                n,
                r["scope"],
                d.weekday(),
                int(d.weekday() >= 5),
            ),
        )
    assert (
        len(rows) == 17568
        and db.execute("SELECT COUNT(DISTINCT day) FROM source").fetchone()[0] == 366
    )
    checks += 2
    for day, count in db.execute("SELECT day,COUNT(*) FROM source GROUP BY day"):
        assert count == 48
        checks += 1
    hourly = json.loads((root / "data/source/hourly.json").read_text(encoding="utf-8"))
    expected = {
        (r["day"][:10], int(r["zone"]), int(r["hour"])): int(r["n"]) for r in hourly
    }
    assert len(expected) == len(hourly)
    for r in rows:
        assert int(r["published_records"]) == expected.get(
            (r["date"], int(r["zone"]), int(r["hour"])), 0
        )
        checks += 1
    actual_daily = {
        (d, z): n
        for d, z, n in db.execute(
            "SELECT day,zone,SUM(n) FROM source GROUP BY day,zone"
        )
    }
    daily = {
        (r["day"][:10], int(r["zone"])): int(r["n"])
        for r in json.loads(
            (root / "data/source/daily.json").read_text(encoding="utf-8")
        )
    }
    assert {k: v for k, v in actual_daily.items() if v != 0} == daily
    checks += len(actual_daily)
    actual_monthly = {
        (int(m), z): n
        for m, z, n in db.execute(
            "SELECT substr(day,6,2),zone,SUM(n) FROM source GROUP BY substr(day,6,2),zone"
        )
    }
    monthly = {
        (int(r["month"]), int(r["zone"])): int(r["n"])
        for r in json.loads(
            (root / "data/source/monthly.json").read_text(encoding="utf-8")
        )
    }
    assert actual_monthly == monthly
    checks += len(monthly)
    assert manifest["metadata"]["matched_before_after"] is True
    total = db.execute("SELECT SUM(n) FROM source").fetchone()[0]
    excluded = db.execute(
        "SELECT SUM(n) FROM source WHERE scope!='IN_SCOPE'"
    ).fetchone()[0]
    assert (
        total == manifest["airport_records"]
        and excluded == manifest["excluded_dst_records"]
    )
    checks += 3
    phases = {}
    for name, start, end in [
        ("initial", "2024-01-01", "2024-07-01"),
        ("validation", "2024-07-01", "2024-10-01"),
        ("held", "2024-10-01", "2025-01-01"),
    ]:
        phases[name] = db.execute(
            "SELECT COUNT(*) FROM source WHERE scope='IN_SCOPE' AND day>=? AND day<?",
            (start, end),
        ).fetchone()[0]
    assert phases == dict(initial=8688, validation=4416, held=4368)
    checks += 3
    return (
        dict(
            status="PASS",
            source_grid_checks=checks,
            grid_rows=len(rows),
            source_records=total,
            excluded_dst_records=excluded,
            phase_rows=phases,
            quality="Independent server aggregate controls and SQL grid reconciliation; original individual-record accuracy/completeness and historical vintages unverified",
        ),
        db,
    )


if __name__ == "__main__":
    result, _ = verify()
    Path("data/source/VERIFICATION.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result))
