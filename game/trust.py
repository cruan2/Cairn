"""How much a vote counts. This is the answer to 'bad data from people who don't know'.

Three tiers, so login is optional but rewarded:

  anonymous      no login              -> tiny weight; can be collected, can't move consensus
  self_reported  typed their rank      -> modest weight, and CAPPED so claiming Challenger
                                          without proof can't outweigh a verified Silver
  verified       proved via Riot API   -> full rank-scaled weight

On top of the tier, a `reliability` multiplier (from honeypots / past agreement) means even a
verified Diamond who answers randomly gets quietly down-weighted. Tier gates the ceiling;
reliability polices behaviour.
"""
from __future__ import annotations

TIER_BASE = {"anonymous": 0.25, "self_reported": 0.6, "verified": 1.0}

# The product cares about high-elo consensus, so weight climbs with rank.
RANK_MULT = {
    "IRON": 0.6, "BRONZE": 0.8, "SILVER": 1.0, "GOLD": 1.2, "PLATINUM": 1.5,
    "EMERALD": 1.8, "DIAMOND": 2.3, "MASTER": 2.8, "GRANDMASTER": 3.2, "CHALLENGER": 3.5,
}
# Unverified claims cannot buy high trust: a self-reported rank is treated as at most Gold.
SELF_REPORT_CAP = RANK_MULT["GOLD"]


def rank_multiplier(rank: str | None, tier: str) -> float:
    m = RANK_MULT.get((rank or "").upper(), 1.0)
    if tier == "self_reported":
        m = min(m, SELF_REPORT_CAP)
    if tier == "anonymous":
        m = 1.0  # anonymous has no (trusted) rank
    return m


def weight(tier: str, rank: str | None = None, reliability: float = 1.0) -> float:
    tier = tier if tier in TIER_BASE else "anonymous"
    reliability = max(0.2, min(1.0, reliability))  # never fully zero, never above 1
    return round(TIER_BASE[tier] * rank_multiplier(rank, tier) * reliability, 3)
