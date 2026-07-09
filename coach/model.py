"""Structured types that flow through the pipeline.

The `CoachingBrief` is the important one: it is the deterministic engine's *entire*
output, a fact-checked object. Everything downstream (template text, LLM prose) may
only *rephrase* what is already in here — never add new claims. That constraint is
what keeps the assistant from hallucinating League advice.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Insight:
    """A single coaching claim plus the evidence that justified it."""
    text: str
    reasons: list[str] = field(default_factory=list)
    priority: float = 0.0
    tag: str = ""  # which rule produced it (for debugging / weighting)


@dataclass
class LaneNote:
    lane: str            # top / jungle / mid / bot
    ally: str            # e.g. "Ezreal + Karma"
    enemy: str           # e.g. "Caitlyn + Blitzcrank"
    lines: list[str] = field(default_factory=list)
    curated: bool = False  # True if a hand-authored matchup rule fired


@dataclass
class ChampIdentity:
    name: str
    note: str              # one-line identity for the sticky note
    wants: str = ""
    avoids: str = ""
    mistake: str = ""


@dataclass
class CoachingBrief:
    your_win_condition: Insight
    enemy_win_condition: Insight
    remember: list[Insight] = field(default_factory=list)
    lanes: list[LaneNote] = field(default_factory=list)
    identities: list[ChampIdentity] = field(default_factory=list)
    power_spikes: list[Insight] = field(default_factory=list)
    mistakes: list[Insight] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)  # unknown champs, thin data, etc.
    debug: dict = field(default_factory=dict)          # raw team features
