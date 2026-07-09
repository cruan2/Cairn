"""The deterministic coaching brain.

Input : two teams' champion objects + their feature vectors.
Output: a CoachingBrief (structured facts), ranked by importance.

Everything here is rules a human coach could state out loud and defend. There is NO
model in this file. Each rule attaches its evidence (`reasons`) so the output is
auditable and so the LLM layer can be told "only rephrase these reasons."
"""
from __future__ import annotations
from .model import CoachingBrief, Insight, LaneNote, ChampIdentity
from .knowledge import Champion, team_features, matchup_lines

SCALE_GAP = 0.75  # curve delta needed to call one team the "scaling" side


# --------------------------------------------------------------------------- #
# Archetype: a short label + the tags that earned it. Rules and prose read this.
# --------------------------------------------------------------------------- #
def classify_archetype(f: dict) -> tuple[str, list[str]]:
    labels = []
    if f["scaling_index"] >= 0.6:
        labels.append("scaling / late-game")
    if f["earlygame"] >= 2 and f["scaling_index"] <= 0:
        labels.append("early-game snowball")
    if f["catcher"] >= 1 or f["pick"] >= 2:
        labels.append("pick / catch")
    if f["wombo"] >= 2 and f["engage"] >= 3:
        labels.append("wombo teamfight")
    elif f["teamfight"] >= 2:
        labels.append("teamfight")
    if f["poke"] >= 3 and f["engage"] <= 1:
        labels.append("poke / siege")
    if f["peel"] >= 2 and f["immobile_carries"]:
        labels.append("protect-the-carry")
    if not labels:
        labels.append("standard")
    return labels[0], labels


# --------------------------------------------------------------------------- #
# Win conditions: always COMPARATIVE. Your plan only makes sense relative to theirs.
# --------------------------------------------------------------------------- #
def win_conditions(you: dict, them: dict) -> tuple[Insight, Insight]:
    gap = you["scaling_index"] - them["scaling_index"]

    if gap >= SCALE_GAP:
        you_wc = Insight(
            "Play slow and reach the mid/late game — your team simply gets stronger than theirs.",
            [f"Your power curve climbs (+{you['scaling_index']}) while theirs is flatter/front-loaded (+{them['scaling_index']}).",
             _carry_reason(you)],
            tag="wc_scale")
        them_wc = Insight(
            "Force early fights and objectives to snowball before your team comes online.",
            [f"They are stronger early and fall off — {them['falloff']} of their champions actively weaken late." if them["falloff"]
             else "They are relatively stronger early and want to end before you scale."],
            tag="wc_early")
        return you_wc, them_wc

    if gap <= -SCALE_GAP:
        them_wc = Insight(
            "They want to play slow and outscale you — the game gets harder for you the longer it goes.",
            [f"Their curve climbs (+{them['scaling_index']}) more than yours (+{you['scaling_index']})."],
            tag="wc_scale")
        you_wc = Insight(
            "Force the early game — take fights and objectives before they reach their item spikes.",
            [f"You are stronger earlier; {you['earlygame']} of your champions are early-game threats." if you["earlygame"]
             else "You need to convert the early game before their scaling takes over."],
            tag="wc_early")
        return you_wc, them_wc

    # Even curves — differentiate on style (engage/pick vs poke/teamfight).
    you_wc = _style_win_condition(you, them, "your")
    them_wc = _style_win_condition(them, you, "their")
    return you_wc, them_wc


def _style_win_condition(a: dict, b: dict, whose: str) -> Insight:
    subj = "Your" if whose == "your" else "They"
    if a["catcher"] or a["pick"] >= 2:
        return Insight(
            f"{'Your' if whose=='your' else 'Their'} team wins by catching someone out and turning the pick into an objective.",
            [f"{a['pick']} pick/assassin/catcher threats vs their {b['pick']}."], tag="wc_pick")
    if a["poke"] >= 3 and a["engage"] <= 1:
        return Insight(
            f"{'Your' if whose=='your' else 'Their'} team wins by poking objectives and sieging — never let it become a 5v5 coinflip.",
            [f"{a['poke']} poke champions and low hard engage ({a['engage']})."], tag="wc_poke")
    if a["wombo"] >= 2:
        return Insight(
            f"{'Your' if whose=='your' else 'Their'} team wins one big grouped teamfight — land the AoE combo and it's over.",
            [f"{a['wombo']} chained-AoE (wombo) champions."], tag="wc_wombo")
    return Insight(
        f"{'Your' if whose=='your' else 'Their'} team wins by grouping and taking objectives on numbers advantage.",
        ["No single lopsided tempo — win the macro game."], tag="wc_generic")


def _carry_reason(f: dict) -> str:
    if f["carries"]:
        return f"Your win condition scales on {', '.join(f['carries'])}."
    return "Your damage compounds with items."


