"""Loads champion facts and turns raw comps into team-feature vectors.

This whole module is DETERMINISTIC. No cleverness, no model — just aggregating the
hand-authored facts into the numbers the rules read. If two people run the same comp
they get byte-identical features.
"""
from __future__ import annotations
import json
import statistics
import sys
from pathlib import Path


def _base_dir() -> Path:
    # When packaged with PyInstaller (onefile), data is unpacked to sys._MEIPASS.
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent.parent


DATA_DIR = _base_dir() / "data"

ROLE_ORDER = ["top", "jungle", "mid", "adc", "support"]


def _load(name: str) -> dict:
    with open(DATA_DIR / name, encoding="utf-8") as fh:
        return json.load(fh)


def load_champions(path: Path | None = None) -> dict[str, dict]:
    """Objective/structured attributes (the Riot-derivable layer)."""
    raw = _load("champions.json") if path is None else json.load(open(path, encoding="utf-8"))
    for name, c in raw.items():
        c["name"] = name
    return raw


def load_identity() -> dict:
    """Curated champion identity (expert knowledge layer)."""
    return {k: v for k, v in _load("identity.json").items() if not k.startswith("_")}


def load_matchups() -> list[dict]:
    """Curated hidden matchup knowledge (expert knowledge layer)."""
    return _load("matchups.json").get("rules", [])


def matchup_lines(ally_names: list[str], enemy_names: list[str], rules: list[dict]) -> list[str]:
    """Return curated lines whose ally/enemy champ sets are subsets of this lane."""
    a, e = set(ally_names), set(enemy_names)
    lines: list[str] = []
    for r in rules:
        if set(r["ally"]) <= a and set(r["enemy"]) <= e:
            lines.extend(r["lines"])
    # de-dupe, keep order
    seen, out = set(), []
    for ln in lines:
        if ln not in seen:
            seen.add(ln)
            out.append(ln)
    return out


class Champion:
    """Thin convenience wrapper so rules read like English (`c.has('poke')`)."""

    def __init__(self, data: dict):
        self.d = data
        self.name = data["name"]

    def has(self, tag: str) -> bool:
        return tag in self.d.get("tags", [])

    def has_hard_cc(self) -> bool:
        return any(cc.get("hard") for cc in self.d.get("cc", []))

    def cc_types(self, hard_only=False) -> list[str]:
        return [cc["type"] for cc in self.d.get("cc", []) if cc.get("hard") or not hard_only]

    @property
    def curve(self) -> dict:
        return self.d["curve"]

    def __getattr__(self, item):  # engage, disengage, mobility, tags, roles, ...
        return self.d[item]


def normalize_comp(comp: list[str], champs: dict[str, dict]) -> tuple[list[Champion], list[str]]:
    """Return (known Champion objects, warnings for unknown names)."""
    out, warnings = [], []
    for name in comp:
        key = name.replace(" ", "").replace("'", "")
        match = next((k for k in champs if k.lower() == key.lower()), None)
        if match:
            out.append(Champion(champs[match]))
        else:
            warnings.append(f"Unknown champion '{name}' — coaching for that slot is omitted.")
    return out, warnings


def team_features(team: list[Champion]) -> dict:
    """Aggregate a 5-champ team into the numbers every rule reads.

    Curves are averaged; capability scores use max() because *one* champion with a
    game-ending hook defines the team's pick threat, not the average of five.
    """
    n = max(len(team), 1)

    def curve_avg(stage):
        return statistics.mean(c.curve[stage] for c in team) if team else 0.0

    early, mid, late = curve_avg("early"), curve_avg("mid"), curve_avg("late")

    def count_tag(tag):
        return sum(1 for c in team if c.has(tag))

    hard_cc = sum(1 for c in team if c.has_hard_cc())
    carries = [c for c in team if c.d.get("carry")]

    # damage split drives "they will build armor/MR against us" advice
    phys = sum(1 for c in team if c.d["damage_type"] in ("physical",))
    magic = sum(1 for c in team if c.d["damage_type"] in ("magic",))

    return {
        "early": round(early, 2),
        "mid": round(mid, 2),
        "late": round(late, 2),
        "scaling_index": round(late - early, 2),   # >0 wants to scale, <0 wants to end early
        "engage": max((c.engage for c in team), default=0),
        "engage_count": sum(1 for c in team if c.engage >= 2),
        "disengage": max((c.disengage for c in team), default=0),
        "mobility_avg": round(statistics.mean(c.mobility for c in team), 2) if team else 0,
        "hard_cc": hard_cc,
        "poke": count_tag("poke"),
        "pick": count_tag("pick") + count_tag("catcher") + count_tag("assassin"),
        "catcher": count_tag("catcher"),
        "teamfight": count_tag("teamfight") + count_tag("wombo"),
        "wombo": count_tag("wombo"),
        "frontline": count_tag("frontline"),
        "peel": count_tag("peel") + count_tag("enchanter"),
        "earlygame": count_tag("earlygame") + count_tag("lanebully"),
        "falloff": count_tag("falloff"),
        "hypercarry": count_tag("hypercarry"),
        "carries": [c.name for c in carries],
        "immobile_carries": [c.name for c in carries if c.has("immobile") or c.has("squishy")],
        "damage_phys": phys,
        "damage_magic": magic,
        "team_names": [c.name for c in team],
    }
