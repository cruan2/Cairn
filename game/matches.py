"""Objective lane-matchup puzzles from real match timelines.

The unit is a 2v2 lane (bot by default). The questions have FACT answers pulled from Riot's
match timeline — "who was up gold in bot at 10:00?", "who got the first bot-lane kill?" — so
being wrong means the real game went the other way, not that a model disagrees.

Two payoffs:
  1. a satisfying, verifiable guessing game (link the match as proof), and
  2. the aggregate: over many games of a matchup, WHICH side is actually ahead at minute Y.
     That is objective ground truth for "who should be winning this lane."

`extract_facts` is a pure function over match+timeline JSON (Riot match-v5 shape) and is fully
testable offline. The Riot fetchers are gated behind a key.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass, field

BOT_POSITIONS = {"BOTTOM", "UTILITY"}
GOLD_EVEN_THRESHOLD = 250  # gold lead smaller than this counts as "even"
LANE_TYPE = {"bot": "BOT_LANE", "top": "TOP_LANE", "mid": "MID_LANE"}
PLATE_LEAD = 2             # plate differential needed to call a side the pressuring one


# --------------------------------------------------------------------------- #
# Pure extraction (offline-testable)
# --------------------------------------------------------------------------- #
def _lane_participants(match: dict, positions=BOT_POSITIONS) -> dict[int, list[dict]]:
    """teamId -> list of participant dicts playing the given lane."""
    out: dict[int, list[dict]] = {100: [], 200: []}
    for p in match["info"]["participants"]:
        if p.get("teamPosition") in positions:
            out.setdefault(p["teamId"], []).append(p)
    return out


def _frame_at(timeline: dict, minute: int) -> dict:
    """The frame whose timestamp is closest to `minute` (frames are ~1/min)."""
    frames = timeline["info"]["frames"]
    target = minute * 60_000
    return min(frames, key=lambda f: abs(f["timestamp"] - target))


def _team_gold(frame: dict, pids: list[int]) -> int:
    pf = frame["participantFrames"]
    return sum(pf[str(pid)]["totalGold"] for pid in pids if str(pid) in pf)


def _events(timeline: dict, before_ms: int | None = None):
    for f in timeline["info"]["frames"]:
        for e in f.get("events", []):
            if before_ms is None or e.get("timestamp", 0) <= before_ms:
                yield e


@dataclass
class LaneFacts:
    match_id: str
    lane: str
    # champions on each team's lane, as sorted tuples (side-independent for aggregation)
    blue: list[str]
    red: list[str]
    # each fact names the side that was ahead: "blue" | "red" | "even" | "none"
    facts: dict[str, str] = field(default_factory=dict)
    winner: str = ""       # "blue"/"red" — the overall game result (also objective)
    rank: str = ""         # approx lobby rank (from the source account's tier); non-obvious but key
    patch: str = ""        # e.g. "15.13" — the meta shifts every patch, so it's a dimension
    link: str = ""         # public match page so players can verify the answer
    # directional pressure signal ------------------------------------------------
    plates: dict = field(default_factory=dict)         # {"blue": n, "red": n} taken before 14:00
    lane_deaths: dict = field(default_factory=dict)    # {"blue": n, "red": n} in-lane deaths
    jungle_interference: bool = False                  # a jungler was involved in a lane kill early
    pressure: str = ""      # even | {side}_safe_pressure | {side}_pressure_punished | jungle_influenced


# platform code (from the match id prefix) -> leagueofgraphs region slug
_LOG_REGION = {"na1": "na", "euw1": "euw", "eun1": "eune", "kr": "kr", "br1": "br",
               "la1": "lan", "la2": "las", "oc1": "oce", "ru": "ru", "tr1": "tr", "jp1": "jp"}


def match_link(match_id: str) -> str:
    """NA1_1234567890 -> a public match page anyone can open to check the facts."""
    if "_" not in match_id:
        return ""
    region, gid = match_id.split("_", 1)
    slug = _LOG_REGION.get(region.lower(), region.lower())
    return f"https://www.leagueofgraphs.com/match/{slug}/{gid}"


def extract_facts(match: dict, timeline: dict, lane: str = "bot",
                  gold_minute: int = 10, kill_before: int = 15,
                  plate_before: int = 14, rank: str = "") -> LaneFacts | None:
    positions = BOT_POSITIONS if lane == "bot" else {lane.upper()}
    lane_ps = _lane_participants(match, positions)
    blue_ps, red_ps = lane_ps.get(100, []), lane_ps.get(200, [])
    if not blue_ps or not red_ps:
        return None

    blue_ids = [p["participantId"] for p in blue_ps]
    red_ids = [p["participantId"] for p in red_ps]
    lane_ids = set(blue_ids) | set(red_ids)
    team_of = {p["participantId"]: p["teamId"] for p in match["info"]["participants"]}
    junglers = {p["participantId"] for p in match["info"]["participants"]
                if p.get("teamPosition") == "JUNGLE"}
    side = lambda pid: "blue" if team_of.get(pid) == 100 else "red"

    # Fact 1: who is up gold in this lane at minute Y
    fr = _frame_at(timeline, gold_minute)
    gdiff = _team_gold(fr, blue_ids) - _team_gold(fr, red_ids)
    gold_side = "even" if abs(gdiff) < GOLD_EVEN_THRESHOLD else ("blue" if gdiff > 0 else "red")

    # Fact 2: first kill involving this lane, before minute N
    first_kill = "none"
    for e in _events(timeline, kill_before * 60_000):
        if e.get("type") != "CHAMPION_KILL":
            continue
        if e.get("killerId") in lane_ids or e.get("victimId") in lane_ids:
            first_kill = side(e.get("killerId"))
            break

    # Directional pressure, measured only in the CLEAN window BEFORE the jungle first touches
    # the lane. A gank at 11:00 no longer voids plate pressure that happened at 4:00; only a
    # very early gank (before any read is possible) drops the game.
    lane_type = LANE_TYPE.get(lane, "BOT_LANE")
    laning_cap = plate_before * 60_000
    kills = [e for e in _events(timeline, laning_cap) if e.get("type") == "CHAMPION_KILL"]

    t_jg = None  # timestamp of first jungle involvement in this lane
    for e in kills:
        k, v = e.get("killerId"), e.get("victimId")
        if (k in lane_ids or v in lane_ids) and \
           ({k, v} | set(e.get("assistingParticipantIds", []))) & junglers:
            t_jg = e["timestamp"]
            break
    window = min(t_jg, laning_cap) if t_jg is not None else laning_cap

    plates = {"blue": 0, "red": 0}
    for e in _events(timeline, window):
        if e.get("type") == "TURRET_PLATE_DESTROYED" and e.get("laneType") == lane_type \
                and e.get("killerId") in team_of:
            plates[side(e["killerId"])] += 1
    lane_deaths = {"blue": 0, "red": 0}
    for e in kills:
        if e["timestamp"] <= window and e.get("victimId") in lane_ids:
            lane_deaths[side(e["victimId"])] += 1

    # Taking plates (walking up) WITHOUT paying for it = safe pressure.
    pd = plates["blue"] - plates["red"]
    if t_jg is not None and t_jg < 5 * 60_000:
        pressure, plate_side = "insufficient_window", "insufficient"  # ganked before any read
    elif abs(pd) < PLATE_LEAD:
        pressure, plate_side = "even", "even"
    else:
        lead = "blue" if pd > 0 else "red"
        plate_side = lead
        pressure = f"{lead}_pressure_punished" if lane_deaths[lead] > 0 else f"{lead}_safe_pressure"
    jungle_interference = t_jg is not None  # informational: did a gank happen at all before 14:00

    winner = "blue" if next(p for p in match["info"]["participants"] if p["teamId"] == 100)["win"] else "red"
    mid = match["metadata"]["matchId"]
    gv = match.get("info", {}).get("gameVersion", "")
    patch = ".".join(gv.split(".")[:2]) if gv else ""
    return LaneFacts(
        match_id=mid, lane=lane,
        blue=sorted(p["championName"] for p in blue_ps),
        red=sorted(p["championName"] for p in red_ps),
        facts={f"gold_lead_at_{gold_minute}": gold_side,
               f"first_lane_kill_before_{kill_before}": first_kill,
               f"plate_lead_before_{plate_before}": plate_side},
        winner=winner, rank=rank, patch=patch, link=match_link(mid),
        plates=plates, lane_deaths=lane_deaths,
        jungle_interference=jungle_interference, pressure=pressure,
    )


# --------------------------------------------------------------------------- #
# Aggregation — the objective "who should be winning" payoff
# --------------------------------------------------------------------------- #
def _canonical(a: list[str], b: list[str]) -> tuple[tuple, tuple]:
    """Side-independent matchup key: the two pairs sorted so aggregation is symmetric."""
    ta, tb = tuple(sorted(a)), tuple(sorted(b))
    return (ta, tb) if ta <= tb else (tb, ta)


def aggregate(records: list[LaneFacts], fact_key: str) -> dict:
    """For each matchup, how often each pair was ahead on `fact_key`."""
    buckets: dict[tuple, Counter] = {}
    for r in records:
        key = _canonical(r.blue, r.red)
        side = r.facts.get(fact_key)
        # translate blue/red -> which champion-pair was ahead
        if side == "blue":
            ahead = tuple(sorted(r.blue))
        elif side == "red":
            ahead = tuple(sorted(r.red))
        else:
            ahead = side  # "even"/"none"
        buckets.setdefault(key, Counter())[ahead] += 1
    result = {}
    for key, counter in buckets.items():
        n = sum(counter.values())
        result[key] = {"n": n, "distribution": {str(k): round(v / n, 2) for k, v in counter.items()}}
    return result


def pressure_report(records: list[LaneFacts]) -> dict:
    """Per matchup, how often each pair applies plate pressure — and gets away with it.

    Only counts jungle-free games, so the number reflects the 2v2, not who got camped.
    Output per matchup: clean_n, and per pair {led, safe} = games it took the plate lead and
    the subset where it wasn't punished. This is the 'can you step up here?' signal.
    """
    out: dict[tuple, dict] = {}
    for r in records:
        if r.pressure == "insufficient_window":   # ganked before a read was possible
            continue
        key = _canonical(r.blue, r.red)
        d = out.setdefault(key, {"clean_n": 0, "pairs": {}})
        d["clean_n"] += 1
        if r.pressure == "even":
            continue
        lead = "blue" if r.pressure.startswith("blue") else "red"
        pair = str(tuple(sorted(r.blue if lead == "blue" else r.red)))
        pd = d["pairs"].setdefault(pair, {"led": 0, "safe": 0})
        pd["led"] += 1
        pd["safe"] += int(r.pressure.endswith("safe_pressure"))
    return out


def champion_fact_rate(records: list[LaneFacts], fact_key: str, min_n: int = 5) -> dict:
    """Per champion, how often THEIR side was ahead on `fact_key`. Champion-level gives the N
    that exact duos can't. E.g. 'Caitlyn lanes lead gold@10 in 61% of games (n=48)'."""
    stats: dict[str, Counter] = {}
    for r in records:
        winning = r.facts.get(fact_key)
        for champ in r.blue:
            stats.setdefault(champ, Counter())["ahead" if winning == "blue"
                                                else "behind" if winning == "red" else "neutral"] += 1
        for champ in r.red:
            stats.setdefault(champ, Counter())["ahead" if winning == "red"
                                                else "behind" if winning == "blue" else "neutral"] += 1
    out = {}
    for champ, c in stats.items():
        n = sum(c.values())
        if n >= min_n:
            out[champ] = {"n": n, "ahead_pct": round(100 * c["ahead"] / n),
                          "behind_pct": round(100 * c["behind"] / n)}
    return dict(sorted(out.items(), key=lambda kv: -kv[1]["ahead_pct"]))


