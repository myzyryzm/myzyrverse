"""The Maestro: a deterministic router (no LLM).

It reads the state and decides what runs next. Gates are real nodes; the graph
is compiled with interrupt_before on them, so routing to a gate pauses the run
until the UI resumes it. Each gate flips review_status to an *_APPROVED value,
which is what lets the Maestro move past it on the next pass.
"""

from __future__ import annotations

from .. import config, logbus
from ..state import (
    COMMITTED, FINAL_APPROVED, LEDGER_APPROVED, OUTLINE_APPROVED, PENDING_FINAL_REVIEW,
    PENDING_LEDGER_REVIEW, PENDING_OUTLINE_REVIEW, PENDING_RESEARCH_EDIT, PENDING_RESEARCH_REVIEW, RESEARCH_APPROVED,
    RESEARCHING, RunState,
)

END = "__end__"


def decide(state: RunState) -> dict:
    """Pure routing decision: returns the partial state update including next_steps."""
    run_type = state.get("run_type", "chapter")
    status = state.get("review_status", "")

    if not state.get("research_complete"):
        chosen = [r for r in state.get("researchers") or [] if r in config.RESEARCHERS]
        if chosen:
            return {"next_steps": chosen, "review_status": RESEARCHING}
        # No researchers ticked: skip research and its gate entirely.
        skipped = {"research_complete": True, "research_notes": state.get("research_notes", ""),
                   "review_status": RESEARCH_APPROVED}
        return {**skipped, **decide({**state, **skipped})}

    if status == PENDING_RESEARCH_EDIT:
        return {"next_steps": "research_editor"}
    if status == PENDING_RESEARCH_REVIEW:
        return {"next_steps": "human_gate_research"}
    if status == PENDING_LEDGER_REVIEW:
        return {"next_steps": "human_gate_ledger"}
    if status == LEDGER_APPROVED:
        return {"next_steps": "commit"}
    if status == COMMITTED:
        return {"next_steps": END}

    if run_type == "research":
        return {"next_steps": "archivist"}

    if run_type == "plan_arc":
        if not state.get("arc_plan"):
            return {"next_steps": "weaver"}
        if status == PENDING_OUTLINE_REVIEW:
            return {"next_steps": "human_gate_outline"}
        return {"next_steps": "archivist"}

    if run_type == "lore":
        if not state.get("lore_doc"):
            return {"next_steps": "loremaster"}
        if status == PENDING_OUTLINE_REVIEW:
            return {"next_steps": "human_gate_outline"}
        return {"next_steps": "archivist"}

    # chapter
    if not state.get("chapter_outline"):
        return {"next_steps": "weaver"}
    if status == PENDING_OUTLINE_REVIEW:
        return {"next_steps": "human_gate_outline"}
    if status == PENDING_FINAL_REVIEW:
        return {"next_steps": "human_gate_final"}
    if status == FINAL_APPROVED:
        return {"next_steps": "archivist"}
    if status != OUTLINE_APPROVED:
        return {"next_steps": "weaver"}

    if not state.get("draft_prose"):
        return {"next_steps": "writer"}
    if not state.get("critique_verdict"):
        return {"next_steps": "grand_critic"}

    revisions = state.get("revision_count", 0)
    if state["critique_verdict"] == "FAILED" and revisions < config.MAX_REVISIONS:
        # Keep critique_notes so the writer knows what to fix; keep the old draft in history.
        return {
            "next_steps": "writer",
            "draft_history": [state["draft_prose"]],
            "draft_prose": "",
            "critique_verdict": "",
            "revision_count": revisions + 1,
        }
    return {"next_steps": "human_gate_final", "review_status": PENDING_FINAL_REVIEW}


async def maestro(state: RunState) -> dict:
    update = decide(state)
    nxt = update["next_steps"]
    msg = {
        "writer": f"maestro: -> writer (revision {update.get('revision_count', state.get('revision_count', 0))})"
        if update.get("revision_count") else "maestro: -> writer",
    }.get(nxt if isinstance(nxt, str) else "", f"maestro: -> {nxt if isinstance(nxt, str) else ', '.join(nxt)}")
    logbus.log(state.get("run_id"), msg)
    return update


def route(state: RunState):
    return state["next_steps"]
