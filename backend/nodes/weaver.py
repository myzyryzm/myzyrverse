"""Weaver: the beat sheet for a chapter run, or the milestone plan for an arc-plan run."""

from __future__ import annotations

from ..state import PENDING_OUTLINE_REVIEW, RunState
from .common import build_prompt, call, system_prompt, usage


async def weaver(state: RunState) -> dict:
    research = ("Approved research", state.get("research_notes", ""))
    if state.get("run_type") == "plan_arc":
        prompt = build_prompt(
            state, research,
            task=(f"Plan the arc toward target event {state.get('target_event_id') or '(see brief)'}. "
                  "Write markdown: a short causal overview, then a numbered list of milestones. For each milestone give "
                  "a bold title, what happens, who is involved, and why it follows from the previous one. "
                  "End with a `## Risks` section."),
        )
        result = await call("weaver", state, prompt, sys_prompt=system_prompt("weaver_arc"))
        return {"arc_plan": result.text, "review_status": PENDING_OUTLINE_REVIEW,
                "author_notes": "", "usage": usage("weaver", result)}

    prompt = build_prompt(state, research, task="Write the beat sheet for this chapter.")
    result = await call("weaver", state, prompt, sys_prompt=system_prompt("weaver"))
    return {"chapter_outline": result.text, "review_status": PENDING_OUTLINE_REVIEW,
            "author_notes": "", "usage": usage("weaver", result)}