def champion_pressure_rate(records: list[LaneFacts], min_n: int = 5) -> dict:
    """Per champion, in clean (readable) games: how often their side took the plate lead, and
    what share of those was un-punished. Validates 'this champ can step up' at volume."""
    stats: dict[str, dict] = {}
    for r in records:
        if r.pressure == "insufficient_window":
            continue
        lead = None if r.pressure == "even" else ("blue" if r.pressure.startswith("blue") else "red")
        safe = r.pressure.endswith("safe_pressure")
        for sidev, champs in (("blue", r.blue), ("red", r.red)):
            for champ in champs:
                s = stats.setdefault(champ, {"clean": 0, "led": 0, "safe": 0})
                s["clean"] += 1
                if lead == sidev:
                    s["led"] += 1
                    s["safe"] += int(safe)
    out = {}
    for champ, s in stats.items():
        if s["clean"] >= min_n:
            out[champ] = {"clean_n": s["clean"], "led_pct": round(100 * s["led"] / s["clean"]),
                          "safe_pct": round(100 * s["safe"] / s["led"]) if s["led"] else 0}
    return dict(sorted(out.items(), key=lambda kv: -kv[1]["led_pct"]))


# --------------------------------------------------------------------------- #
# Riot fetchers (gated on RIOT_API_KEY) — match-v5 uses regional routing
# --------------------------------------------------------------------------- #
def recent_match_ids(puuid: str, region: str = "americas", count: int = 20,
                     queue: int = 420) -> list[str]:
    from .riot import _get
    return _get(f"https://{region}.api.riotgames.com/lol/match/v5/matches/by-puuid/"
                f"{puuid}/ids?queue={queue}&count={count}")


