# Gamified Data Collection ("the data collection IS the game")

## Why this is the right idea

The engine's bottleneck is not code — it's the **curated subjective layer**: power `curve`,
coaching `tags`, champion `identity`, and `matchups`. The Data Dragon seeder gives us 173
champions but flat 3/3/3 curves and no hidden knowledge. Curation is expensive *and* it's
exactly the kind of judgment that many decent players hold in their heads. So: harvest it
from players, and make giving it fun. A "Game With A Purpose" (GWAP) both **collects** and
**validates** data as a side effect of play.

This also fits what we already built: the CoachNote app runs during real games, so we can ask
a player one sharp question about a matchup they *just experienced* — the highest-signal,
lowest-friction moment possible.

## What we're collecting (maps 1:1 to the existing schemas)

| Target field | Game question | Aggregates into |
|---|---|---|
| `curve.early/late` | "Did this champ want the game shorter or longer?" (slider) | median → early/late buckets |
| `tags` | "Pick the 3 words that fit this champ" (from the ontology) | agreement → validated tags |
| `identity.wants/avoids` | "One thing this champ WANTS / must AVOID" (choices + free text) | vote/cluster → canonical line |
| `matchups.rules[].lines` | "What decided this lane?" for a real matchup you played | duel-vote → top line ships |

## The Rankdle insight (why "guess-the-X" is the right shell)

Rankdle / GuessTheRank / GuessMyRank show a gameplay clip and ask **"guess the player's
rank."** Daily puzzle, 2 stars for exact / 1 for one-off, streaks, leaderboard, a Wordle-style
shareable score. It's addictive — and, not by accident, it is a **crowdsourced labeling
engine**: the crowd's aggregate guess *is* a label, and how close you land to the consensus
*is* a skill signal.

We steal the shell and swap the payload. Instead of "guess the rank," we ask questions whose
answers are the coaching data we lack — but keep the daily/streak/stars/leaderboard loop that
makes people show up. Three properties fall out for free:

1. **Self-validating.** High inter-player agreement on a matchup = a high-confidence datum.
   No separate labeling pass.
2. **It measures the labeler.** Score each player against the emerging consensus (and against
   gold-standard items). People who consistently match the *high-rank* consensus get weighted
   up — we derive a "coaching trust" score **without even needing Riot rank verification** to
   start. Rank verification later just sharpens it.
3. **It doubles as engine QA.** Our engine already *outputs* win-condition/matchup calls. Seed
   each puzzle with the engine's answer; when crowd-consensus disagrees with the engine, that
   is an automatic bug report against a specific rule. The game improves the engine while it
   collects data.

```
 engine makes a call ──▶ becomes a puzzle ──▶ crowd guesses ──▶ consensus
        ▲                                                          │
        │  agree: +confidence          disagree: flag the rule ◀───┘
        └──────────────  fix rule / update curated data  ◀─────────┘
```

## Objective ground truth beats consensus (the flagship mode)

