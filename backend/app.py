"""FastAPI backend for the control deck.

One compiled graph, one SQLite checkpointer, thread_id = run id. Graph runs
happen in background asyncio tasks (nodes can take many minutes), and the UI
polls /api/runs/{id}/state for progress.

    uvicorn backend.app:app --reload        # dev, with `npm run dev` in frontend/
    FAKE_LLM=1 uvicorn backend.app:app      # no subscription usage
"""

from __future__ import annotations

import asyncio
import shutil
import traceback
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from pydantic import BaseModel, Field

from . import config, logbus, lore, runs
from .graph import build_graph
from .state import (
    FINAL_APPROVED, OUTLINE_APPROVED, RESEARCH_APPROVED, RESEARCHING,
)

STATE = {"graph": None, "checkpointer": None}
TASKS: dict[str, asyncio.Task] = {}
ERRORS: dict[str, str] = {}

# Fields the UI may edit at a gate. Anything else in an edit payload is rejected.
EDITABLE = {"research_notes", "chapter_outline", "arc_plan", "lore_doc", "draft_prose", "critique_notes",
            "proposed_ledger", "summary", "characters_present", "pov", "brief", "title",
            "author_research_notes"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(str(config.CHECKPOINT_DB)) as saver:
        STATE["checkpointer"] = saver
        STATE["graph"] = build_graph(saver)
        yield
    for t in TASKS.values():
        t.cancel()


app = FastAPI(title="myzyrverse", lifespan=lifespan)


def _cfg(run_id: str) -> dict:
    return {"configurable": {"thread_id": run_id}, "recursion_limit": 100}


def _graph():
    return STATE["graph"]


def _require_run(run_id: str) -> dict:
    try:
        if not runs.exists(run_id):
            raise HTTPException(404, f"run {run_id} not found")
        return runs.read_meta(run_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


def _running(run_id: str) -> bool:
    t = TASKS.get(run_id)
    return bool(t and not t.done())


def _launch(run_id: str, payload: Any) -> None:
    if _running(run_id):
        raise HTTPException(409, f"run {run_id} is already running")
    ERRORS.pop(run_id, None)

    async def go():
        try:
            await _graph().ainvoke(payload, _cfg(run_id))
            st = await _graph().aget_state(_cfg(run_id))
            logbus.log(run_id, f"paused before {st.next[0]}" if st.next else "run finished", kind="pause")
        except asyncio.CancelledError:
            logbus.log(run_id, "run cancelled", kind="warn")
            raise
        except Exception as e:  # surface to UI; checkpoint keeps completed nodes, so Retry resumes
            ERRORS[run_id] = f"{type(e).__name__}: {e}"
            logbus.log(run_id, f"ERROR {type(e).__name__}: {e}", kind="error")
            traceback.print_exc()

    TASKS[run_id] = asyncio.create_task(go())


# ---------------- runs ----------------

class NewRun(BaseModel):
    id: str
    type: Literal["chapter", "research", "plan_arc", "lore"]
    title: str = ""
    brief: str = ""
    pov: str = ""
    researchers: list[str] = Field(default_factory=list)
    target_event_id: str = ""


class Resume(BaseModel):
    edits: dict = Field(default_factory=dict)


class Regenerate(BaseModel):
    notes: str = ""


@app.get("/api/config")
def get_config():
    return {"fake_llm": config.FAKE_LLM, "researchers": list(config.RESEARCHERS),
            "models": {k: v["model"] for k, v in config.NODE_SETTINGS.items()},
            "max_revisions": config.MAX_REVISIONS}


@app.get("/api/runs")
def list_runs():
    return [{**m, "running": _running(m["id"])} for m in runs.list_runs()]


@app.post("/api/runs")
def create_run(body: NewRun):
    bad = [r for r in body.researchers if r not in config.RESEARCHERS]
    if bad:
        raise HTTPException(400, f"unknown researchers {bad}")
    if body.type == "plan_arc" and not body.target_event_id:
        raise HTTPException(400, "plan_arc runs need a target_event_id")
    try:
        return runs.create_run(run_id=body.id, run_type=body.type, title=body.title, brief=body.brief,
                               pov=body.pov, researchers=body.researchers, target_event_id=body.target_event_id)
    except (ValueError, FileExistsError) as e:
        raise HTTPException(400, str(e))


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    meta = _require_run(run_id)
    return {**meta, "brief": runs.read_artifact(run_id, "brief"), "ledger": runs.read_ledger(run_id),
            "running": _running(run_id)}


@app.delete("/api/runs/{run_id}")
async def delete_run(run_id: str):
    meta = _require_run(run_id)
    if meta["status"] == "committed":
        raise HTTPException(400, "revert a committed run before deleting it")
    if _running(run_id):
        TASKS[run_id].cancel()
    await STATE["checkpointer"].adelete_thread(run_id)
    shutil.rmtree(runs.run_dir(run_id))
    logbus.clear(run_id)
    if meta["type"] == "chapter":
        runs.compile_manuscript()
    return {"ok": True}


@app.get("/api/runs/{run_id}/state")
async def run_state(run_id: str):
    meta = _require_run(run_id)
    st = await _graph().aget_state(_cfg(run_id))
    values = dict(st.values or {})
    values.pop("canon", None)
    usage = values.pop("usage", []) or []
    return {
        "meta": meta,
        "started": bool(st.values),
        "values": values,
        "next": list(st.next or []),
        "running": _running(run_id),
        "error": ERRORS.get(run_id),
        "log": logbus.tail(run_id),
        "usage": usage,
        "cost_usd": round(sum(u.get("cost_usd") or 0 for u in usage), 4),
    }


@app.post("/api/runs/{run_id}/start")
async def start_run(run_id: str):
    meta = _require_run(run_id)
    st = await _graph().aget_state(_cfg(run_id))
    if st.values:
        raise HTTPException(400, "run already started; use resume or retry")
    initial = {
        "run_id": run_id,
        "run_type": meta["type"],
        "title": meta.get("title", ""),
        "brief": runs.read_artifact(run_id, "brief"),
        "pov": meta.get("pov", ""),
        "researchers": meta.get("researchers", []),
        "target_event_id": meta.get("target_event_id", ""),
        "canon": lore.build_canon(run_id),
        "author_research_notes": "",
        "revision_count": 0,
        "review_status": RESEARCHING,
    }
    logbus.log(run_id, f"start ({meta['type']})")
    _launch(run_id, initial)
    return {"ok": True}


@app.post("/api/runs/{run_id}/resume")
async def resume_run(run_id: str, body: Resume):
    """Apply gate edits, refresh canon (you may have edited lore while paused), continue."""
    _require_run(run_id)
    st = await _graph().aget_state(_cfg(run_id))
    if not st.next:
        raise HTTPException(400, "run is not paused at a gate")
    bad = set(body.edits) - EDITABLE
    if bad:
        raise HTTPException(400, f"fields not editable: {sorted(bad)}")
    patch = {**body.edits, "canon": lore.build_canon(run_id)}
    if "brief" in body.edits:
        runs.write_artifact(run_id, "brief", body.edits["brief"])
    meta_fields = {k: body.edits[k] for k in ("pov", "title", "characters_present") if k in body.edits}
    if meta_fields:
        runs.update_meta(run_id, **meta_fields)
    await _graph().aupdate_state(_cfg(run_id), patch)
    logbus.log(run_id, f"resume from {st.next[0]}" + (f" with edits to {', '.join(sorted(body.edits))}" if body.edits else ""))
    _launch(run_id, None)
    return {"ok": True}


@app.post("/api/runs/{run_id}/retry")
async def retry_run(run_id: str):
    """Re-run after an error: the checkpoint resumes at the node that failed."""
    _require_run(run_id)
    logbus.log(run_id, "retry")
    _launch(run_id, None)
    return {"ok": True}


@app.post("/api/runs/{run_id}/cancel")
async def cancel_run(run_id: str):
    if _running(run_id):
        TASKS[run_id].cancel()
    return {"ok": True}


@app.post("/api/runs/{run_id}/regenerate")
async def regenerate(run_id: str, body: Regenerate):
    """Redo the phase the run is paused at, optionally steered by author notes.

    The patch is written as if the gate had run (as_node=gate), so the next
    node is the Maestro, which sees the cleared fields and re-dispatches.
    At the final gate this is the "force rewrite": the current draft is kept as
    the previous draft and the writer revises it against your notes.
    """
    meta = _require_run(run_id)
    st = await _graph().aget_state(_cfg(run_id))
    if not st.next:
        raise HTTPException(400, "run is not paused at a gate")
    gate = st.next[0]
    v = st.values
    notes = body.notes.strip()
    if gate == "human_gate_research":
        patch = {"research_complete": False, "research_notes": "", "review_status": RESEARCHING,
                 **{f"{r}_notes": "" for r in config.RESEARCHERS}}
    elif gate == "human_gate_outline":
        field = {"plan_arc": "arc_plan", "lore": "lore_doc"}.get(meta["type"], "chapter_outline")
        patch = {field: ""}
        patch["review_status"] = RESEARCH_APPROVED
    elif gate == "human_gate_final":
        patch = {"draft_history": [v.get("draft_prose", "")], "draft_prose": "", "critique_verdict": "",
                 "critique_notes": "", "revision_count": 0, "review_status": OUTLINE_APPROVED}
    elif gate == "human_gate_ledger":
        status = {"chapter": FINAL_APPROVED, "plan_arc": OUTLINE_APPROVED, "lore": OUTLINE_APPROVED}.get(meta["type"], RESEARCH_APPROVED)
        patch = {"proposed_ledger": [], "summary": "", "review_status": status}
    else:
        raise HTTPException(400, f"cannot regenerate at {gate}")
    patch.update(author_notes=notes, canon=lore.build_canon(run_id))
    await _graph().aupdate_state(_cfg(run_id), patch, as_node=gate)
    logbus.log(run_id, f"regenerate at {gate}" + (f" with notes: {notes[:80]}" if notes else ""))
    _launch(run_id, None)
    return {"ok": True}


class Adopt(BaseModel):
    file: str


@app.post("/api/runs/{run_id}/adopt")
async def adopt_lore(run_id: str, body: Adopt):
    """Append a lore run's approved document to a prehistory file (created if missing).

    The AI never writes prehistory; this is the author's explicit choice. It uses the
    document saved by the outline gate, so it includes any edits made there.
    """
    meta = _require_run(run_id)
    if meta["type"] != "lore":
        raise HTTPException(400, "only lore runs can be adopted into prehistory")
    st = await _graph().aget_state(_cfg(run_id))
    at_ledger = not _running(run_id) and list(st.next or []) == ["human_gate_ledger"]
    if not (at_ledger or meta["status"] == "committed"):
        raise HTTPException(400, "adopt from the ledger gate or after commit")
    doc = runs.read_artifact(run_id, "lore").strip()
    if not doc:
        raise HTTPException(400, "this run has no approved lore document")
    try:
        existing = lore.read_prehistory(body.file).rstrip()
        lore.write_prehistory(body.file, (existing + "\n\n" if existing else "") + doc + "\n")
    except ValueError as e:
        raise HTTPException(400, str(e))
    name = body.file.removesuffix(".md")
    updated = runs.update_meta(run_id, adopted_to=name, adopted_at=runs.now_iso())
    logbus.log(run_id, f"adopted lore document into prehistory/{name}.md")
    return updated


@app.post("/api/runs/{run_id}/revert")
def revert(run_id: str):
    _require_run(run_id)
    try:
        return {"warnings": lore.revert_run(run_id)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/runs/{run_id}/restore")
def restore(run_id: str):
    _require_run(run_id)
    try:
        lore.restore_run(run_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


# ---------------- lore ----------------

class TextBody(BaseModel):
    text: str


class ManualEntry(BaseModel):
    run_id: str | None = None
    kind: str = "lore"
    entity: str = ""
    change: str = ""
    detail: str
    ref_id: str = ""


class NewQuestion(BaseModel):
    question: str
    about: str = ""


class NewEvent(BaseModel):
    title: str
    description: str = ""
    scope: Literal["arc", "chapter"] = "arc"
    category: Literal["world", "personal"] = "world"
    parent_id: str | None = None
    characters: list[str] = Field(default_factory=list)
    target_run: str = ""


@app.get("/api/lore/prehistory")
def prehistory_list():
    return {name: lore.read_prehistory(name) for name in lore.list_prehistory()}


@app.put("/api/lore/prehistory/{name}")
def prehistory_write(name: str, body: TextBody):
    try:
        lore.write_prehistory(name, body.text)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.delete("/api/lore/prehistory/{name}")
def prehistory_delete(name: str):
    try:
        lore.delete_prehistory(name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.get("/api/lore/present")
def present():
    return {"entries": lore.present_entries(), "markdown": lore.materialize_present()}


@app.post("/api/lore/present/entries")
def present_add(body: ManualEntry):
    if body.run_id:
        _require_run(body.run_id)
    return lore.add_manual_entry(body.model_dump(exclude={"run_id"}), run_id=body.run_id)


@app.get("/api/lore/open-questions")
def questions_list():
    return lore.open_questions()


@app.post("/api/lore/open-questions")
def questions_create(body: NewQuestion):
    return lore.create_question(body.question, body.about)


@app.patch("/api/lore/open-questions/{item_id}")
def questions_update(item_id: str, patch: dict):
    lore.update_question(item_id, patch)
    return {"ok": True}


@app.delete("/api/lore/open-questions/{item_id}")
def questions_delete(item_id: str):
    lore.delete_question(item_id)
    return {"ok": True}


@app.get("/api/lore/events")
def events_list():
    return lore.events()


@app.post("/api/lore/events")
def events_create(body: NewEvent):
    return lore.create_event(**body.model_dump())


@app.patch("/api/lore/events/{item_id}")
def events_update(item_id: str, patch: dict):
    lore.update_event(item_id, patch)
    return {"ok": True}


@app.delete("/api/lore/events/{item_id}")
def events_delete(item_id: str):
    lore.delete_event(item_id)
    return {"ok": True}


class LaneBody(BaseModel):
    ids: list[str] = Field(default_factory=list)


@app.get("/api/lore/timelines")
def timelines_get():
    return lore.timelines_view()


@app.put("/api/lore/timelines/{lane}")
def timelines_put(lane: str, body: LaneBody):
    try:
        return lore.set_lane(lane, body.ids)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/timeline")
def timeline():
    return runs.timeline()


@app.get("/api/manuscript")
def manuscript():
    p = config.MANUSCRIPT_FILE
    return {"text": p.read_text() if p.exists() else ""}


# ---------------- frontend (production build) ----------------

if config.FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=config.FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        return FileResponse(config.FRONTEND_DIST / "index.html")
