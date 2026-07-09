"""Deterministic daily puzzle: everyone sees the same one each day (Rankdle-style).

Puzzles are drawn from a hand-picked pool of *curated* comps (not auto-seeded champs), so the
question is meaningful. The engine computes the seed answer; the crowd supplies the label.
"""
from __future__ import annotations
import datetime as _dt

from .puzzle import make_puzzle, Puzzle

# Curated, meaningful matchups. Grows as the curated champion pool grows.
POOL: list[tuple[list[str], list[str]]] = [
    (["Ornn", "Sejuani", "Orianna", "Ezreal", "Karma"],
     ["Renekton", "LeeSin", "LeBlanc", "Caitlyn", "Blitzcrank"]),
    (["Malphite", "Sejuani", "Orianna", "Jinx", "Lulu"],
     ["Renekton", "LeeSin", "LeBlanc", "Caitlyn", "Leona"]),
    (["Ornn", "Sejuani", "Yasuo", "Jinx", "Lulu"],
     ["Renekton", "LeeSin", "LeBlanc", "Caitlyn", "Blitzcrank"]),
]


def _day_index(today: _dt.date | None = None) -> int:
    today = today or _dt.date.today()
    return today.toordinal()


def daily_puzzle(today: _dt.date | None = None) -> Puzzle:
    idx = _day_index(today)
    blue, red = POOL[idx % len(POOL)]
    return make_puzzle(blue, red, puzzle_id=f"daily-{(today or _dt.date.today()).isoformat()}")
