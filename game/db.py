"""SQLite store for lane-fact records — our own accumulating match database.

Stdlib `sqlite3`, so no dependency and it's a single file (game/data/coach.db). One row per
(match_id, lane). Aggregation is a query with rank/patch/lane filters; the analysis functions in
matches.py operate on the `LaneFacts` this returns, so nothing else changes.

Swap SQLite for Postgres only when concurrency/scale demands it — the interface stays the same.
"""
from __future__ import annotations
import dataclasses
import json
import sqlite3
from pathlib import Path

from .matches import LaneFacts

DB_PATH = Path(__file__).resolve().parent / "data" / "coach.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS lane_facts (
    match_id TEXT NOT NULL,
    lane     TEXT NOT NULL,
    rank     TEXT,
    patch    TEXT,
    winner   TEXT,
    blue     TEXT,   -- json list
    red      TEXT,   -- json list
    facts    TEXT,   -- json dict
    plates   TEXT,   -- json dict
    lane_deaths TEXT,-- json dict
    jungle_interference INTEGER,
    pressure TEXT,
    link     TEXT,
    PRIMARY KEY (match_id, lane)
);
CREATE INDEX IF NOT EXISTS idx_rank_patch ON lane_facts(rank, patch, lane);
"""

_FIELDS = {f.name for f in dataclasses.fields(LaneFacts)}


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


def upsert(con: sqlite3.Connection, f: LaneFacts) -> None:
    con.execute(
        "INSERT OR REPLACE INTO lane_facts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (f.match_id, f.lane, f.rank, f.patch, f.winner,
         json.dumps(f.blue), json.dumps(f.red), json.dumps(f.facts),
         json.dumps(f.plates), json.dumps(f.lane_deaths),
         int(bool(f.jungle_interference)), f.pressure, f.link),
    )


def has(con: sqlite3.Connection, match_id: str, lane: str) -> bool:
    return con.execute("SELECT 1 FROM lane_facts WHERE match_id=? AND lane=?",
                       (match_id, lane)).fetchone() is not None


def count(con: sqlite3.Connection, rank: str | None = None, patch: str | None = None,
          lane: str | None = None) -> int:
    return len(load_records(con, rank, patch, lane, columns_only=True))


def load_records(con: sqlite3.Connection, rank: str | None = None, patch: str | None = None,
                 lane: str | None = None, columns_only: bool = False) -> list:
    q = ("SELECT match_id,lane,rank,patch,winner,blue,red,facts,plates,lane_deaths,"
         "jungle_interference,pressure,link FROM lane_facts WHERE 1=1")
    args: list = []
    for col, val in (("rank", rank), ("patch", patch), ("lane", lane)):
        if val:
            q += f" AND {col}=?"
            args.append(val)
    rows = con.execute(q, args).fetchall()
    if columns_only:
        return rows
    out = []
    for r in rows:
        out.append(LaneFacts(
            match_id=r[0], lane=r[1], rank=r[2], patch=r[3], winner=r[4],
            blue=json.loads(r[5]), red=json.loads(r[6]), facts=json.loads(r[7]),
            plates=json.loads(r[8]), lane_deaths=json.loads(r[9]),
            jungle_interference=bool(r[10]), pressure=r[11], link=r[12]))
    return out


def migrate_jsonl(con: sqlite3.Connection, path: Path) -> int:
    """Load an old *.jsonl file into the DB, ignoring unknown/missing fields."""
    if not path.exists():
        return 0
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        f = LaneFacts(**{k: v for k, v in d.items() if k in _FIELDS})
        upsert(con, f)
        n += 1
    con.commit()
    return n
