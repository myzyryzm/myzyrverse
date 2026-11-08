"""Ledger folding, revert/restore, open questions, events, timeline."""

from backend import lore, runs


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