Grading a *judgment* ("which team should scale?") against a model or a crowd is the
MobaTrainer failure: there's often no objective right answer, so being told you're "wrong"
feels contestable and bad. Rankdle is satisfying because the answer is a **fact you can look
up** (the clip's real rank).

So the flagship daily uses facts, not opinions, and shrinks the unit to something *readable* —
a **2v2 lane** — with questions answered by the real **match timeline** (`game/matches.py`):

- "Who was up gold in bot at **10:00**?"  → fact from `participantFrames.totalGold`
- "Who got the **first bot-lane kill**?"  → fact from `CHAMPION_KILL` events
- "Who **won** the game?"                 → fact from the result

Being wrong means the real game went the other way — ego-safe, and we link the match as proof.

**The data this yields is the good part.** Aggregate the same matchup across many games and you
get an *objective* label: *"Caitlyn+Blitz is up gold at 10 in 68% of games."* That verifies which
side actually should be winning a lane — grounding the engine's `curve` and matchup difficulty in
reality instead of vibes. `extract_facts` is a pure function over match-v5 JSON (offline-testable);
the Riot fetchers are gated on a key.

Subjective knowledge (champion identity, "save Bubble for Leona") is *not* forced into this mold —
it lives in a clearly-labelled **opinion** mode (advice duels), never graded as right/wrong.

## Game modes (all "guess-the-X", all harvest a schema field)

| Mode | The hook (what the player does) | What it harvests |
|---|---|---|
| **Guess the Win Condition** | See two comps → "who wants the game to go LONG?" | `curve` / scaling labels; engine QA |
| **Higher Elo Says** | Two advice cards for a matchup → pick the better one | `matchups.rules[].lines` ranking |
| **Rank the Lane** | See a lane matchup → "how hard is this for you? 1–5" | matchup difficulty; `identity` signals |
| **Spot the Mistake** | Short clip/scenario → "what did they do wrong?" (choices) | common-mistakes / `Don't` lines |

Scoring mirrors Rankdle: **2 stars** if you match consensus/gold, **1** if adjacent, **0**
otherwise; keep a **streak** by clearing ≥2 stars; a daily leaderboard by stars *and* by
"agreement with Diamond+ consensus." That last axis is the one quietly building your dataset.

## Core mechanics (pick 1 to start, add later)

1. **Contextual post-game micro-question** *(recommended MVP)*. The app already detects the
   game; after it ends, ask ONE question about a lane that was on the board. Fresh ground
   truth, one tap, zero context-switch. This is the "collection is the game" move.
2. **Agreement game (ESP-style)**. Two+ players independently answer the same prompt; a match
   promotes the datum to high-confidence. Rewards agreement, filters noise automatically.
3. **Advice duel**. Show two candidate lines for a matchup; players vote the better one; Elo
   ranks them; the top line becomes canonical. Great for *phrasing* quality of `matchups.json`.
4. **Curve calibration**. The single highest-value field, harvested with one slider.

## Trust tiers & the (optional) Riot login  — implemented in `game/`

The failure mode of any open data game is noise from players who don't know the game. The fix
is that **login is optional but changes how much your vote counts** (`game/trust.py`):

| Tier | How | Weight | Rationale |
|---|---|---|---|
| **anonymous** | no login | `0.25` | counted, but can't move consensus alone |
| **self_reported** | pick your rank | `0.6 × rank`, **capped at Gold** | can't *claim* your way to influence |
| **verified** | Riot ownership proof | `1.0 × rank` (Iron 0.6 → Challenger 3.5) | the votes we actually trust |

On top of tier sits a **reliability** multiplier (honeypots / past agreement), so even a verified
Diamond who spams gets down-weighted. Tier sets the ceiling; reliability polices behaviour. Demo
proof: 3 anonymous votes (0.75) lose to 1 anon + 1 Diamond (0.97).

### Why not "Log in with Riot"?
Riot Sign-On (RSO / real OAuth) requires an **approved production application** — you don't get
it with a hobby key. So verification uses the **third-party-code ownership flow** (`game/riot.py`),
the same trick op.gg/Porofessor use:

1. Player enters their **Riot ID** (`Name#TAG`) → we resolve puuid → summonerId (account-v4 →
   summoner-v4; note: summoner-*by-name* is deprecated).
2. We issue a nonce; they paste it into **League client → Settings → Verification**.
3. We read it back via `third-party-code/by-summoner`; match ⇒ they own the account.
4. We fetch their ranked tier (league-v4) → that sets their weight.

Caveats to plan around: personal dev keys **expire every 24h** and are rate-limited — a real
deployment needs a production key. Without any key, `game/riot.py` reports verification off and
players simply use self-report/anonymous.

## Trust & quality (this is what makes it usable, not just data exhaust)

The product's whole premise is *"what a Master+ tells a Gold."* So contributor rank is a
first-class signal:

- **Verify rank via the Riot API** (summoner → ranked tier). Weight every contribution by
  verified rank; show rank badges. A Diamond's vote outweighs a Bronze's *by design*.
- **Gold-standard honeypots.** Mix in known-answer questions to score each contributor's
  reliability, and down-weight the unreliable.
- **Promotion gate.** Nothing reaches the engine's canonical JSON until N agreeing,
  high-trust answers clear a review queue. Raw contributions and canonical data are separate.
- **Provenance.** Every canonical datum stores what supported it — same "claims carry their
  evidence" ethos the engine already uses (`Insight.reasons`). Auditable, reversible.

## The flywheel

```
 friends run CoachNote  ──▶  it asks a contextual question about a game they played
        ▲                                     │
        │                                     ▼
 better notes attract more players     raw contributions (rank-weighted)
        ▲                                     │
        │                                     ▼
 engine reads canonical JSON  ◀──  aggregate + validate + promote (review gate)
```

## Architecture to support it

- **Thin client = today's app, extended.** It already reads the live game. Add: (a) fetch the
  latest *canonical* data snapshot so friends' engines improve without rebuilding the exe, and
  (b) `GET /task` + `POST /answer` for the question loop.
- **One small backend service** (the only thing you host): task selection (personalized to the
  champs a player actually plays), rank verification, a contributions store, and an aggregation
  worker that promotes validated data into versioned `champions/identity/matchups` JSON.
- **Optional web version** — a browser "coaching cards" game for people who want to grind
  without playing League, widening the contributor pool. This is the literal lessgames-style
  site; the engine and data schemas are identical to the app's.

## Smallest useful MVP (no backend required at first)

1. In the app, after a detected game, show **one** question: a curve slider + "what decided
   this lane?" for one matchup that was on the board.
2. Append the answer to a local `contributions.jsonl` (schema below). "Sync" can start as
   dumb as: the file posts to a single serverless endpoint, or even a Google Form — defer the
   real backend until volume justifies it.
3. You periodically run an aggregation script that turns validated contributions into edits to
   `identity.json` / `matchups.json` / curve fields, gated by your review.

```jsonc
// one line per contribution in contributions.jsonl
{
  "ts": "2026-07-09T20:00:00Z",
  "reporter_rank": "EMERALD",          // verified via Riot API, or self-reported at first
  "kind": "matchup_line",              // curve | tags | identity | matchup_line
  "subject": {"ally": ["Ezreal","Karma"], "enemy": ["Caitlyn","Blitzcrank"], "lane": "bot"},
  "value": "Deny plates, not CS — a CS deficit is fine if she can't take the tower.",
  "game_id": "NA1_1234567890"          // ties the claim to a real game they played
}
```

## Guardrails

- **Riot policy / ToS.** The Riot API and Live Client API must be used within Riot's developer
  terms. Friends-scale personal use is fine; storing summoner data means keeping it minimal
  and consented. Revisit before any public launch.
- **Garbage-in.** The rank weighting + agreement gate is not optional — without it a gamified
  pipeline mostly collects noise. Ship the validation with the collection, not after.
