"""Optional Riot account-ownership verification (no RSO needed).

Flow (the op.gg / Porofessor trick):
  1. Resolve a Riot ID (gameName#tagLine) -> puuid -> summonerId.
  2. Issue the player a random nonce and tell them to paste it into League client:
     Settings -> Verification.
  3. Read it back via the third-party-code endpoint; if it matches, they own the account.
  4. Fetch their ranked tier -> that becomes their trust weight.

Requires a Riot API key in RIOT_API_KEY. Without one, verification is unavailable and the app
falls back to self-reported / anonymous tiers. Note: personal dev keys expire every 24h and are
rate-limited — a real deployment needs a production key.

Riot summoner-by-name is deprecated, so we use the Riot ID + account-v4 path.
"""
from __future__ import annotations
import json
import os
import urllib.error
import urllib.parse
import urllib.request

# platform routing (summoner/league) -> regional cluster (account-v4)
REGION_CLUSTER = {
    "na1": "americas", "br1": "americas", "la1": "americas", "la2": "americas", "oc1": "americas",
    "euw1": "europe", "eun1": "europe", "tr1": "europe", "ru": "europe",
    "kr": "asia", "jp1": "asia",
}


def has_key() -> bool:
    return bool(os.environ.get("RIOT_API_KEY"))


# Riot's edge WAF rejects the default "Python-urllib" User-Agent with a generic 403
# ("error code: 1010"), which looks exactly like an auth failure. A browser-like UA is required.
_USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={
        "X-Riot-Token": os.environ["RIOT_API_KEY"],
        "User-Agent": _USER_AGENT,
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read().decode("utf-8"))


def resolve_puuid(riot_id: str, platform: str) -> str:
    """riot_id 'Name#TAG' -> puuid (the modern identifier). Raises on not-found/bad key."""
    if "#" not in riot_id:
        raise ValueError("Enter your Riot ID as Name#TAG")
    name, tag = riot_id.split("#", 1)
    cluster = REGION_CLUSTER.get(platform, "americas")
    acct = _get(f"https://{cluster}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/"
                f"{urllib.parse.quote(name)}/{urllib.parse.quote(tag)}")
    return acct["puuid"]


def resolve_summoner(riot_id: str, platform: str) -> dict:
    """riot_id 'Name#TAG' -> {puuid, summoner_id}. summoner_id may be None (Riot is retiring it)."""
    puuid = resolve_puuid(riot_id, platform)
    summ = _get(f"https://{platform}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}")
    return {"puuid": puuid, "summoner_id": summ.get("id")}


def read_third_party_code(summoner_id: str, platform: str) -> str:
    try:
        return _get(f"https://{platform}.api.riotgames.com/lol/platform/v4/"
                    f"third-party-code/by-summoner/{summoner_id}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return ""  # no code set yet
        raise


def _tier_from_entries(entries: list[dict]) -> str | None:
    solo = next((e for e in entries if e.get("queueType") == "RANKED_SOLO_5x5"), None)
    chosen = solo or (entries[0] if entries else None)
    return chosen["tier"] if chosen else None  # e.g. "DIAMOND", or None if unranked


def fetch_rank_by_puuid(puuid: str, platform: str) -> str | None:
    entries = _get(f"https://{platform}.api.riotgames.com/lol/league/v4/entries/by-puuid/{puuid}")
    return _tier_from_entries(entries)


def fetch_rank(summoner_id: str, platform: str) -> str | None:
    entries = _get(f"https://{platform}.api.riotgames.com/lol/league/v4/"
                   f"entries/by-summoner/{summoner_id}")
    return _tier_from_entries(entries)


_APEX_PATH = {"CHALLENGER": "challengerleagues", "GRANDMASTER": "grandmasterleagues",
              "MASTER": "masterleagues"}


def apex_league(tier: str, platform: str) -> list[dict]:
    """Solo-queue apex ladder entries. Each entry has puuid (modern) or summonerId (older)."""
    path = _APEX_PATH[tier.upper()]
    data = _get(f"https://{platform}.api.riotgames.com/lol/league/v4/{path}/by-queue/RANKED_SOLO_5x5")
    return data.get("entries", [])


def puuid_from_summoner_id(summoner_id: str, platform: str) -> str | None:
    s = _get(f"https://{platform}.api.riotgames.com/lol/summoner/v4/summoners/{summoner_id}")
    return s.get("puuid")


def verify_ownership(summoner_id: str, platform: str, nonce: str) -> tuple[bool, str | None]:
    """Return (owns_account, rank_tier). rank is None if unranked."""
    code = (read_third_party_code(summoner_id, platform) or "").strip()
    if code != nonce:
        return False, None
    return True, fetch_rank(summoner_id, platform)
