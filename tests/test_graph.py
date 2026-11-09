"""Routing and gate behavior, run with FAKE_LLM (no subscription usage)."""

import pytest
from langgraph.checkpoint.memory import MemorySaver

from backend import config, lore, runs
from backend.graph import build_graph
from backend.nodes.maestro import decide


def _start(run_id, run_type="chapter", researchers=("historian", "psychologist"), **kw):
    runs.create_run(run_id=run_id, run_type=run_type, title=run_id, brief="brief text", pov=kw.get("pov", "Tiye"),
                    researchers=list(researchers), target_event_id=kw.get("target_event_id", ""))
    return {"run_id": run_id, "run_type": run_type, "brief": "brief text", "pov": kw.get("pov", "Tiye"),
            "researchers": list(researchers), "target_event_id": kw.get("target_event_id", ""),
            "canon": lore.build_canon(run_id), "revision_count": 0}


async def _walk(graph, run_id, initial, edits_by_gate=None):
    cfg = {"configurable": {"thread_id": run_id}}
    await graph.ainvoke(initial, cfg)
    gates = []
    while True:
        st = await graph.aget_state(cfg)
        if not st.next:
            return gates, st.values
        gates.append(st.next[0])
        edits = (edits_by_gate or {}).get(st.next[0])
        if edits:
            await graph.aupdate_state(cfg, edits)
        await graph.ainvoke(None, cfg)


@pytest.mark.asyncio
async def test_chapter_run_stops_at_all_four_gates_and_commits():
    g = build_graph(MemorySaver())
    gates, values = await _walk(g, "ch01", _start("ch01"),
                                {"human_gate_outline": {"chapter_outline": "MY OUTLINE"}})
    assert gates == ["human_gate_research", "human_gate_outline", "human_gate_final", "human_gate_ledger"]
    assert values["review_status"] == "COMMITTED"
    assert "MY OUTLINE" in values["draft_prose"]  # fake writer echoes its prompt: edit reached the writer
    assert runs.read_meta("ch01")["status"] == "committed"
    assert runs.read_ledger("ch01")
    assert "harem corridor" in config.MANUSCRIPT_FILE.read_text()


@pytest.mark.asyncio
async def test_parallel_research_honors_subset():
    g = build_graph(MemorySaver())
    initial = _start("ch01", researchers=["antiquarian", "mythographer"])
    cfg = {"configurable": {"thread_id": "ch01"}}
    await g.ainvoke(initial, cfg)
    v = (await g.aget_state(cfg)).values
    assert v["antiquarian_research"] and v["mythographer_research"]
    assert not v.get("historian_research") and not v.get("psychologist_research")
    assert "Antiquarian" in v["research_notes"] and "Mythographer" in v["research_notes"]
    # proposals are merged with stable ids, all pending; the shared source URL is numbered once
    props = v["research_proposals"]
    assert [p["id"] for p in props] == ["antiquarian-1", "antiquarian-2", "mythographer-1", "mythographer-2"]
    assert {p["decision"] for p in props} == {"pending"}
    assert v["research_sources"] == [{"n": 1, "title": "Placeholder source", "url": "https://example.org/source",
                                      "researchers": ["antiquarian", "mythographer"]}]
    assert "example.org" not in v["research_notes"] and "[1]" not in v["research_notes"]


@pytest.mark.asyncio
async def test_no_researchers_skips_research_gate():
    g = build_graph(MemorySaver())
    gates, _ = await _walk(g, "ch01", _start("ch01", researchers=[]))
    assert gates[0] == "human_gate_outline"


@pytest.mark.asyncio
async def test_research_run_skips_writing():
    g = build_graph(MemorySaver())
    gates, values = await _walk(g, "r1", _start("r1", run_type="research", researchers=["historian"]))
    assert gates == ["human_gate_research", "human_gate_ledger"]
    assert "draft_prose" not in values and "chapter_outline" not in values
    assert runs.read_meta("r1")["status"] == "committed"


@pytest.mark.asyncio
async def test_plan_arc_run():
    ev = lore.create_event("Battle of the Delta")
    g = build_graph(MemorySaver())
    gates, values = await _walk(g, "arc1", _start("arc1", run_type="plan_arc", researchers=[], target_event_id=ev["id"]))
    assert gates == ["human_gate_outline", "human_gate_ledger"]
    assert values["arc_plan"]
    tl = lore.timelines_view()
    subs = {e["title"]: e for e in lore.events() if e.get("parent_id") == ev["id"]}
    assert subs["Grain convoys fail"]["category"] == "personal"
    assert subs["Sherden demand pay"]["category"] == "world"
    assert subs["Grain convoys fail"]["id"] in tl["unplaced"]["Tiye"]


@pytest.mark.asyncio
async def test_critic_loop_keeps_notes_and_caps(monkeypatch):
    monkeypatch.setenv("FAKE_CRITIC_FAIL", "99")
    g = build_graph(MemorySaver())
    cfg = {"configurable": {"thread_id": "ch01"}}
    await g.ainvoke(_start("ch01", researchers=[]), cfg)  # pauses at outline gate
    await g.ainvoke(None, cfg)  # writes, fails critique repeatedly, escalates
    st = await g.aget_state(cfg)
    assert st.next == ("human_gate_final",)
    v = st.values
    assert v["revision_count"] == config.MAX_REVISIONS
    assert len(v["draft_history"]) == config.MAX_REVISIONS
    assert v["critique_verdict"] == "FAILED"
    # the revision prompt carried the previous critique to the writer
    assert "Critique of the previous draft" in v["draft_prose"] or "placeholder issue" in v["draft_prose"]


def test_maestro_failed_preserves_critique_notes():
    state = {"run_type": "chapter", "research_complete": True, "chapter_outline": "o",
             "review_status": "OUTLINE_APPROVED", "draft_prose": "d", "critique_verdict": "FAILED",
             "critique_notes": "fix it", "revision_count": 0}
    update = decide(state)
    assert update["next_steps"] == "writer"
    assert "critique_notes" not in update
    assert update["draft_history"] == ["d"] and update["draft_prose"] == ""


@pytest.mark.asyncio
async def test_lore_run():
    g = build_graph(MemorySaver())
    gates, values = await _walk(g, "lore1", _start("lore1", run_type="lore", researchers=["psychologist"]))
    assert gates == ["human_gate_research", "human_gate_outline", "human_gate_ledger"]
    assert values["lore_doc"].startswith("# Placeholder lore document")
    assert runs.read_artifact("lore1", "lore") == values["lore_doc"]
    assert "draft_prose" not in values and "chapter_outline" not in values and "arc_plan" not in values
    assert runs.read_meta("lore1")["status"] == "committed"


def test_maestro_lore_routing():
    base = {"run_type": "lore", "research_complete": True}
    assert decide({**base, "review_status": "RESEARCH_APPROVED"})["next_steps"] == "loremaster"
    assert decide({**base, "lore_doc": "d", "review_status": "PENDING_OUTLINE_REVIEW"})["next_steps"] == "human_gate_outline"
    assert decide({**base, "lore_doc": "d", "review_status": "OUTLINE_APPROVED"})["next_steps"] == "archivist"
