"""Vote storage + rank-weighted consensus. JSONL now; swap for a DB when it matters.

A vote records the answer AND the trust inputs (tier/rank/reliability) so consensus is
computed with `trust.weight`. Anonymous votes are kept but barely move the needle.
"""
from __future__ import annotations
import json
import threading
from dataclasses import dataclass
from pathlib import Path

from .puzzle import OPTIONS
from .trust import weight

VOTES = Path(__file__).resolve().parent / "data" / "votes.jsonl"
_LOCK = threading.Lock()


def record_vote(puzzle_id: str, answer: str, tier: str, rank: str | None,
                session: str, reliability: float = 1.0, ts: str = "") -> None:
    VOTES.parent.mkdir(parents=True, exist_ok=True)
    row = {"puzzle_id": puzzle_id, "answer": answer, "tier": tier, "rank": rank,
           "session": session, "reliability": reliability, "ts": ts}
    with _LOCK:
        with open(VOTES, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")


def _read(puzzle_id: str) -> list[dict]:
    if not VOTES.exists():
        return []
    out = []
    with open(VOTES, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("puzzle_id") == puzzle_id:
                out.append(r)
    return out


@dataclass
class Consensus:
    answer: str
    agreement: float          # rank-weighted share of the winning answer
    n: int                    # raw number of votes
    breakdown: dict           # option -> {"weight": float, "raw": int}
    engine_agrees: bool
    flag_engine_bug: bool


def consensus(puzzle_id: str, engine_answer: str, confident_at: float = 0.66) -> Consensus:
    votes = _read(puzzle_id)
    wsum = {o: 0.0 for o in OPTIONS}
    raw = {o: 0 for o in OPTIONS}
    for v in votes:
        ans = v["answer"]
        if ans not in wsum:
            continue
        wsum[ans] += weight(v.get("tier", "anonymous"), v.get("rank"), v.get("reliability", 1.0))
        raw[ans] += 1
    total = sum(wsum.values()) or 1.0
    winner = max(wsum, key=lambda k: wsum[k])
    agreement = wsum[winner] / total
    engine_agrees = winner == engine_answer
    return Consensus(
        answer=winner, agreement=round(agreement, 3), n=len(votes),
        breakdown={o: {"weight": round(wsum[o], 2), "raw": raw[o]} for o in OPTIONS},
        engine_agrees=engine_agrees,
        flag_engine_bug=(len(votes) >= 5 and agreement >= confident_at and not engine_agrees),
    )
