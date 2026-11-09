"""Commit: writes the approved ledger entries and the run's artifacts to disk and marks the run committed."""

from __future__ import annotations

from .. import logbus, runs
from ..state import COMMITTED, RunState


async def commit(state: RunState) -> dict:
    run_id = state["run_id"]
    accepted = [e for e in state.get("proposed_ledger") or [] if e.get("accepted", True)]
    ledger = []
    for i, e in enumerate(accepted, 1):
        entry = {k: v for k, v in e.items() if k != "accepted"}
        entry["id"] = f"{run_id}-{i}"
        entry.setdefault("source", "ai")
        entry["created_at"] = runs.now_iso()
        ledger.append(entry)
    runs.write_ledger(run_id, ledger)
    runs.write_artifact(run_id, "summary", state.get("summary", ""))
    runs.write_artifact(run_id, "research", state.get("research_notes", ""))
    runs.write_artifact(run_id, "notes", state.get("author_research_notes", ""))
    if state.get("run_type") == "chapter":
        runs.write_artifact(run_id, "prose", state.get("draft_prose", ""))
    if state.get("run_type") == "plan_arc":
        runs.write_artifact(run_id, "plan", state.get("arc_plan", ""))
    if state.get("run_type") == "lore":
        runs.write_artifact(run_id, "lore", state.get("lore_doc", ""))
    runs.update_meta(run_id, status="committed", committed_at=runs.now_iso(),
                     characters_present=state.get("characters_present") or [])
    if state.get("run_type") == "chapter":
        runs.compile_manuscript()
    logbus.log(run_id, f"commit: {len(ledger)} ledger entries written")
    return {"review_status": COMMITTED}
