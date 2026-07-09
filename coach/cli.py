"""CLI: generate a sticky note from two comps.

Examples (PowerShell):
  python -m coach.cli --you Ornn Sejuani Orianna Ezreal Karma --enemy Renekton LeeSin LeBlanc Caitlyn Blitzcrank
  python -m coach.cli --example bot_poke_vs_pick --reasons
  python -m coach.cli --example bot_poke_vs_pick --llm      # uses ANTHROPIC_API_KEY if set
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

try:  # make em-dashes etc. survive Windows' default cp1252 console
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from .knowledge import load_champions, load_identity, load_matchups, normalize_comp
from .analysis import build_brief
from .synthesis import render_sticky_note, generate

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def _load_example(name: str) -> tuple[list[str], list[str]]:
    with open(EXAMPLES / f"{name}.json", encoding="utf-8") as fh:
        d = json.load(fh)
    return d["you"], d["enemy"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="League coaching sticky-note generator")
    ap.add_argument("--you", nargs="+", help="your 5 champions (any order)")
    ap.add_argument("--enemy", nargs="+", help="enemy 5 champions (any order)")
    ap.add_argument("--example", help="load examples/<name>.json instead of --you/--enemy")
    ap.add_argument("--reasons", action="store_true", help="show the evidence behind each claim")
    ap.add_argument("--local", action="store_true", help="use a local Ollama model (no API credits)")
    ap.add_argument("--llm", action="store_true", help="use the Anthropic API (needs ANTHROPIC_API_KEY, costs credits)")
    ap.add_argument("--model", help="override the model name for the chosen backend")
    ap.add_argument("--brief", action="store_true", help="dump the structured brief as JSON (for the LLM/debug)")
    args = ap.parse_args(argv)

    if args.example:
        you, enemy = _load_example(args.example)
    elif args.you and args.enemy:
        you, enemy = args.you, args.enemy
    else:
        ap.error("provide --example NAME or both --you ... and --enemy ...")

    champs = load_champions()
    you_team, w1 = normalize_comp(you, champs)
    them_team, w2 = normalize_comp(enemy, champs)
    brief = build_brief(you_team, them_team, w1 + w2, load_identity(), load_matchups())

    if args.brief:
        from .synthesis import _brief_to_dict
        print(json.dumps({**_brief_to_dict(brief), "_features": brief.debug}, indent=2))
        return 0

    backend = "ollama" if args.local else "anthropic" if args.llm else "template"
    if backend == "template":
        print(render_sticky_note(brief, show_reasons=args.reasons))
    else:
        print(generate(brief, backend=backend, model=args.model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