def get_match(match_id: str, region: str = "americas") -> dict:
    from .riot import _get
    return _get(f"https://{region}.api.riotgames.com/lol/match/v5/matches/{match_id}")


def get_timeline(match_id: str, region: str = "americas") -> dict:
    from .riot import _get
    return _get(f"https://{region}.api.riotgames.com/lol/match/v5/matches/{match_id}/timeline")


# --------------------------------------------------------------------------- #
# Synthetic match+timeline so the pipeline is playable/testable with no API key
# --------------------------------------------------------------------------- #
def mock_match(match_id: str, blue_bot, red_bot, red_gold_edge: int, red_first_kill: bool,
               red_wins: bool, red_plates: int = 3, blue_plates: int = 0,
               jungle_gank: bool = False):
    """Build a minimal match-v5-shaped match + timeline for tests/demos."""
    roster = [
        (1, 100, "TOP", "Ornn"), (2, 100, "JUNGLE", "Sejuani"), (3, 100, "MIDDLE", "Orianna"),
        (4, 100, "BOTTOM", blue_bot[0]), (5, 100, "UTILITY", blue_bot[1]),
        (6, 200, "TOP", "Renekton"), (7, 200, "JUNGLE", "LeeSin"), (8, 200, "MIDDLE", "LeBlanc"),
        (9, 200, "BOTTOM", red_bot[0]), (10, 200, "UTILITY", red_bot[1]),
    ]
    participants = [{"participantId": pid, "teamId": tid, "teamPosition": pos,
                     "championName": champ, "win": (red_wins == (tid == 200))}
                    for pid, tid, pos, champ in roster]
    match = {"metadata": {"matchId": match_id}, "info": {"participants": participants}}

    red_plate_min = [4, 6, 8, 10, 12][:red_plates]     # red bot (9) takes blue's plates
    blue_plate_min = [5, 7, 9, 11, 13][:blue_plates]   # blue bot (4) takes red's plates
    frames = []
    for m in range(0, 15):
        pf = {}
        for pid, tid, *_ in roster:
            base = 500 + m * 300
            if pid in (9, 10):        # red bot pair pulls ahead in gold
                base += (red_gold_edge * m) // 10
            pf[str(pid)] = {"participantId": pid, "totalGold": base, "minionsKilled": m * 8}
        events = []
        if red_first_kill and m == 6:  # red bot solo-kills blue ADC (no jungler)
            events.append({"type": "CHAMPION_KILL", "timestamp": m * 60_000,
                           "killerId": 9, "victimId": 4, "assistingParticipantIds": [10]})
        if jungle_gank and m == 5:     # red JUNGLE (7) ganks blue bot -> jungle interference
            events.append({"type": "CHAMPION_KILL", "timestamp": m * 60_000,
                           "killerId": 7, "victimId": 4, "assistingParticipantIds": [9]})
        if m in red_plate_min:
            events.append({"type": "TURRET_PLATE_DESTROYED", "timestamp": m * 60_000,
                           "killerId": 9, "laneType": "BOT_LANE", "teamId": 100})
        if m in blue_plate_min:
            events.append({"type": "TURRET_PLATE_DESTROYED", "timestamp": m * 60_000,
                           "killerId": 4, "laneType": "BOT_LANE", "teamId": 200})
        frames.append({"timestamp": m * 60_000, "participantFrames": pf, "events": events})
    return match, {"info": {"frames": frames}}


