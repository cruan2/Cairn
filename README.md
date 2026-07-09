# Coach Sticky-Note Engine

Simulates what an Emerald/Diamond player tells a Silver/Gold friend in Discord 30 seconds
before the game: **win conditions, lane dynamics, hidden matchup knowledge, champion
identity, and what NOT to do** — short and memorable, like a note handed over before you
walk on stage.

The hard design constraint that shapes everything: **the LLM must never invent League
knowledge.** A deterministic engine produces a fact-checked *brief*; the LLM only turns
that brief into natural coaching prose.

```
              OBJECTIVE DATA                    EXPERT KNOWLEDGE (curated)
         ┌───────────────────────┐        ┌──────────────────────────────────┐
         │ champions.json        │        │ identity.json   (what a champ     │
         │  roles, ranges,       │        │                  wants / avoids)  │
         │  curve, cc, tags      │        │ matchups.json   (hidden lane       │
         │ (Riot-derivable)      │        │                  knowledge)        │
         └───────────┬───────────┘        └───────────────┬──────────────────┘
                     │                                    │
                     ▼                                    ▼
             knowledge.py  ── team feature vectors (deterministic) ──┐
                     │                                               │
                     ▼                                               │
             analysis.py  ── RULES → CoachingBrief ◄─────────────────┘
                     │        (win conditions, remember, lanes,
                     │         identity, spikes, mistakes + evidence)
                     ▼
             synthesis.py
              ├─ render_sticky_note()   deterministic template  (ground truth, no key)
              └─ generate(use_llm=True) LLM = communication layer (rephrase only)
```

## 1. Architecture

Four stages, each with a single job. The value is in the **separation**, so no stage can
corrupt another's guarantees.

| Stage | File | Deterministic? | Job |
|---|---|---|---|
| Knowledge | `knowledge.py` | Yes | Load facts; aggregate a comp into a feature vector. |
| Analysis | `analysis.py` | Yes | Apply coaching rules → a `CoachingBrief` with evidence. |
| Synthesis | `synthesis.py` | Template yes / LLM no | Render the brief as the sticky note. |
| Interface | `cli.py`, `__init__.py` | — | CLI + `coach(you, enemy)` one-call API. |

The `CoachingBrief` (`model.py`) is the contract between the engine and the renderer. It is
the engine's *entire* output and the LLM's *only* allowed source of truth.

## 2. Data sources (and how they combine)

Three layers, deliberately separated so we always know which claims are objective and which
are opinion:

1. **`champions.json` — structured/objective attributes.** Roles, ranges, damage type,
   coarse power `curve`, CC, tags. Much of this is **Riot-API / Data-Dragon derivable**
   (base stats, ranges, ability CC flags, tags) and could be auto-seeded, then hand-checked.
2. **Champion statistics (future).** Win/pick rates and power-by-minute from an aggregator
   (e.g. a stats API) can *seed or sanity-check* the `curve` field — but we store coarse
   buckets, never raw win rates, because a Gold player doesn't need "51.3% at 14 min."
3. **`identity.json` — curated champion identity.** What a champion *wants* and *avoids*.
   Not derivable from stats. This is pure expert authoring (the Warwick/Viego/Nami lines).
4. **`matchups.json` — curated hidden matchup knowledge.** The "save Bubble for Leona's E"
   and "deny plates, don't match CS" tier of insight. Keyed by champion(s) on each side.
5. **LLM — communication only.** Turns the assembled brief into memorable prose.

**How they combine:** objective data drives *team-level* conclusions that must scale to any
comp (win conditions, power spikes, protect-the-carry) via tags/curve. Curated data drives
*specific* conclusions that can't be computed (lane dynamics, champion identity). Curated
always **beats** the generic engine when both have something to say — see `lane_notes()`,
where a matched `matchups.json` rule replaces the tag-generated line.

## 3. Objective data vs expert knowledge

The split is a first-class architectural boundary, not just tidiness:

- **Objective** (`champions.json`, stats): things with a defensible source. Wrong here =
  data bug, fixable by re-deriving.
- **Expert** (`identity.json`, `matchups.json`): opinions a Diamond player holds. Wrong
  here = coaching disagreement, fixable by editing a curated line.

Keeping them apart means we can regenerate the objective layer from Riot data without
touching a single hand-written insight, and we can audit every subjective claim in one place.

## 4. Knowledge representation

- **Tag ontology** (`data/tags.md`): a small controlled vocabulary (`poke`, `catcher`,
  `scaling`, `falloff`, `wombo`, `peel`…). Tags are the **join key** between data and rules,
  so a rule works for champions it has never seen as long as they're tagged.
- **Power curve** as `{early, mid, late}` 1–5 buckets: the single most important abstraction.
  `scaling_index = late − early` is what a coach means by "you outscale."
