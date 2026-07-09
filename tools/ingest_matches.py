"""Pull real ranked games and turn them into objective lane puzzles.

    python tools/ingest_matches.py --riot-id "Name#TAG" --platform na1 --count 20

Resolves the account, reads its solo-queue rank (used as the game's approximate lobby rank),
fetches recent ranked matches + timelines, extracts the lane facts, and appends them to
game/data/matches.jsonl. Needs RIOT_API_KEY (in .env or the environment).
"""
from __future__ import annotations
import argparse
import dataclasses
import json
import sys
import time
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.envfile import load_env
from game import riot, matches

OUT = Path(__file__).resolve().parent.parent / "game" / "data" / "matches.jsonl"


def _existing_ids() -> set[str]:
    if not OUT.exists():
        return set()
    ids = set()
    for line in OUT.read_text(encoding="utf-8").splitlines():
        if line.strip():
            ids.add(json.loads(line)["match_id"])
    return ids


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--riot-id", required=True, help='Riot ID as "Name#TAG"')
    ap.add_argument("--platform", default="na1", help="na1, euw1, kr, ...")
    ap.add_argument("--count", type=int, default=20)
    ap.add_argument("--lane", default="bot")
    args = ap.parse_args(argv)

    load_env()
    if not riot.has_key():
        print("No RIOT_API_KEY found (put it in .env). Aborting.")
        return 1

    region = riot.REGION_CLUSTER.get(args.platform, "americas")
    try:
        puuid = riot.resolve_puuid(args.riot_id, args.platform)
        rank = riot.fetch_rank_by_puuid(puuid, args.platform) or "UNRANKED"
    except Exception as e:
        print(f"Could not resolve '{args.riot_id}' on {args.platform}: {e}")
        return 1
    print(f"Account OK. Solo-queue rank: {rank}. Region cluster: {region}")

    ids = matches.recent_match_ids(puuid, region, count=args.count, queue=420)
    print(f"Found {len(ids)} ranked matches; extracting {args.lane} facts...")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    have = _existing_ids()
    added = 0
    with open(OUT, "a", encoding="utf-8") as fh:
        for i, mid in enumerate(ids, 1):
            if mid in have:
                continue
            try:
                m = matches.get_match(mid, region)
                tl = matches.get_timeline(mid, region)
            except urllib.error.HTTPError as e:
                if e.code == 429:  # rate limited — back off and retry once
                    print("  rate limited; sleeping 10s..."); time.sleep(10)
                    continue
                print(f"  {mid}: HTTP {e.code}, skipping"); continue
            facts = matches.extract_facts(m, tl, lane=args.lane, rank=rank)
            if facts:
                fh.write(json.dumps(dataclasses.asdict(facts)) + "\n")
                added += 1
                print(f"  [{i}/{len(ids)}] {mid}  {facts.blue} vs {facts.red}  "
                      f"gold@10={facts.facts.get('gold_lead_at_10')}")
            time.sleep(1.2)  # stay under dev-key rate limits

    print(f"\nDone. Added {added} new matches -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
