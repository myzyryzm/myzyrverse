"""Metrics: events recorded through the API, the summary endpoint, and backfill of older runs."""

import json

import pytest
from fastapi.testclient import TestClient

from backend import app as app_module
from backend import fakes, metrics, runs

from test_api import _wait


@pytest.fixture
def client():
    with TestClient(app_module.app) as c:
        yield c


def _run(client, run_id):
    return next(r for r in client.get("/api/metrics").json()["runs"] if r["id"] == run_id)


def test_lore_run_records_usage_time_and_reviews(client):
    client.post("/api/runs", json={"id": "lore-m", "type": "lore", "title": "Metrics lore", "brief": "b",
                                   "researchers": ["historian", "psychologist"]})
    client.post("/api/runs/lore-m/start")
    s = _wait(client, "lore-m")
    assert s["next"] == ["human_gate_research"]

    proposals = s["values"]["research_proposals"]
    assert len(proposals) == 4
    decisions = [("accepted", "keep but older"), ("maybe", ""), ("rejected", ""), ("rejected", "")]
    for p, (d, note) in zip(proposals, decisions):
        p.update(decision=d, note=note)
    client.post("/api/runs/lore-m/resume", json={"edits": {"research_proposals": proposals}})
    s = _wait(client, "lore-m")
    assert s["next"] == ["human_gate_outline"]

    client.post("/api/runs/lore-m/regenerate", json={"notes": "more about the sea"})
    s = _wait(client, "lore-m")
    client.post("/api/runs/lore-m/resume", json={"edits": {"lore_doc": s["values"]["lore_doc"] + "\n\nMy own line."}})
    s = _wait(client, "lore-m")
    assert s["next"] == ["human_gate_ledger"]

    ledger = s["values"]["proposed_ledger"]
    ledger[0]["accepted"] = False
    client.post("/api/runs/lore-m/resume", json={"edits": {"proposed_ledger": ledger}})
    s = _wait(client, "lore-m")
    assert s["values"]["review_status"] == "COMMITTED"

    r = _run(client, "lore-m")
    assert not r["backfilled"]
    # historian, psychologist, research_editor, loremaster x2, archivist
    calls = 6
    assert r["usage"]["calls"] == calls
    assert r["usage"]["cost_usd"] == pytest.approx(calls * fakes.FAKE_COST_USD)
    assert r["usage"]["input"] == calls * fakes.FAKE_TOKENS["input"]
    assert r["usage"]["web_searches"] == fakes.FAKE_RESEARCH_WEB_SEARCHES  # historian only
    assert {n["node"] for n in r["nodes"]} >= {"historian", "loremaster", "archivist"}
    assert r["time"]["active_ms"] > 0 and r["time"]["waiting_ms"] is not None

    res = r["research"]
    assert (res["accepted"], res["maybe"], res["rejected"], res["accepted_with_notes"]) == (1, 1, 2, 1)
    assert sum(sum(c.values()) for c in res["by_researcher"].values()) == 4

    assert r["doc"] == {**r["doc"], "doc": "lore_doc", "regenerations": 1, "approved": True, "edited": True}
    assert r["ledger"]["dropped"] == 1 and r["ledger"]["kept"] == len(ledger) - 1

    data = metrics.load("lore-m")
    outcomes = [e["outcome"] for e in data["events"] if e["kind"] == "segment"]
    assert outcomes[-1] == "finished" and outcomes.count("paused:human_gate_research") == 1

    totals = client.get("/api/metrics").json()["totals"]
    assert totals["research"]["accepted"] == 1 and totals["ledger"]["dropped"] == 1
    assert totals["docs"][0]["regenerations"] == 1


def test_chapter_run_records_critic_and_force_rewrite(client, monkeypatch):
    monkeypatch.setenv("FAKE_CRITIC_FAIL", "1")
    monkeypatch.setattr(fakes, "_critic_calls", {})
    client.post("/api/runs", json={"id": "ch-m", "type": "chapter", "title": "C", "brief": "b",
                                   "researchers": ["psychologist"]})
    client.post("/api/runs/ch-m/start")
    s = _wait(client, "ch-m")
    client.post("/api/runs/ch-m/resume", json={"edits": {"research_proposals": [
        {**p, "decision": "accepted"} for p in s["values"]["research_proposals"]]}})
    _wait(client, "ch-m")
    client.post("/api/runs/ch-m/resume", json={"edits": {}})  # outline as written
    s = _wait(client, "ch-m")
    assert s["next"] == ["human_gate_final"]

    client.post("/api/runs/ch-m/regenerate", json={"notes": "more dread"})
    s = _wait(client, "ch-m")
    client.post("/api/runs/ch-m/resume", json={"edits": {"draft_prose": s["values"]["draft_prose"]}})  # unchanged
    _wait(client, "ch-m")

    r = _run(client, "ch-m")
    p = r["prose"]
    assert p["failed"] == 1 and p["passed"] == 2 and p["force_rewrites"] == 1
    assert p["approved"] and p["edited"] is False and p["avg_score"] == pytest.approx((5 + 8 + 8) / 3, abs=0.01)
    assert r["doc"]["doc"] == "chapter_outline" and r["doc"]["edited"] is False


def test_backfill_older_run(client):
    runs.create_run(run_id="old", run_type="lore", title="Old", brief="b", pov="", researchers=[],
                    target_event_id="")  # created directly: no metrics.json, like runs from before metrics
    runs.write_artifact("old", "proposals", json.dumps([
        {"id": "a-1", "researcher": "antiquarian", "decision": "rejected", "note": ""},
        {"id": "a-2", "researcher": "antiquarian", "decision": "modified", "note": "x"},
        {"id": "h-1", "researcher": "historian", "decision": "accepted", "note": ""},
    ]))
    r = _run(client, "old")
    assert r["backfilled"] is True
    assert (r["research"]["accepted"], r["research"]["rejected"], r["research"]["accepted_with_notes"]) == (2, 1, 1)
    assert r["usage"]["input"] is None and r["time"]["active_ms"] is None
    # Idempotent: a second read does not double-count.
    assert _run(client, "old")["research"]["total"] == 3
    assert len(metrics.load("old")["events"]) == 1


def test_ledger_counts_deleted_rows_as_dropped():
    before = [{"kind": "lore"}, {"kind": "lore"}, {"kind": "hook"}]
    after = [{"kind": "lore", "accepted": True}, {"kind": "hook", "accepted": False},
             {"kind": "lore", "source": "user", "accepted": True}]
    c = metrics.ledger_counts(before, after)
    assert (c["kept"], c["dropped"], c["added_by_user"]) == (1, 2, 1)
    assert c["by_kind"] == {"lore": {"kept": 1, "dropped": 1}, "hook": {"kept": 0, "dropped": 1}}
