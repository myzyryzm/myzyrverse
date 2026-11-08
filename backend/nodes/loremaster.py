"""Loremaster: turns approved research into a lore document (backstory, profile, proposal).

It plays the weaver's role in lore runs. Its output is a proposal: the author
reviews it at the outline gate and may adopt it into a prehistory file
afterwards (POST /api/runs/{id}/adopt). The AI never writes prehistory itself.
"""

from __future__ import annotations

from ..state import PENDING_OUTLINE_REVIEW, RunState
from .common import build_prompt, call, system_prompt, usage


async def loremaster(state: RunState) -> dict:
    prompt = build_prompt(state, ("Approved research", state.get("research_notes", "")),
                          task="Write the lore document the author's brief asks for.")
    result = await call("loremaster", state, prompt, sys_prompt=system_prompt("loremaster"))
    return {"lore_doc": result.text, "review_status": PENDING_OUTLINE_REVIEW,
            "author_notes": "", "usage": usage("loremaster", result)}
