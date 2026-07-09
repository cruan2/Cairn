"""Auto-detect the current League game from the local client (the 'Porofessor' part).

Uses Riot's **Live Client Data API**: a REST endpoint the game itself serves on
https://127.0.0.1:2999 while you are in a match (from the loading screen onward).
It needs no API key and no auth — but it is localhost-only, which is exactly why a
Porofessor-style tool has to run on each player's own machine.

The cert is Riot's self-signed one, so we skip verification for that single localhost host.
"""
from __future__ import annotations
import json
import ssl
import urllib.request

LIVE_URL = "https://127.0.0.1:2999/liveclientdata/allgamedata"

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE  # Riot's localhost cert is self-signed; scope is one host


def _player_name(p: dict) -> str:
    return p.get("summonerName") or p.get("riotIdGameName") or p.get("riotId") or ""


def _active_name(data: dict) -> str:
    ap = data.get("activePlayer") or {}
    return ap.get("summonerName") or ap.get("riotIdGameName") or ap.get("riotId") or ""


def read_live_game(timeout: float = 2.0) -> tuple[list[str], list[str], dict] | None:
    """Return (your_champs, enemy_champs, meta) or None if no game is running.

    'Your' team is the one containing the active player; if that can't be resolved we
    fall back to ORDER (blue side) so the tool still shows something useful.
    """
    try:
        with urllib.request.urlopen(LIVE_URL, timeout=timeout, context=_CTX) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None  # game not running / API not up yet

    players = data.get("allPlayers") or []
    if len(players) < 2:
        return None

    me = _active_name(data)
    my_team = next((p.get("team") for p in players if _player_name(p) == me), None) or "ORDER"

    you = [p["championName"] for p in players if p.get("team") == my_team]
    enemy = [p["championName"] for p in players if p.get("team") != my_team]
    meta = {"active": me, "my_side": "Blue" if my_team == "ORDER" else "Red",
            "map": data.get("gameData", {}).get("mapName", "")}
    return you, enemy, meta
