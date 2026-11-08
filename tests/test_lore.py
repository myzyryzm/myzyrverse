"""Ledger folding, revert/restore, open questions, events, timeline, character lanes."""

import pytest

from backend import lore, runs
from backend.nodes.common import render_canon


def _commit(run_id, entries, run_type="chapter", pov="Tiye", chars=None, target_event_id=""):
    runs.create_run(run_id=run_id, run_type=run_type, title=run_id, brief="b", pov=pov,
                    target_event_id=target_event_id)
    ledger = [{**e, "id": f"{run_id}-{i}", "source": e.get("source", "ai")} for i, e in enumerate(entries, 1)]
    runs.write_ledger(run_id, ledger)
    if run_type == "chapter":
        runs.write_artifact(run_id, "prose", f"prose of {run_id}")
    runs.update_meta(run_id, status="committed", committed_at=runs.now_iso() + run_id,
                     characters_present=chars or [pov])


def test_present_folds_in_commit_order_and_revert_removes():
    _commit("ch01", [{"kind": "lore", "entity": "Tiye", "change": "status", "detail": "plotting"}])
    _commit("ch02", [{"kind": "lore", "entity": "Tiye", "change": "status", "detail": "queen mother"}])
    md = lore.materialize_present()
    assert md.index("plotting") < md.index("queen mother")

    warnings = lore.revert_run("ch01")
    assert any("ch02" in w for w in warnings)
    assert "plotting" not in lore.materialize_present()
    runs.compile_manuscript()
    assert "prose of ch01" not in open(runs.config.MANUSCRIPT_FILE).read()

    lore.restore_run("ch01")
    assert "plotting" in lore.materialize_present()


def test_questions_answered_by_run_and_reverted():
    q = lore.create_question("How did Tiye marry into the harem?", about="Tiye")
    _commit("r1", [{"kind": "answer", "ref_id": q["id"], "detail": "A treaty bride"},
                   {"kind": "new_question", "entity": "Sherden", "detail": "Who pays them?"}], run_type="research")
    qs = {x["id"]: x for x in lore.open_questions()}
    assert qs[q["id"]]["status"] == "answered" and qs[q["id"]]["answered_by_run"] == "r1"
    assert any(x["question"] == "Who pays them?" for x in qs.values())

    lore.revert_run("r1")
    qs = {x["id"]: x for x in lore.open_questions()}
    assert qs[q["id"]]["status"] == "open"
    assert not any(x["question"] == "Who pays them?" for x in qs.values())


def test_manual_override_beats_ledger():
    q = lore.create_question("Q?")
    lore.update_question(q["id"], {"answer": "author's answer"})
    _commit("r1", [{"kind": "answer", "ref_id": q["id"], "detail": "ai answer"}], run_type="research")
    assert lore.open_questions()[0]["answer"] == "author's answer"


def test_sub_events_from_arc_and_event_progress():
    ev = lore.create_event("War with Hatti")
    _commit("arc1", [{"kind": "sub_event", "entity": "Envoy murdered", "change": "1", "detail": "..."}],
            run_type="plan_arc", target_event_id=ev["id"])
    _commit("ch01", [{"kind": "event_update", "ref_id": ev["id"], "change": "in_progress", "detail": "troops gather"}])
    evs = {e["id"]: e for e in lore.events()}
    subs = [e for e in evs.values() if e.get("parent_id") == ev["id"]]
    assert subs and subs[0]["title"] == "Envoy murdered"
    assert evs[ev["id"]]["status"] == "in_progress"


def test_manual_present_entry_on_run_and_general():
    _commit("ch01", [])
    lore.add_manual_entry({"entity": "Pentawere", "change": "wounded", "detail": "lost an eye"}, run_id="ch01")
    lore.add_manual_entry({"entity": "World", "detail": "Nile flood failed"})
    md = lore.materialize_present()
    assert "lost an eye" in md and "ch01 · user" in md and "Nile flood failed" in md
    lore.revert_run("ch01")
    md = lore.materialize_present()
    assert "lost an eye" not in md and "Nile flood failed" in md


def test_timeline():
    _commit("ch01", [], pov="Tiye", chars=["Tiye", "Pentawere"])
    _commit("ch02", [], pov="Ramesses", chars=["Ramesses"])
    t = runs.timeline()
    assert [x["pov"] for x in t] == ["Tiye", "Ramesses"]
    assert t[0]["characters_present"] == ["Tiye", "Pentawere"]


def test_events_default_category_world():
    ev = lore.create_event("Elam attacks Babylon")
    assert ev["category"] == "world"
    store = lore._load_store(runs.config.EVENTS_FILE)
    del store["items"][0]["category"]  # an item written before categories existed
    lore._save_store(runs.config.EVENTS_FILE, store)
    assert lore.events()[0]["category"] == "world"
    assert lore.create_event("Someone dies for Aegon", category="personal")["category"] == "personal"


def test_story_order_levels():
    order = lore.story_order({"Jon": ["a", "b", "c"], "Aegon": ["x", "b", "y"]})
    assert order == {"levels": [["a", "x"], ["b"], ["c", "y"]], "cycle": None}


