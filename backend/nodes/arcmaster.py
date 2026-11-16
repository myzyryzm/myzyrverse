"""Arcmaster: the milestone plan for an arc-plan run.

It plays the weaver's role in plan_arc runs: it proposes the chain of milestone
sub-events that leads to the target event, as a structured plan (backend/arcplan.py).
The author edits the milestones at the outline gate, and the archivist turns each
one into a sub_event ledger row as is.
"""

from __future__ import annotations

from .. import logbus
from ..arcplan import ARC_PLAN_SCHEMA, clean_plan
from ..state import PENDING_OUTLINE_REVIEW, RunState
from .common import build_prompt, call, system_prompt, usage


async def arcmaster(state: RunState) -> dict:
    prompt = build_prompt(
        state, ("Approved research", state.get("research_notes", "")),
        task=f"Plan the arc toward target event {state.get('target_event_id') or '(see brief)'}.",
    )
    result = await call("arcmaster", state, prompt, sys_prompt=system_prompt("arcmaster"),
                        output_schema=ARC_PLAN_SCHEMA)
    if isinstance(result.structured_output, dict):
        plan = clean_plan(result.structured_output)
    else:
        logbus.log(state.get("run_id"), "arcmaster: no structured output; kept the text as the overview", kind="warn")
        plan = clean_plan(result.text or "")
    return {"arc_plan": plan, "review_status": PENDING_OUTLINE_REVIEW,
            "author_notes": "", "usage": usage("arcmaster", result)}
