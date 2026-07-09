"""Slowly accumulate high-elo lane data into the DB, staying under dev-key rate limits.

Designed to be run over and over (manually or on a schedule). It:
  - samples apex-ladder players,
  - skips match ids already in the DB (no API call wasted on dupes),
  - paces every request so it won't trip the 100-req/2-min dev-key limit,
  - stops cleanly if the dev key has expired (403) so you know to refresh it.

    python tools/accumulate.py --target 60          # add ~60 new games this run
    python tools/accumulate.py --tier CHALLENGER --target 100 --pace 3

Run it on a schedule (Task Scheduler) to trickle data in while you wait for a production key.
"""
from __future__ import annotations
import argparse
import sys
import time
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.envfile import load_env
from game import riot, matches, db


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
    ap.add_argument("--target", type=int, default=60, help="new games to add this run")
    ap.add_argument("--per-player", type=int, default=15)
    ap.add_argument("--pace", type=float, default=3.0, help="seconds between requests (>=2.5 is safe)")
    ap.add_argument("--lane", default="bot")
    args = ap.parse_args(argv)

    load_env()
    if not riot.has_key():
        print("No RIOT_API_KEY in .env. Aborting.")
        return 1

    region = riot.REGION_CLUSTER.get(args.platform, "americas")
    con = db.connect()
    start_total = db.count(con)
    print(f"Start: DB has {start_total} records. Target: +{args.target} {args.tier} games "
          f"(pace {args.pace}s/request).")

    try:
        entries = riot.apex_league(args.tier, args.platform)
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print("403: dev key expired or invalid. Refresh RIOT_API_KEY in .env and re-run.")
            return 2
        raise
    import random
    random.shuffle(entries)

    added = 0
    for e in entries:
        if added >= args.target:
            break
        pu = _puuid(e, args.platform)
        if not pu:
            continue
        try:
            mids = matches.recent_match_ids(pu, region, count=args.per_player, queue=420)
            time.sleep(args.pace)
        except urllib.error.HTTPError as ex:
            if ex.code == 403:
                print("403 mid-run: dev key expired. Refresh .env and re-run — progress is saved.")
                break
            if ex.code == 429:
                time.sleep(15)
            continue

        for mid in mids:
            if added >= args.target:
                break
            if db.has(con, mid, args.lane):     # already have it — no API call spent
                continue
            try:
                m = matches.get_match(mid, region)
                time.sleep(args.pace)
                tl = matches.get_timeline(mid, region)
                time.sleep(args.pace)
            except urllib.error.HTTPError as ex:
                if ex.code == 403:
                    print("403 mid-run: dev key expired. Refresh .env and re-run — progress is saved.")
                    con.commit()
                    return 2
                if ex.code == 429:
                    print("  429 rate-limited; backing off 20s..."); time.sleep(20)
                continue
            facts = matches.extract_facts(m, tl, lane=args.lane, rank=args.tier)
            if facts:
                db.upsert(con, facts)
                added += 1
                if added % 10 == 0:
                    con.commit()
                    print(f"  +{added} (DB total {db.count(con)})")
    con.commit()
    print(f"Done. Added {added} this run. DB now holds {db.count(con)} records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