def test_story_order_cycle_does_not_raise():
    order = lore.story_order({"Jon": ["a", "b"], "Aegon": ["b", "a"], "Tiye": ["z"]})
    assert order["levels"] == [["z"]]
    assert order["cycle"] == ["a", "b"]


def test_set_lane_syncs_characters():
    e1 = lore.create_event("Jon arrives at Knossos", category="personal")
    e2 = lore.create_event("Minotaur trial", characters=["Jon", "Ariadne"], category="personal")
    w = lore.create_event("Elam attacks Babylon")

    view = lore.set_lane("Jon", [e1["id"]])
    evs = {e["id"]: e for e in lore.events()}
    assert "Jon" in evs[e1["id"]]["characters"]
    assert evs[e2["id"]]["characters"] == ["Jon", "Ariadne"]  # never placed, so left alone
    assert view["lanes"]["Jon"] == [e1["id"]] and view["unplaced"]["Jon"] == [e2["id"]]

    lore.set_lane("Jon", [e1["id"], e2["id"]])
    view = lore.set_lane("Jon", [e1["id"]])  # taking it off the placed lane removes Jon
    evs = {e["id"]: e for e in lore.events()}
    assert evs[e2["id"]]["characters"] == ["Ariadne"]
    assert view["unplaced"]["Jon"] == []

    lore.set_lane("World", [w["id"]])
    evs = {e["id"]: e for e in lore.events()}
    assert evs[w["id"]]["characters"] == []

    with pytest.raises(ValueError):
        lore.set_lane("Jon", ["ev-nope"])
    with pytest.raises(ValueError):
        lore.set_lane("../x", [])


def test_unplaced_events_listed_but_not_ordered():
    e1 = lore.create_event("A", characters=["Jon"], category="personal")
    lore.set_lane("Jon", [e1["id"]])
    e2 = lore.create_event("B", characters=["Jon"], category="personal")
    e3 = lore.create_event("C", characters=["Jon"], category="personal")
    w1, w2 = lore.create_event("W1"), lore.create_event("W2")
    placed, unplaced = lore.effective_lanes()
    assert placed["Jon"] == [e1["id"]] and unplaced["Jon"] == [e2["id"], e3["id"]]
    assert placed["World"] == [] and unplaced["World"] == [w1["id"], w2["id"]]
    # unplaced events impose no order on each other
    assert lore.timelines_view()["story_order"]["levels"] == [[e1["id"]]]
    _commit("ch01", [], pov="Aegon")
    assert {"Jon", "Aegon"} <= set(lore.characters())
    lore.set_lane("Helen", [])  # an empty lane still names a character
    assert "Helen" in lore.characters()


def test_shared_event_in_story_order():
    shared = lore.create_event("The harem conspiracy", characters=["Jon", "Aegon"])
    i = lore.create_event("I", characters=["Jon"], category="personal")
    ii = lore.create_event("II", characters=["Aegon"], category="personal")
    iii = lore.create_event("III", characters=["Aegon"], category="personal")
    lore.set_lane("Jon", [i["id"], shared["id"]])
    lore.set_lane("Aegon", [ii["id"], iii["id"], shared["id"]])
    lore.set_lane("World", [shared["id"]])
    levels = lore.timelines_view()["story_order"]["levels"]
    where = {eid: n for n, lvl in enumerate(levels) for eid in lvl}
    assert where[shared["id"]] > max(where[i["id"]], where[ii["id"]], where[iii["id"]])
    assert where[i["id"]] == where[ii["id"]]  # unordered relative to each other


def test_ledger_sub_event_lands_on_lane_and_reverts():
    ev = lore.create_event("War with Hatti")
    _commit("arc1", [{"kind": "sub_event", "entity": "Envoy murdered", "change": "1", "detail": "...",
                      "characters": ["Jon"]}], run_type="plan_arc", target_event_id=ev["id"])
    sub = next(e for e in lore.events() if e.get("parent_id") == ev["id"])
    assert sub["category"] == "personal"
    mine = lore.create_event("Jon earlier", characters=["Jon"], category="personal")
    lore.set_lane("Jon", [mine["id"], sub["id"]])
    lore.revert_run("arc1")
    assert lore.effective_lanes()[0]["Jon"] == [mine["id"]]
    assert sub["id"] in lore._load_timelines()["lanes"]["Jon"]  # stored order kept
    lore.restore_run("arc1")
    assert lore.effective_lanes()[0]["Jon"] == [mine["id"], sub["id"]]


def test_deleting_event_drops_it_from_lanes():
    e = lore.create_event("A", characters=["Jon"])
    lore.set_lane("Jon", [e["id"]])
    lore.delete_event(e["id"])
    assert lore._load_timelines()["lanes"]["Jon"] == []


def test_render_canon_includes_timelines():
    a = lore.create_event("Jon arrives at Knossos", characters=["Jon"], category="personal")
    lore.set_lane("Jon", [a["id"]])
    md = render_canon(lore.build_canon("x"))
    assert "## Story order" in md and "## Character timelines" in md
    assert f"- Jon: [{a['id']}] Jon arrives at Knossos" in md
    assert "(chapter" not in md and "(arc, personal, planned)" in md
