"""Smoke + guardrail tests. Run: python -m pytest -q  (or python tests/test_smoke.py)"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from coach import coach, load_champions, load_identity, load_matchups, normalize_comp
from coach.analysis import build_brief

BLUE = ["Ornn", "Sejuani", "Orianna", "Ezreal", "Karma"]
RED = ["Renekton", "LeeSin", "LeBlanc", "Caitlyn", "Blitzcrank"]


def _brief(you, them):
    champs = load_champions()
    yt, w1 = normalize_comp(you, champs)
    tt, w2 = normalize_comp(them, champs)
    return build_brief(yt, tt, w1 + w2, load_identity(), load_matchups())


def test_scaling_team_gets_scaling_win_condition():
    b = _brief(BLUE, RED)
    assert "slow" in b.your_win_condition.text.lower() or "late" in b.your_win_condition.text.lower()
    assert "early" in b.enemy_win_condition.text.lower()


def test_scaling_side_is_consistent_when_swapped():
    # Phrasing is perspective-relative, but the same team must be tagged the scaling one.
    def scaling_side(you, them):
        b = _brief(you, them)
        return "slow" in b.your_win_condition.text.lower() or "late" in b.your_win_condition.text.lower()
    assert scaling_side(BLUE, RED) is True    # BLUE reads as the scaling team
    assert scaling_side(RED, BLUE) is False   # RED reads as the early team


def test_curated_bot_matchup_fires():
    b = _brief(BLUE, RED)
    bot = next(l for l in b.lanes if l.lane == "bot")
    assert bot.curated
    assert any("match Caitlyn's CS" in ln for ln in bot.lines)


def test_exactly_three_remember_points():
    assert len(_brief(BLUE, RED).remember) == 3


def test_unknown_champion_is_warned_not_crashed():
    out = coach(["Ornn", "Sejuani", "Orianna", "Ezreal", "Zyra_Fake"], RED)
    assert "Unknown champion" in out


def test_identity_only_carries_get_wants():
    b = _brief(BLUE, RED)
    ez = next(i for i in b.identities if i.name == "Ezreal")
    ornn = next(i for i in b.identities if i.name == "Ornn")
    assert ez.wants and not ornn.wants  # Ezreal is a carry, Ornn is not


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    ok = 0
    for fn in fns:
        try:
            fn(); ok += 1; print(f"PASS {fn.__name__}")
        except Exception:
            print(f"FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{ok}/{len(fns)} passed")
    sys.exit(0 if ok == len(fns) else 1)
