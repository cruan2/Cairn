"""Seed the OBJECTIVE layer of champions.json from Riot's Data Dragon.

Data Dragon is free, static, no key. It gives us the facts that are genuinely objective:
attack range (=> melee/ranged), champion classes, and a name we can match against the live
client. It does NOT know positions, power curves, CC, or the coaching tags — those are the
SUBJECTIVE layer and stay hand-curated (that's the whole point of the split).

So this seeder only fills the objective skeleton and MARKS everything subjective as needing
review. It never overwrites an already-curated champion — curation always wins.

    python tools/seed_from_ddragon.py            # merge new champs into data/champions.json
    python tools/seed_from_ddragon.py --dry-run  # show what it would add, write nothing

Run it on a machine with internet.
"""
from __future__ import annotations
import argparse
import json
import shutil
import sys
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "champions.json"
VERSIONS = "https://ddragon.leagueoflegends.com/api/versions.json"
SUMMARY = "https://ddragon.leagueoflegends.com/cdn/{ver}/data/en_US/champion.json"

# DDragon 'tags' are combat classes, not our ontology. Map to our closest class vocab.
CLASS_MAP = {"Fighter": "bruiser", "Tank": "tank", "Mage": "mage",
             "Assassin": "assassin", "Marksman": "marksman", "Support": "enchanter"}
# A conservative starter role guess from the primary class (always flagged for review).
ROLE_GUESS = {"Marksman": "adc", "Support": "support", "Mage": "mid",
              "Assassin": "mid", "Tank": "top", "Fighter": "top"}
# A few coaching tags we can assert from class alone; the rest must be curated.
TAG_SEED = {"Marksman": ["carry"], "Tank": ["frontline"],
            "Assassin": ["assassin", "pick"], "Support": ["enchanter", "peel"]}

# Fields DDragon cannot provide — every auto entry is flagged so we know what to curate.
NEEDS_CURATION = ["roles", "damage_type", "curve", "engage", "disengage",
                  "mobility", "waveclear", "cc", "tags", "spikes"]


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def _key(name: str) -> str:
    """Match the live-client display name: squish spaces/punctuation (Lee Sin -> LeeSin)."""
    return name.replace(" ", "").replace("'", "").replace(".", "").replace("&", "")


def _skeleton(c: dict) -> dict:
    tags = c.get("tags", [])
    primary = tags[0] if tags else ""
    rng = int(c.get("stats", {}).get("attackrange", 0))
    dmg = ("magic" if primary in ("Mage", "Support")
           else "mixed" if primary == "Tank" else "physical")
    return {
        "name": c["name"],
        "_ddragon_id": c["id"],
        "_auto": True,
        "_needs": NEEDS_CURATION,
        "roles": [ROLE_GUESS.get(primary, "mid")],
        "classes": [CLASS_MAP.get(t, t.lower()) for t in tags],
        "damage_type": dmg,
        "damage_profile": "mixed",
        "range_type": "ranged" if rng > 250 else "melee",
        "attack_range": rng,
        "curve": {"early": 3, "mid": 3, "late": 3},
        "engage": 0, "disengage": 0, "mobility": 0, "waveclear": 0,
        "cc": [], "utility": [],
        "tags": sorted({t for tag in tags for t in TAG_SEED.get(tag, [])}),
        "carry": "Marksman" in tags,
        "spikes": [],
        "notes": f"Auto-seeded from Data Dragon ({', '.join(tags)}). Needs curation.",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Seed champions.json from Data Dragon")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, write nothing")
    args = ap.parse_args(argv)

    ver = _get(VERSIONS)[0]
    print(f"Data Dragon version: {ver}")
    summary = _get(SUMMARY.format(ver=ver))["data"]

    existing = json.loads(DATA.read_text(encoding="utf-8"))
    have = {k.lower() for k in existing}

    added = []
    for c in summary.values():
        k = _key(c["name"])
        if k.lower() in have:      # curated OR already seeded -> never touch
            continue
        existing[k] = _skeleton(c)
        added.append(k)

    print(f"Existing (kept as-is): {len(existing) - len(added)}")
    print(f"New skeletons to add:  {len(added)}")
    if added:
        print("  e.g. " + ", ".join(sorted(added)[:12]) + (" ..." if len(added) > 12 else ""))

    if args.dry_run:
        print("\n[dry-run] nothing written.")
        return 0
    if not added:
        print("Nothing to add; champions.json already covers the roster.")
        return 0

    backup = DATA.with_suffix(".json.bak")
    shutil.copyfile(DATA, backup)
    DATA.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {DATA} ({len(existing)} champions). Backup at {backup.name}.")
    print("Auto entries are marked \"_auto\": true with a \"_needs\" list — curate those next.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