# --------------------------------------------------------------------------- #
# "Three things to remember" — generate many candidates, score, keep the top 3.
# --------------------------------------------------------------------------- #
def remember_points(you: dict, them: dict, you_wc: Insight) -> list[Insight]:
    c: list[Insight] = []

    if them["engage"] >= 3 or them["catcher"]:
        threat = "hook/engage" if them["catcher"] else "engage"
        c.append(Insight(
            f"Respect their {threat}: keep vision up and do not walk up alone or facecheck.",
            [f"They have {them['engage']}/3 engage" + (f" and {them['catcher']} hook threat." if them["catcher"] else ".")],
            priority=3 + them["engage"] + 2 * them["catcher"], tag="rem_engage"))

    if you["scaling_index"] - them["scaling_index"] >= SCALE_GAP:
        c.append(Insight(
            "Do not take bad fights before your first item spikes — time is on your side.",
            [f"You outscale (+{you['scaling_index']} vs +{them['scaling_index']})."],
            priority=3 + (you["scaling_index"] - them["scaling_index"]), tag="rem_dontfight"))

    if len(you["carries"]) == 1:
        car = you["carries"][0]
        c.append(Insight(
            f"Protect {car} — that is your only reliable damage source.",
            [f"{car} is your lone carry."], priority=3.5, tag="rem_protect"))
    elif you["immobile_carries"]:
        car = you["immobile_carries"][0]
        c.append(Insight(
            f"Peel for {car}: they are immobile and win the game if kept alive.",
            [f"{car} is an immobile carry."], priority=2.5, tag="rem_protect"))

    if them["pick"] >= 2 and them["engage"] < 3 and not them["catcher"]:
        c.append(Insight(
            "Don't get picked — cross the map as a group and hug walls when the map is dark.",
            [f"They have {them['pick']} pick/assassin threats."], priority=2.8, tag="rem_pick"))

    if you["disengage"] >= 3:
        c.append(Insight(
            "When they commit, use your disengage and reset — you win the fight they can't finish.",
            [f"You have {you['disengage']}/3 disengage."], priority=2.0, tag="rem_disengage"))

    if them["scaling_index"] - you["scaling_index"] >= SCALE_GAP:
        c.append(Insight(
            "Don't let the game go long and even — every objective early matters.",
            [f"They outscale you (+{them['scaling_index']})."], priority=3.2, tag="rem_tempo"))

    # Always-available fallback so we can guarantee three points.
    c.append(Insight(
        "Play around objectives with vision — dragon/herald fights decide this game more than kills.",
        ["Baseline macro reminder."], priority=1.0, tag="rem_objective"))

    c.sort(key=lambda i: i.priority, reverse=True)
    return c[:3]


# --------------------------------------------------------------------------- #
# Lane matchups. Bot is a 2v2 pair; top/mid/jungle are 1v1.
# --------------------------------------------------------------------------- #
def _by_role(team: list[Champion]) -> dict[str, list[Champion]]:
    d: dict[str, list[Champion]] = {}
    for c in team:
        d.setdefault(c.roles[0], []).append(c)
    return d


def lane_notes(you: list[Champion], them: list[Champion],
               curated_rules: list[dict]) -> list[LaneNote]:
    yr, tr = _by_role(you), _by_role(them)
    notes: list[LaneNote] = []
    lane_map = [("top", ["top"]), ("jungle", ["jungle"]), ("mid", ["mid"]),
                ("bot", ["adc", "support"])]
    for lane, roles in lane_map:
        allies = [c for r in roles for c in yr.get(r, [])]
        enemies = [c for r in roles for c in tr.get(r, [])]
        if not allies or not enemies:
            continue
        note = LaneNote(lane,
                        " + ".join(c.name for c in allies),
                        " + ".join(c.name for c in enemies))
        # Curated hidden knowledge first; generic tag rules only fill the gaps.
        curated = matchup_lines([c.name for c in allies],
                                [c.name for c in enemies], curated_rules)
        note.curated = bool(curated)
        # Curated knowledge is higher quality than the generic tag engine — when it
        # fires we use it alone, keeping the note short and memorable.
        note.lines = curated if curated else _matchup_lines(allies, enemies)
        notes.append(note)
    return notes


def champion_identities(you: list[Champion], identity: dict) -> list[ChampIdentity]:
    """Identity for YOUR champions, ordered by role. Carries get wants/avoids/mistake."""
    out: list[ChampIdentity] = []
    order = {r: i for i, r in enumerate(["top", "jungle", "mid", "adc", "support"])}
    for c in sorted(you, key=lambda c: order.get(c.roles[0], 9)):
        idn = identity.get(c.name)
        if not idn:
            continue
        detailed = bool(c.d.get("carry"))
        out.append(ChampIdentity(
            name=c.name,
            note=idn.get("note", ""),
            wants=idn.get("wants", "") if detailed else "",
            avoids=idn.get("avoids", "") if detailed else "",
            mistake=idn.get("mistake", "") if detailed else "",
        ))
    return out


