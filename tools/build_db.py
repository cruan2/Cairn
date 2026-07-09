"""Migrate existing *.jsonl match files into the SQLite database and show a sample query.

    python tools/build_db.py
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import db
from game.matches import champion_fact_rate, champion_pressure_rate

DATA = Path(__file__).resolve().parent.parent / "game" / "data"


def main() -> int:
    con = db.connect()
    total = 0
    for jsonl in sorted(DATA.glob("*.jsonl")):
        n = db.migrate_jsonl(con, jsonl)
        print(f"  migrated {n:4d} rows from {jsonl.name}")
        total += n
    print(f"DB now holds {db.count(con)} unique lane records (from {total} jsonl rows).")

    for rank in ("MASTER", "EMERALD"):
        recs = db.load_records(con, rank=rank, lane="bot")
        if not recs:
            continue
        print(f"\n=== {rank}: {len(recs)} bot lanes (queried from DB) ===")
        g = champion_fact_rate(recs, "gold_lead_at_10", min_n=5)
        for champ, s in list(g.items())[:5]:
            print(f"  {champ:14} ahead@10 {s['ahead_pct']}%  (n={s['n']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
