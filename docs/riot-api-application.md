# Riot API — Personal Key Application (copy-paste ready)

Fill this at developer.riotgames.com → **Register Product → Personal API Key**. Reviewers want:
a clear product, a real URL, honest endpoint justification, and evidence you'll follow policy.
Ours is a standard, approvable case (a coaching tool — same category as op.gg/Porofessor).

---

## Product name
`Coach Sticky-Note`  *(or your preferred name — keep it consistent everywhere)*

## Product URL
A public **GitHub repo** is the lowest-friction option — the README already describes the
project. (Make sure `.env` stays gitignored — it is.) If you'd rather not open the code, a
single landing page describing the tool also works. It does **not** need to be a deployed app.

## Product group / company
Leave blank or "Personal project".

## Is it commercial?
**No — non-commercial, personal project used by the developer and a small group of friends.**

## Product description  *(paste this)*

> Coach Sticky-Note is a free, non-commercial educational tool that helps lower-ranked League
> of Legends players improve their pre-game decision-making. Given two team compositions, it
> produces a concise coaching note — win conditions, lane-matchup advice, power spikes, and
> common mistakes — in the voice of a higher-ranked player briefing a friend before a game.
>
> To ground its advice in reality rather than opinion, it aggregates lane-phase statistics
> (gold and CS differentials, first-objective and plate timings) from public ranked match data,
> broken down by rank and patch. It also includes an optional companion that reads the player's
> own live game (via the local Live Client Data API) to show the relevant note automatically.
>
> The project is a personal, non-commercial tool for the developer and a small group of friends.
> It respects Riot's rate limits, stores only derived aggregate statistics (not bulk raw match
> data), verifies account ownership via the standard third-party verification code, and displays
> the required "isn't endorsed by Riot Games" notice.

## Which APIs you'll use  *(justify each — reviewers like specificity)*

- **account-v4** — resolve a player's Riot ID (gameName#tagLine) to a PUUID for their own match
  history and for account-ownership verification.
- **summoner-v4** — resolve summoner data (PUUID → account) needed by other endpoints.
- **league-v4** — read ranked tier, to (a) label aggregated stats by elo and (b) weight
  community-contributed data by verified rank. Also apex-tier lists to sample high-elo games.
- **match-v5** — read match and timeline data to compute the lane-phase statistics that ground
  the coaching advice.
- **lol-status-v4** — service status checks.

*(The live-game companion uses Riot's local Live Client Data API on 127.0.0.1:2999, which needs
no web API key — mention it for completeness, not as an endpoint request.)*

## Compliance checklist to state / follow
- **Non-commercial**, personal use.
- **Rate limits** respected (paced requests; no scraping of Riot or third-party sites).
- **Data handling**: store only derived aggregates, not a bulk copy of raw Riot data.
- **Legal notice**: the app shows "Coach Sticky-Note isn't endorsed by Riot Games and doesn't
  reflect the views or opinions of Riot Games or anyone officially involved in producing or
  managing Riot Games properties."
- No gambling, no real-time botting/automation that affects live games, no selling data.

---

### After approval
The Personal key doesn't expire every 24h and has higher limits — bump `accumulate.py --target`
up and the DB fills fast. Keep the key in `.env` (gitignored), never in `.env.example`.
