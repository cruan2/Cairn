"""Ingest a batch of high-elo ranked games to validate lane assumptions at volume.

Pulls the apex ladder (Master/GM/Challenger), samples players, extracts lane facts from their
recent solo-queue games, and writes them to game/data/matches_highelo.jsonl (tagged with tier).

    python tools/ingest_highelo.py --tier MASTER --players 20 --per-player 6 --games 100

Needs RIOT_API_KEY. Dev keys are rate-limited (100 req / 2 min) — keep batches modest, or use a
Personal/Production key for big runs.
"""
from __future__ import annotations
import argparse
import dataclasses
import json
import random
import sys
import time
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.envfile import load_env
from game import riot, matches, db

OUT = Path(__file__).resolve().parent.parent / "game" / "data" / "matches_highelo.jsonl"


def _existing_ids() -> set[str]:
    if not OUT.exists():
        return set()
    return {json.loads(l)["match_id"] for l in OUT.read_text(encoding="utf-8").splitlines() if l.strip()}


def _puuid(entry: dict, platform: str) -> str | None:
    if entry.get("puuid"):
        return entry["puuid"]
    if entry.get("summonerId"):
        try:
            return riot.puuid_from_summoner_id(entry["summonerId"], platform)
        except Exception:
            return None
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", default="MASTER", choices=["MASTER", "GRANDMASTER", "CHALLENGER"])
    ap.add_argument("--platform", default="na1")
    ap.add_argument("--players", type=int, default=20, help="how many ladder players to sample")
    ap.add_argument("--per-player", type=int, default=6, help="recent matches per player")
    ap.add_argument("--games", type=int, default=120, help="hard cap on games ingested this run")
    ap.add_argument("--lane", default="bot")
    args = ap.parse_args(argv)

    load_env()
    if not riot.has_key():
        print("No RIOT_API_KEY (put it in .env). Aborting.")
        return 1

    region = riot.REGION_CLUSTER.get(args.platform, "americas")
    print(f"Fetching {args.tier} ladder on {args.platform}...")
    entries = riot.apex_league(args.tier, args.platform)
    random.shuffle(entries)
    entries = entries[:args.players]
    print(f"Sampled {len(entries)} {args.tier} players.")

    # gather candidate match ids
    ids: list[str] = []
    for i, e in enumerate(entries, 1):
        pu = _puuid(e, args.platform)
        if not pu:
            continue
        try:
            mids = matches.recent_match_ids(pu, region, count=args.per_player, queue=420)
        except urllib.error.HTTPError as ex:
            if ex.code == 429:
                time.sleep(10)
            continue
        ids.extend(mids)
        time.sleep(1.2)
    ids = list(dict.fromkeys(ids))          # de-dupe, preserve order
    have = _existing_ids()
    ids = [m for m in ids if m not in have][:args.games]
    print(f"{len(ids)} new games to process...")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    con = db.connect()
    added = 0
    with open(OUT, "a", encoding="utf-8") as fh:
        for i, mid in enumerate(ids, 1):
            try:
                m = matches.get_match(mid, region)
                tl = matches.get_timeline(mid, region)
            except urllib.error.HTTPError as ex:
                if ex.code == 429:
                    print("  rate limited; sleeping 10s..."); time.sleep(10); continue
                continue
            facts = matches.extract_facts(m, tl, lane=args.lane, rank=args.tier)
            if facts:
                db.upsert(con, facts)                                   # -> SQLite (the database)
                fh.write(json.dumps(dataclasses.asdict(facts)) + "\n")  # -> jsonl (human-readable log)
                added += 1
                if added % 10 == 0:
                    con.commit()
                    print(f"  {added} games...")
            time.sleep(1.2)
    con.commit()

    print(f"Done. Added {added} {args.tier} games -> DB ({db.count(con)} total) + {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
