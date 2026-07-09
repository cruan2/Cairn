"""Turns a CoachingBrief into the sticky note.

Two renderers, one contract: **neither may introduce a League fact that isn't already
in the brief.**

- `render_sticky_note` — deterministic template. No API key, fully reproducible. This is
  the ground truth and the fallback.
- `build_llm_messages` — constructs a tightly-scoped prompt so an LLM can improve the
  *phrasing* (memorable, in a coach's voice) while being forbidden from adding knowledge.
  The brief is passed as the only source of truth; the system prompt makes that a rule.
"""
from __future__ import annotations
import json
from .model import CoachingBrief


# --------------------------------------------------------------------------- #
# Deterministic renderer (the source of truth, always available).
# --------------------------------------------------------------------------- #
def render_sticky_note(b: CoachingBrief, show_reasons: bool = False) -> str:
    L: list[str] = []
    L.append("GAME PLAN")
    L.append("")
    L.append("Your win condition:")
    L.append(_wrap(b.your_win_condition.text))
    if show_reasons:
        L += [f"    · {r}" for r in b.your_win_condition.reasons if r]
    L.append("")
    L.append("Enemy win condition:")
    L.append(_wrap(b.enemy_win_condition.text))
    L.append("")
    L.append("Remember:")
    for i, pt in enumerate(b.remember, 1):
        L.append(f"{i}. {pt.text}")
        if show_reasons:
            L += [f"    · {r}" for r in pt.reasons if r]
    L.append("")
    L.append("Lane advice:")
    for lane in b.lanes:
        tag = "  [curated]" if lane.curated else ""
        L.append(f"  {lane.lane.upper()} — {lane.ally} vs {lane.enemy}{tag}")
        for ln in lane.lines:
            L.append(f"    {ln}")
    L.append("")
    L.append("Champion identity (your team):")
    for idn in b.identities:
        L.append(f"  {idn.name}: {idn.note}")
        if idn.wants:
            L.append(f"    Wants:  {idn.wants}")
        if idn.avoids:
            L.append(f"    Avoid:  {idn.avoids}")
    L.append("")
    L.append("Don't:")
    for m in b.mistakes[:4]:
        L.append(f"  - {m.text}")
    if b.warnings:
        L.append("")
        L.append("Notes:")
        for w in b.warnings:
            L.append(f"  ! {w}")
    return "\n".join(L)


def _wrap(text: str, width: int = 92) -> str:
    words, line, out = text.split(), "", []
    for w in words:
        if len(line) + len(w) + 1 > width:
            out.append(line)
            line = w
        else:
            line = f"{line} {w}".strip()
    out.append(line)
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# LLM seam — the communication layer. It rephrases; it does not know League.
# --------------------------------------------------------------------------- #
SYSTEM_PROMPT = """\
You are a Diamond-level League of Legends player writing a 30-second pre-game note to a \
Gold friend who knows the basics but lacks pattern recognition.

ABSOLUTE RULE: every strategic claim must come from the JSON brief you are given. You are \
the COMMUNICATION layer, not the knowledge layer. Do NOT add champion facts, matchup \
knowledge, item builds, or numbers that are not in the brief. If it's not in the brief, \
it does not go in the note.

Voice: short, memorable, direct — like a coach handing over a note before the player walks \
on stage. No filler ("farm more", "play safe", "take objectives" on their own). No hedging. \
Keep the section structure of the brief. Prefer the curated lane lines verbatim or nearly so.\
"""


def build_llm_messages(b: CoachingBrief) -> list[dict]:
    """Messages for the Claude Messages API. The brief is the ONLY source of truth."""
    brief_json = json.dumps(_brief_to_dict(b), indent=2)
    user = (
        "Rewrite this structured brief as the sticky note. Keep it tight. Do not introduce "
        "anything not present here.\n\n```json\n" + brief_json + "\n```"
    )
    return [{"role": "user", "content": user}]


def _brief_to_dict(b: CoachingBrief) -> dict:
    return {
        "your_win_condition": b.your_win_condition.text,
        "enemy_win_condition": b.enemy_win_condition.text,
        "remember": [pt.text for pt in b.remember],
        "lanes": [{"lane": l.lane, "ally": l.ally, "enemy": l.enemy,
                   "lines": l.lines, "curated": l.curated} for l in b.lanes],
        "champion_identity": [{"name": i.name, "identity": i.note,
                               "wants": i.wants, "avoids": i.avoids} for i in b.identities],
        "dont": [m.text for m in b.mistakes[:4]],
        "warnings": b.warnings,
    }


DEFAULT_MODELS = {"anthropic": "claude-opus-4-8", "ollama": "llama3.1"}


def generate(b: CoachingBrief, backend: str = "template", model: str | None = None) -> str:
    """Render the note via the chosen backend.

    backend="template"  -> deterministic, free, always available (the fallback).
    backend="ollama"    -> local LLM on your machine, no API credits.
    backend="anthropic" -> Anthropic API (uses ANTHROPIC_API_KEY, costs credits).

    Any backend failure falls back to the deterministic template — the note never fails.
    """
    if backend == "template":
        return render_sticky_note(b)
    model = model or DEFAULT_MODELS.get(backend)
    if backend == "ollama":
        return _render_ollama(b, model)
    if backend == "anthropic":
        return _render_anthropic(b, model)
    raise ValueError(f"unknown backend '{backend}'")


def _render_ollama(b: CoachingBrief, model: str, host: str = "http://localhost:11434") -> str:
    """Talk to a local Ollama server over its HTTP API. Stdlib only — no dependencies."""
    import urllib.request
    import urllib.error
    payload = {
        "model": model,
        "stream": False,
        "options": {"temperature": 0.4},
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + build_llm_messages(b),
    }
    req = urllib.request.Request(
        host + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["message"]["content"].strip()
    except urllib.error.URLError as e:
        return (render_sticky_note(b) +
                f"\n\n[Ollama not reachable at {host} ({e.reason}). Is `ollama serve` running "
                f"and `{model}` pulled? Showed deterministic note instead.]")
    except Exception as e:
        return render_sticky_note(b) + f"\n\n[Ollama error: {e}; showed deterministic note]"


def _render_anthropic(b: CoachingBrief, model: str) -> str:
    try:
        # Imported dynamically so packagers (PyInstaller) don't bundle the whole SDK into
        # the friend-facing app — the exe only ever uses the template/ollama backends.
        import importlib
        anthropic = importlib.import_module("anthropic")
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=model, max_tokens=1200, system=SYSTEM_PROMPT,
            messages=build_llm_messages(b),
        )
        return resp.content[0].text
    except Exception as e:  # missing key/package/etc. — never fail the note
        return render_sticky_note(b) + f"\n\n[Anthropic unavailable: {e}; showed deterministic note]"
