"""Human gates. The graph pauses *before* each of these (interrupt_before).

While paused, the UI may edit state (graph.aupdate_state). When you resume,
the gate runs: it saves the possibly-edited artifact to the run dir and marks
the phase approved so the Maestro moves on.
"""

from __future__ import annotations

from .. import logbus, runs
from ..state import FINAL_APPROVED, LEDGER_APPROVED, OUTLINE_APPROVED, RESEARCH_APPROVED, RunState


def _save_notes(state: RunState) -> None:
    """The author's research notes are editable at every gate, so every gate saves them."""
    runs.write_artifact(state["run_id"], "notes", state.get("author_research_notes", ""))


async def human_gate_research(state: RunState) -> dict:
    _save_notes(state)
    runs.write_artifact(state["run_id"], "research", state.get("research_notes", ""))
    logbus.log(state["run_id"], "gate: research approved")
    return {"review_status": RESEARCH_APPROVED, "author_notes": ""}


async def human_gate_outline(state: RunState) -> dict:
    _save_notes(state)
    if state.get("run_type") == "plan_arc":
        runs.write_artifact(state["run_id"], "plan", state.get("arc_plan", ""))
    elif state.get("run_type") == "lore":
        runs.write_artifact(state["run_id"], "lore", state.get("lore_doc", ""))
    else:
        runs.write_artifact(state["run_id"], "outline", state.get("chapter_outline", ""))
    logbus.log(state["run_id"], "gate: outline approved")
    return {"review_status": OUTLINE_APPROVED, "author_notes": ""}


async def human_gate_final(state: RunState) -> dict:
    _save_notes(state)
    runs.write_artifact(state["run_id"], "prose", state.get("draft_prose", ""))
    runs.write_artifact(state["run_id"], "critique", state.get("critique_notes", ""))
    logbus.log(state["run_id"], "gate: final prose approved")
    return {"review_status": FINAL_APPROVED, "author_notes": ""}


async def human_gate_ledger(state: RunState) -> dict:
    _save_notes(state)
    logbus.log(state["run_id"], "gate: ledger approved")
    return {"review_status": LEDGER_APPROVED, "author_notes": ""}
