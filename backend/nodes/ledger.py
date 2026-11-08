"""Archivist (proposes ledger entries) and commit (writes them to disk)."""

from __future__ import annotations

from .. import logbus, runs
from ..state import COMMITTED, PENDING_LEDGER_REVIEW, RunState
from .common import build_prompt, call, system_prompt, usage

ENTRY_KINDS = ["lore", "answer", "new_question", "event_update", "sub_event"]

ARCHIVIST_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "characters_present", "entries"],
    "properties": {
        "summary": {"type": "string"},
        "characters_present": {"type": "array", "items": {"type": "string"}},
        "entries": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["kind", "entity", "change", "detail", "ref_id", "characters", "confidence"],
                "properties": {
                    "kind": {"type": "string", "enum": ENTRY_KINDS},
                    "entity": {"type": "string"},
                    "change": {"type": "string"},
                    "detail": {"type": "string"},
                    "ref_id": {"type": "string"},
                    "characters": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                },
            },
        },
    },
}


async def archivist(state: RunState) -> dict:
    run_type = state.get("run_type")
    if run_type == "chapter":
        sections = [("Final chapter prose", state.get("draft_prose", ""))]
        task = "Propose ledger entries for what this chapter establishes, plus the summary and characters present."
    elif run_type == "plan_arc":
        sections = [("Approved research", state.get("research_notes", "")),
                    ("Approved arc plan", state.get("arc_plan", ""))]
        task = (f"Turn each milestone in the approved arc plan into a sub_event entry (ref_id = "
                f"{state.get('target_event_id') or ''}). Also propose new_question entries for anything the plan "
                "depends on that canon leaves open, and answer entries if the plan settles an open question.")
    elif run_type == "lore":
        sections = [("Approved research", state.get("research_notes", "")),
                    ("Approved lore document", state.get("lore_doc", ""))]
        task = ("This was a lore run: the author approved the lore document above and may adopt it into prehistory "
                "themselves, so do not restate its background as lore entries. Propose lore entries only for things it "
                "makes true in the present of the story that canon does not already say, answer entries for open "
                "questions it settles, and new_question entries for its proposed open questions. Do not propose "
                "event_update or sub_event entries. characters_present = the characters the document is about.")
    else:
        sections = [("Approved research", state.get("research_notes", ""))]
        task = ("This was a research run, not a chapter. Propose lore entries only for things the author's brief and the "
                "approved research settle about this universe, answers to open questions the research resolves, and new "
                "questions it raises. Do not propose event_update or sub_event entries.")
    if (state.get("author_research_notes") or "").strip():
        task += (" The author left notes on the research: treat them as settled. Propose answer entries for open "
                 "questions they resolve and lore entries for facts they establish.")
    prompt = build_prompt(state, *sections, task=task)
    result = await call("archivist", state, prompt, sys_prompt=system_prompt("archivist"),
                        output_schema=ARCHIVIST_SCHEMA)
    out = result.structured_output if isinstance(result.structured_output, dict) else {}
    known = {(q.get("question") or "").strip().lower() for q in (state.get("canon") or {}).get("open_questions", [])}
    entries = []
    for e in out.get("entries") or []:
        if e.get("kind") == "new_question" and (e.get("detail") or "").strip().lower() in known:
            continue  # already an open question
        entries.append({**e, "source": "ai", "accepted": True})
    if not out:
        logbus.log(state.get("run_id"), "archivist: no structured output; ledger left empty for manual entry", kind="warn")
    chars = out.get("characters_present") or []
    if state.get("pov") and state["pov"] not in chars:
        chars = [state["pov"], *chars]
    return {
        "proposed_ledger": entries,
        "summary": out.get("summary") or result.text,
        "characters_present": chars,
        "review_status": PENDING_LEDGER_REVIEW,
        "author_notes": "",
        "usage": usage("archivist", result),
    }


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
