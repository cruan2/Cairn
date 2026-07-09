"""'Guess the Win Condition' — a Rankdle-style puzzle built from the coaching engine.

The player sees two comps and guesses which team wants the game to go long. The engine's own
read seeds the puzzle; the crowd's aggregate answer becomes the label. Where the crowd and the
engine disagree, we get a free bug report against a specific rule.

Demo:  python -m game.puzzle
"""
from __future__ import annotations
import random
from dataclasses import dataclass, field

from coach.knowledge import load_champions, normalize_comp, team_features

OPTIONS = ["your_scales", "enemy_scales", "even"]
LABELS = {"your_scales": "Blue wants it LONG (they outscale)",
          "enemy_scales": "Red wants it LONG (they outscale)",
          "even": "Even — no clear scaling side"}
SCALE_GAP = 0.75  # same threshold the engine uses


@dataclass
class Puzzle:
    puzzle_id: str
    blue: list[str]
    red: list[str]
    question: str = "Which team wants the game to go LONG?"
    options: list[str] = field(default_factory=lambda: list(OPTIONS))
    engine_answer: str = ""      # the engine's read — the seed hypothesis (hidden from player)
    engine_gap: float = 0.0


def engine_read(blue: list[str], red: list[str]) -> tuple[str, float]:
    """The engine's own scaling call — the hypothesis the crowd will confirm or overturn."""
    champs = load_champions()
    b, _ = normalize_comp(blue, champs)
    r, _ = normalize_comp(red, champs)
    gap = team_features(b)["scaling_index"] - team_features(r)["scaling_index"]
    if gap >= SCALE_GAP:
        return "your_scales", round(gap, 2)
    if gap <= -SCALE_GAP:
        return "enemy_scales", round(gap, 2)
    return "even", round(gap, 2)


def make_puzzle(blue: list[str], red: list[str], puzzle_id: str = "daily") -> Puzzle:
    ans, gap = engine_read(blue, red)
    return Puzzle(puzzle_id=puzzle_id, blue=blue, red=red, engine_answer=ans, engine_gap=gap)


def score(guess: str, truth: str) -> int:
    """Rankdle-style stars: 2 exact, 1 adjacent (involving 'even'), else 0."""
    if guess == truth:
        return 2
    adjacent = {"even"} & {guess, truth}  # scaling<->even is 'one off'; blue<->red is not
    return 1 if adjacent and guess != truth else 0


@dataclass
class Consensus:
    answer: str
    agreement: float          # share of (rank-weighted) votes for the winning answer
    n: int
    engine_agrees: bool
    flag_engine_bug: bool     # crowd is confident AND disagrees with the engine -> bug report


def tally(votes: list[tuple[str, float]], engine_answer: str,
          confident_at: float = 0.66) -> Consensus:
    """Aggregate (answer, weight) votes into a rank-weighted consensus.

    weight = a contributor's trust (e.g. derived from rank / past agreement). This is where
    'Diamond+ says' enters: their votes simply weigh more.
    """
    tot: dict[str, float] = {o: 0.0 for o in OPTIONS}
    for ans, w in votes:
        tot[ans] = tot.get(ans, 0.0) + w
    total = sum(tot.values()) or 1.0
    winner = max(tot, key=lambda k: tot[k])
    agreement = tot[winner] / total
    engine_agrees = winner == engine_answer
    return Consensus(
        answer=winner, agreement=round(agreement, 2), n=len(votes),
        engine_agrees=engine_agrees,
        flag_engine_bug=(agreement >= confident_at and not engine_agrees),
    )


# --------------------------------------------------------------------------- #
def _demo():
    blue = ["Ornn", "Sejuani", "Orianna", "Ezreal", "Karma"]     # scaling/teamfight
    red = ["Renekton", "LeeSin", "LeBlanc", "Caitlyn", "Blitzcrank"]  # early/pick
    pz = make_puzzle(blue, red)
    print("PUZZLE:", pz.question)
    print("  Blue:", " ".join(pz.blue))
    print("  Red: ", " ".join(pz.red))
    print("  Options:", [LABELS[o] for o in pz.options])
    print(f"  [engine seed] {pz.engine_answer}  (scaling gap {pz.engine_gap})")

    # Simulate a player answering, scored against the engine seed (provisional gold).
    guess = "your_scales"
    print(f"\nPlayer guesses '{guess}' -> {score(guess, pz.engine_answer)} stars")

    # Simulate a rank-weighted crowd (weights stand in for contributor trust).
    random.seed(7)
    votes = ([("your_scales", 3.0)] * 7 +   # Diamonds agreeing, weighted 3
             [("even", 1.0)] * 2 +          # a couple of lower-trust 'even'
             [("enemy_scales", 1.0)])
    c = tally(votes, pz.engine_answer)
    print(f"\nCONSENSUS: {c.answer}  agreement={c.agreement}  n={c.n}  "
          f"engine_agrees={c.engine_agrees}  flag_bug={c.flag_engine_bug}")
    print("  -> crowd confirms the engine; this datum's confidence goes UP.")


if __name__ == "__main__":
    _demo()
