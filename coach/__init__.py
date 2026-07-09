"""Coaching engine: comps in, structured brief out, sticky note rendered.

Pipeline:  champions.json + identity.json + matchups.json
              -> knowledge (features)  [deterministic]
              -> analysis (rules)      [deterministic]  -> CoachingBrief
              -> synthesis (template | LLM communication layer)
"""
from .knowledge import load_champions, load_identity, load_matchups, normalize_comp
from .analysis import build_brief
from .synthesis import render_sticky_note, generate, build_llm_messages


def coach(you: list[str], enemy: list[str], backend: str = "template",
          model: str | None = None) -> str:
    """One-call convenience: two comps (lists of champion names) -> sticky note text.

    backend: "template" (free/local), "ollama" (local LLM), or "anthropic" (API).
    """
    champs = load_champions()
    you_team, w1 = normalize_comp(you, champs)
    them_team, w2 = normalize_comp(enemy, champs)
    brief = build_brief(you_team, them_team, w1 + w2, load_identity(), load_matchups())
    return generate(brief, backend=backend, model=model)


__all__ = ["coach", "build_brief", "render_sticky_note", "generate",
           "load_champions", "load_identity", "load_matchups", "normalize_comp",
           "build_llm_messages"]
