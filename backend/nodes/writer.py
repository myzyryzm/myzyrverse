"""Writer: drafts the chapter from the approved outline, or revises it against the critique."""

from __future__ import annotations

from ..state import RunState
from .common import build_prompt, call, system_prompt, usage


async def writer(state: RunState) -> dict:
    history = state.get("draft_history") or []
    sections = [
        ("Approved research (use for texture, not lectures)", state.get("research_notes", "")),
        ("Approved chapter outline", state.get("chapter_outline", "")),
    ]
    if history:
        sections += [("Previous draft", history[-1]), ("Critique of the previous draft", state.get("critique_notes", ""))]
        task = ("Revise the previous draft into a stronger chapter. Fix every issue in the critique and any author notes. "
                "Keep what works. Output the full revised chapter.")
    else:
        task = f"Write the chapter from {state.get('pov') or 'the POV character'}'s point of view, following the outline."
    prompt = build_prompt(state, *sections, task=task)
    result = await call("writer", state, prompt, sys_prompt=system_prompt("writer", tone=True))
    return {"draft_prose": result.text, "author_notes": "", "usage": usage("writer", result)}
