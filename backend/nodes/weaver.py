"""Weaver: the beat sheet for a chapter run."""

from __future__ import annotations

from ..state import PENDING_OUTLINE_REVIEW, RunState
from .common import build_prompt, call, system_prompt, usage


async def weaver(state: RunState) -> dict:
    prompt = build_prompt(state, ("Approved research", state.get("research_notes", "")),
                          task="Write the beat sheet for this chapter.")
    result = await call("weaver", state, prompt, sys_prompt=system_prompt("weaver"))
    return {"chapter_outline": result.text, "review_status": PENDING_OUTLINE_REVIEW,
            "author_notes": "", "usage": usage("weaver", result)}