- **Named spikes** (`level_2`, `item_1`, `three_item`): a shared timeline vocabulary.
- **Matchup rules** as subset-matching: a rule fires when its `ally`/`enemy` champ sets are
  subsets of a lane. This lets rules be champion-level (`Karma vs Blitzcrank`) or full-pair
  (`Ezreal+Karma vs Caitlyn+Blitzcrank`) and stack naturally.
- **Insights carry their evidence.** Every conclusion stores the `reasons` that produced it
  (`--reasons` to see them). This makes the engine auditable *and* gives the LLM a fixed,
  closed set of facts it may rephrase.

## 5. Deterministic vs LLM

**Deterministic (rules):** anything where being wrong is harmful or the answer is derivable —
feature extraction, win-condition comparison, power-spike timeline, protect-the-carry
detection, curated-matchup lookup, "3 things to remember" scoring. Reproducible byte-for-byte.

**LLM (communication layer):** voice, memorability, deduping, and phrasing the fixed brief
like a real coach. Governed by `SYSTEM_PROMPT` in `synthesis.py`, which is explicit: *every
claim must come from the JSON brief; you are not the knowledge layer.* The deterministic
template is always the fallback, so a missing API key degrades gracefully — you still get a
correct (if drier) note. This is the "LLM narrates, rules decide" pattern; it's what keeps
the assistant from confidently saying something false about League.

## Usage

```powershell
# Deterministic note (no API key needed)
python -m coach.cli --example bot_poke_vs_pick

# Any two comps, any champion order
python -m coach.cli --you Ornn Sejuani Orianna Ezreal Karma `
                    --enemy Renekton LeeSin LeBlanc Caitlyn Blitzcrank

python -m coach.cli --example bot_poke_vs_pick --reasons   # show the evidence
python -m coach.cli --example bot_poke_vs_pick --brief     # structured JSON (the LLM's input)
python -m coach.cli --example bot_poke_vs_pick --llm       # LLM communication layer (needs ANTHROPIC_API_KEY)

python tests/test_smoke.py                                 # guardrail tests
```

```python
from coach import coach
print(coach(["Ornn","Sejuani","Orianna","Ezreal","Karma"],
            ["Renekton","LeeSin","LeBlanc","Caitlyn","Blitzcrank"]))
```

## Give it to your friends (Porofessor-style, no install)

The engine also ships as a **local companion app** that auto-detects your live game and
shows the note in your browser — like Porofessor. It reads Riot's **Live Client Data API**
(`https://127.0.0.1:2999`, no key, no login) which the game serves from the loading screen
onward. Because that API is localhost-only, the app runs on each player's own machine.

**Run from source:**
```powershell
python -m coach.serve      # opens http://127.0.0.1:7379 ; launch a game and it auto-detects
```

**Build a single .exe to hand to friends:**
```powershell
./build.ps1                # produces dist/CoachNote.exe (~8 MB, self-contained)
```
Send them that one file. They double-click it → a browser tab opens → they launch a League
game → the note appears and refreshes itself. No Python, no typing champs, nothing leaves
their PC. To stop it, they close the little console window.

Two things to tell them:
- **SmartScreen**: because the .exe is unsigned, Windows may say "Windows protected your PC."
  They click *More info → Run anyway*. (Code-signing removes this, but that's a scale-up step.)
- It shows the **example note until a game is running**, so they can see it works immediately.

Design note: this is the "overlay later" boundary respected. The *engine* is the product;
this companion is a thin delivery shell (stdlib `http.server` + the Live Client API). A true
always-on-top overlay or champ-select (LCU) detection are later upgrades that don't touch the
coaching logic.

## The data flywheel: a daily game that curates the engine

The hardest part to scale is the *curated* knowledge. So `game/` is a Rankdle-style **daily
web game** ("Guess the Win Condition") that crowdsources it — and defends against noise with
**optional Riot login**: anonymous votes count little, self-reported rank counts more (capped),
a Riot-verified rank counts fully. Crowd-vs-engine disagreement auto-flags a rule to fix, so the
game QAs the engine while it collects data. Full design: [docs/gamified-collection.md](docs/gamified-collection.md).

```powershell
pip install -r requirements.txt
python -m game.server            # http://127.0.0.1:5000
$env:RIOT_API_KEY="RGAPI-..."    # optional: enables account verification
```

## What's an MVP shortcut (and how it grows)

- **~17 champions, hand-authored.** Grows by (a) auto-seeding `champions.json` from Data
  Dragon, (b) crowd/expert-authoring `identity.json` + `matchups.json`. The engine already
  handles unknown champs gracefully (warns, omits that slot).
- **Rules are tuned on one archetype clash.** The generic tag engine covers the long tail;
  curated rules cover the sharp cases. Add coverage by writing data, not code.
- **No Riot API client yet.** The champion schema is designed to be Data-Dragon-shaped so a
  loader can populate it. Live-game/roster ingestion is a later interface concern — the
  engine is deliberately built and validated first.