def _demo():
    # Ezreal+Karma (scaling) vs Caitlyn+Blitz (lane bully). Games vary: some clean, one ganked.
    specs = [  # (gold_edge, first_kill, red_wins, red_plates, jungle_gank)
        (900, True, True, 3, False),
        (700, False, True, 2, False),
        (300, False, False, 3, True),   # this one is jungle-influenced -> excluded from pressure
        (200, False, False, 0, False),  # even lane, no plates
    ]
    recs = []
    for i, (edge, fk, win, plates, gank) in enumerate(specs):
        match, tl = mock_match(f"NA1_TEST{i}", ["Ezreal", "Karma"], ["Caitlyn", "Blitzcrank"],
                               red_gold_edge=edge, red_first_kill=fk, red_wins=win,
                               red_plates=plates, jungle_gank=gank)
        recs.append(extract_facts(match, tl, rank="GOLD"))

    r0 = recs[0]
    print("PUZZLE (one match):")
    print(f"  Rank: {r0.rank}   Bot — Blue {r0.blue}  vs  Red {r0.red}   [{r0.match_id}]")
    print(f"  Verify: {r0.link}")
    print(f"  gold@10: {r0.facts['gold_lead_at_10'].upper()}   "
          f"plates blue/red: {r0.plates['blue']}/{r0.plates['red']}   "
          f"lane deaths blue/red: {r0.lane_deaths['blue']}/{r0.lane_deaths['red']}")
    print(f"  jungle_interference: {r0.jungle_interference}   pressure: {r0.pressure}")

    print("\nPER-GAME pressure read:")
    for r in recs:
        print(f"  {r.match_id}: plates {r.plates['blue']}/{r.plates['red']}  "
              f"jungle={r.jungle_interference}  -> {r.pressure}")

    print("\nPRESSURE REPORT (jungle-free games only) — the surfaced matchup knowledge:")
    for key, d in pressure_report(recs).items():
        print(f"  {key[0]} vs {key[1]}  (clean n={d['clean_n']})")
        for pair, s in d["pairs"].items():
            pct = int(100 * s["led"] / d["clean_n"])
            safe = int(100 * s["safe"] / s["led"]) if s["led"] else 0
            print(f"    {pair} took the plate lead in {pct}% of clean games, "
                  f"un-punished {safe}% of the time -> step-up read")


if __name__ == "__main__":
    _demo()
