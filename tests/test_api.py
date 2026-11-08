"""End-to-end through the HTTP API with FAKE_LLM."""

import time

import pytest
from fastapi.testclient import TestClient

from backend import app as app_module


@pytest.fixture
def client():
    with TestClient(app_module.app) as c:
        yield c


def _wait(client, run_id, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = client.get(f"/api/runs/{run_id}/state").json()
        if not s["running"]:
            assert not s["error"], s["error"]
            return s
        time.sleep(0.1)
    raise AssertionError("run did not pause in time")


def test_chapter_flow_with_regenerate_and_revert(client):
    r = client.post("/api/runs", json={"id": "ch01", "type": "chapter", "title": "The Harem", "brief": "Tiye moves",
                                       "pov": "Tiye", "researchers": ["historian"]})
    assert r.status_code == 200, r.text
    client.post("/api/runs/ch01/start")
    s = _wait(client, "ch01")
    assert s["next"] == ["human_gate_research"]

    client.post("/api/runs/ch01/resume", json={"edits": {"research_notes": "EDITED RESEARCH"}})
    s = _wait(client, "ch01")
    assert s["next"] == ["human_gate_outline"]
    assert "EDITED RESEARCH" in s["values"]["chapter_outline"]

    client.post("/api/runs/ch01/regenerate", json={"notes": "make beat 3 a betrayal"})
    s = _wait(client, "ch01")
    assert s["next"] == ["human_gate_outline"]
    assert "make beat 3 a betrayal" in s["values"]["chapter_outline"]

    client.post("/api/runs/ch01/resume", json={"edits": {}})
    s = _wait(client, "ch01")
    assert s["next"] == ["human_gate_final"]

    client.post("/api/runs/ch01/regenerate", json={"notes": "more dread"})
    s = _wait(client, "ch01")
    assert s["next"] == ["human_gate_final"]
    assert "more dread" in s["values"]["draft_prose"] and len(s["values"]["draft_history"]) == 1

    client.post("/api/runs/ch01/resume", json={"edits": {}})
    s = _wait(client, "ch01")
    assert s["next"] == ["human_gate_ledger"]
    ledger = s["values"]["proposed_ledger"]
    ledger[0]["accepted"] = False
    ledger.append({"kind": "lore", "entity": "Tiye", "change": "secret", "detail": "poisoned the wine",
                   "ref_id": "", "confidence": "high", "source": "user", "accepted": True})
    client.post("/api/runs/ch01/resume", json={"edits": {"proposed_ledger": ledger}})
    s = _wait(client, "ch01")
    assert s["next"] == [] and s["values"]["review_status"] == "COMMITTED"

    present = client.get("/api/lore/present").json()["markdown"]
    assert "poisoned the wine" in present and "Placeholder lore change" not in present
    assert client.get("/api/timeline").json()[0]["pov"] == "Tiye"
    assert "harem corridor" in client.get("/api/manuscript").json()["text"]

    client.post("/api/runs/ch01/revert")
    assert "poisoned the wine" not in client.get("/api/lore/present").json()["markdown"]
    assert client.get("/api/manuscript").json()["text"].strip() == ""


def test_rejects_bad_edits_and_ids(client):
    assert client.post("/api/runs", json={"id": "Bad Id", "type": "chapter"}).status_code == 400
    client.post("/api/runs", json={"id": "r1", "type": "research", "researchers": ["antiquarian"]})
    client.post("/api/runs/r1/start")
    _wait(client, "r1")
    assert client.post("/api/runs/r1/resume", json={"edits": {"canon": {}}}).status_code == 400


def test_lore_flow_with_regenerate_and_adopt(client):
    r = client.post("/api/runs", json={"id": "lore-tiye", "type": "lore", "title": "Tiye backstory",
                                       "brief": "Write Tiye's backstory", "researchers": ["psychologist"]})
    assert r.status_code == 200, r.text
    client.post("/api/runs/lore-tiye/start")
    s = _wait(client, "lore-tiye")
    assert s["next"] == ["human_gate_research"]
    assert client.post("/api/runs/lore-tiye/adopt", json={"file": "characters"}).status_code == 400  # too early

    client.post("/api/runs/lore-tiye/resume", json={"edits": {}})
    s = _wait(client, "lore-tiye")
    assert s["next"] == ["human_gate_outline"]
    assert s["values"]["lore_doc"].startswith("# Placeholder lore document")

    client.post("/api/runs/lore-tiye/regenerate", json={"notes": "more about her mother"})
    s = _wait(client, "lore-tiye")
    assert s["next"] == ["human_gate_outline"]
    assert "more about her mother" in s["values"]["lore_doc"]

    client.post("/api/runs/lore-tiye/resume", json={"edits": {"lore_doc": "# Tiye\n\nBorn in Thebes. EDITED."}})
    s = _wait(client, "lore-tiye")
    assert s["next"] == ["human_gate_ledger"]

    assert client.post("/api/runs/lore-tiye/adopt", json={"file": "../evil"}).status_code == 400
    r = client.post("/api/runs/lore-tiye/adopt", json={"file": "world"})
    assert r.status_code == 200, r.text
    assert r.json()["adopted_to"] == "world"
    world = client.get("/api/lore/prehistory").json()["world"]
    assert world.startswith("Egypt, 1160 BCE. Tiye plots.") and world.rstrip().endswith("Born in Thebes. EDITED.")

    client.post("/api/runs/lore-tiye/resume", json={"edits": {}})
    s = _wait(client, "lore-tiye")
    assert s["values"]["review_status"] == "COMMITTED"
    assert client.post("/api/runs/lore-tiye/adopt", json={"file": "characters"}).status_code == 200
    assert "Born in Thebes" in client.get("/api/lore/prehistory").json()["characters"]


def test_adopt_rejects_non_lore_runs(client):
    client.post("/api/runs", json={"id": "r2", "type": "research", "researchers": []})
    assert client.post("/api/runs/r2/adopt", json={"file": "world"}).status_code == 400