def _matchup_lines(allies: list[Champion], enemies: list[Champion]) -> list[str]:
    lines: list[str] = []
    ally_tags = {t for c in allies for t in c.tags}
    enemy_tags = {t for c in enemies for t in c.tags}
    ally_ranged = all(c.d["range_type"] == "ranged" for c in allies)
    enemy_has_hook = any(c.has("catcher") for c in enemies)
    enemy_bully = "lanebully" in enemy_tags or "allin" in enemy_tags
    enemy_falloff = "falloff" in enemy_tags
    ally_poke = "poke" in ally_tags
    ally_scaling = "scaling" in ally_tags or "hypercarry" in ally_tags

    # The signature line from the prompt's example, generated from tags:
    if ally_poke and enemy_has_hook:
        hooker = next(c.name for c in enemies if c.has("catcher"))
        lines.append("Your goal isn't necessarily to kill them — it's to constantly poke "
                     "them down and deny their walk-up.")
        lines.append(f"Punish {hooker} when the hook is down; until then, stay behind your "
                     "minions and never facecheck a brush.")
    elif ally_poke and not enemy_has_hook:
        lines.append("Use your range to poke and win the trades before all-in ever comes up.")

    if enemy_bully and ally_scaling:
        bully = next((c.name for c in enemies if c.has("lanebully") or c.has("allin")), "them")
        lines.append(f"You lose the early 1v1 to {bully} — play safe, give up a little CS if you "
                     "must, and scale to your spikes.")
    if enemy_bully and not ally_scaling and "earlygame" not in ally_tags:
        lines.append("Respect their early levels; don't trade into their power window.")

    if enemy_falloff and ally_scaling:
        lines.append("They're on a timer — survive their strong phase and the matchup flips to you.")

    if "roam" in enemy_tags:
        roamer = next(c.name for c in enemies if c.has("roam"))
        lines.append(f"{roamer} will roam — ping when they leave and don't over-extend the wave.")

    if "dive" in enemy_tags and any(c.d.get("carry") for c in allies):
        lines.append("They can dive you under tower — track their jungler before you push.")

    if not lines:
        lines.append("Even matchup — farm safe, trade on cooldown advantage, and play for your team's win condition.")
    return lines


# --------------------------------------------------------------------------- #
# Power-spike timeline and mistakes flow straight from the data + archetype.
# --------------------------------------------------------------------------- #
def power_spikes(you: list[Champion], them: list[Champion]) -> list[Insight]:
    out: list[Insight] = []
    for side, team in (("You", you), ("Enemy", them)):
        for c in team:
            for s in c.d.get("spikes", []):
                out.append(Insight(f"{side}: {c.name} @ {s['when'].replace('_', ' ')} — {s['note']}",
                                    tag=f"spike_{side.lower()}"))
    return out


def mistakes(you: dict, them: dict, arch: str) -> list[Insight]:
    m: list[Insight] = []
    if you["scaling_index"] - them["scaling_index"] >= SCALE_GAP:
        m.append(Insight("Throwing the lead-up: taking a coinflip 50/50 fight when just farming wins you the game."))
        m.append(Insight("Contesting objectives without vision and dying for a dragon you didn't need yet."))
    if them["scaling_index"] - you["scaling_index"] >= SCALE_GAP:
        m.append(Insight("Playing passive and 'farming even' — that is losing, because they outscale."))
        m.append(Insight("Winning a fight and then recalling instead of taking a tower or objective with the timer."))
    if them["catcher"] or them["engage"] >= 3:
        m.append(Insight("Walking through the river/fog without vision and getting picked before the fight even starts."))
    if you["immobile_carries"]:
        m.append(Insight(f"{you['immobile_carries'][0]} positioning too aggressively and dying before dealing damage."))
    if not m:
        m.append(Insight("Fighting without a clear reason — every fight should be for an objective or a pick."))
    return m


# --------------------------------------------------------------------------- #
def build_brief(you_team: list[Champion], them_team: list[Champion],
                warnings: list[str], identity: dict,
                curated_rules: list[dict]) -> CoachingBrief:
    you, them = team_features(you_team), team_features(them_team)
    you_arch, you_labels = classify_archetype(you)
    them_arch, them_labels = classify_archetype(them)

    # Be honest when the note leans on auto-seeded (uncurated) champions.
    auto = [c.name for c in (you_team + them_team) if c.d.get("_auto")]
    if auto:
        shown = ", ".join(auto[:6]) + (" …" if len(auto) > 6 else "")
        warnings = warnings + [f"Limited data for {shown} — their advice is generic until curated."]

    you_wc, them_wc = win_conditions(you, them)
    brief = CoachingBrief(
        your_win_condition=you_wc,
        enemy_win_condition=them_wc,
        remember=remember_points(you, them, you_wc),
        lanes=lane_notes(you_team, them_team, curated_rules),
        identities=champion_identities(you_team, identity),
        power_spikes=power_spikes(you_team, them_team),
        mistakes=mistakes(you, them, you_arch),
        warnings=warnings,
        debug={"you": {**you, "archetype": you_labels},
               "them": {**them, "archetype": them_labels}},
    )
    return brief
