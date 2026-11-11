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


def _decide_all(state, decision="maybe"):
    """The research gate only resumes once every proposal has a decision."""
    return [{**p, "decision": decision if p["decision"] == "pending" else p["decision"]}
            for p in state["values"]["research_proposals"]]


def test_chapter_flow_with_regenerate_and_revert(client):
    r = client.post("/api/runs", json={"id": "ch01", "type": "chapter", "title": "The Harem", "brief": "Tiye moves",
                                       "pov": "Tiye", "researchers": ["historian"]})
    assert r.status_code == 200, r.text
    client.post("/api/runs/ch01/start")
    s = _wait(client, "ch01")
    assert s["next"] == ["human_gate_research"]

    proposals = s["values"]["research_proposals"]
    assert len(proposals) == 2 and s["values"]["research_sources"]
    proposals[0].update(decision="accepted", note="MAKE IT THE SHERDEN CAPTAIN")
    proposals[0]["questions"][0]["answer"] = "THE TEMPLE OF AMUN"
    proposals[1]["decision"] = "pending"
    r = client.post("/api/runs/ch01/resume", json={"edits": {"research_proposals": proposals}})
    assert r.status_code == 400 and "1 proposal(s) still need a decision" in r.text
    proposals[1]["decision"] = "rejected"
    client.post("/api/runs/ch01/resume", json={"edits": {"research_proposals": proposals}})
    s = _wait(client, "ch01")
    assert s["next"] == ["human_gate_outline"]
    notes = s["values"]["research_notes"]
    assert "MAKE IT THE SHERDEN CAPTAIN" in notes and "THE TEMPLE OF AMUN" in notes
    assert "historian proposal B" not in notes and "ACCEPTED WITH CHANGES" in notes

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

    assert client.post("/api/runs/lore-tiye/resume", json={"edits": {}}).status_code == 400  # undecided
    client.post("/api/runs/lore-tiye/resume", json={"edits": {"research_proposals": _decide_all(s)}})
    s = _wait(client, "lore-tiye")
    assert s["next"] == ["human_gate_outline"]
    assert "MAYBE: an idea the author is keeping open" in s["values"]["research_notes"]
    assert s["values"]["lore_doc"].startswith("# Placeholder lore document")

    client.post("/api/runs/lore-tiye/regenerate", json={"notes": "more about her mother"})
    s = _wait(client, "lore-tiye")
    assert s["next"] == ["human_gate_outline"]
    assert "more about her mother" in s["values"]["lore_doc"]

    edited = ("# Tiye\n\nBorn in Thebes. EDITED.\n\n## Proposed open questions\n- Who was her mother?\n\n"
              "## Hooks\n- Placeholder hook one.\n- Placeholder hook two,\n  wrapped.\n")
    client.post("/api/runs/lore-tiye/resume", json={"edits": {"lore_doc": edited}})
    s = _wait(client, "lore-tiye")
    assert s["next"] == ["human_gate_ledger"]

    assert client.post("/api/runs/lore-tiye/adopt", json={"file": "../evil"}).status_code == 400
    r = client.post("/api/runs/lore-tiye/adopt", json={"file": "world"})
    assert r.status_code == 200, r.text
    assert r.json()["adopted_to"] == "world"
    world = client.get("/api/lore/prehistory").json()["world"]
    assert world.startswith("Egypt, 1160 BCE. Tiye plots.") and "Born in Thebes. EDITED." in world

    ledger = s["values"]["proposed_ledger"]
    hooks = [e for e in ledger if e["kind"] == "hook"]
    questions = [e for e in ledger if e["kind"] == "new_question"]
    assert [h["detail"] for h in hooks] == ["Placeholder hook one.", "Placeholder hook two, wrapped."]
    assert [q["detail"] for q in questions if q["entity"] == "Tiye backstory"] == ["Who was her mother?"]
    assert all(e["accepted"] for e in hooks + questions)
    hooks[1]["accepted"] = False  # the author drops one hook at the ledger gate
    client.post("/api/runs/lore-tiye/resume", json={"edits": {"proposed_ledger": ledger}})
    s = _wait(client, "lore-tiye")
    assert s["values"]["review_status"] == "COMMITTED"
    assert [h["text"] for h in client.get("/api/lore/hooks").json()] == ["Placeholder hook one."]
    assert "Who was her mother?" in [q["question"] for q in client.get("/api/lore/open-questions").json()]
    assert client.post("/api/runs/lore-tiye/adopt", json={"file": "characters"}).status_code == 200
    assert "Born in Thebes" in client.get("/api/lore/prehistory").json()["characters"]


def test_hooks_api(client):
    h = client.post("/api/lore/hooks", json={"text": "Jon finds the tanks", "about": "Jon"}).json()
    assert h["created_by"] == "user"
    assert client.post("/api/lore/hooks", json={"text": "  "}).status_code == 400
    assert [x["text"] for x in client.get("/api/lore/hooks").json()] == ["Jon finds the tanks"]
    client.delete(f"/api/lore/hooks/{h['id']}")
    assert client.get("/api/lore/hooks").json() == []


def test_adopt_rejects_non_lore_runs(client):
    client.post("/api/runs", json={"id": "r2", "type": "research", "researchers": []})
    assert client.post("/api/runs/r2/adopt", json={"file": "world"}).status_code == 400


def test_timelines_api(client):
    w = client.post("/api/lore/events", json={"title": "Elam attacks Babylon"}).json()
    p = client.post("/api/lore/events", json={"title": "The embassy", "category": "personal", "scope": "chapter"}).json()
    assert w["category"] == "world" and p["category"] == "personal"

    r = client.put("/api/lore/timelines/Ramesses%20III", json={"ids": [p["id"], w["id"]]})
    assert r.status_code == 200, r.text
    view = client.get("/api/lore/timelines").json()
    assert view["lanes"]["Ramesses III"] == [p["id"], w["id"]]
    assert "Ramesses III" in view["characters"]
    evs = {e["id"]: e for e in client.get("/api/lore/events").json()}
    assert evs[p["id"]]["characters"] == ["Ramesses III"]

    assert client.put("/api/lore/timelines/Jon", json={"ids": ["ev-nope"]}).status_code == 400
    assert client.put("/api/lore/timelines/bad%2Aname", json={"ids": []}).status_code == 400


def test_author_research_notes_reach_every_later_node(client):
    client.post("/api/runs", json={"id": "ch01", "type": "chapter", "title": "T", "brief": "b",
                                   "pov": "Tiye", "researchers": ["historian"]})
    client.post("/api/runs/ch01/start")
    s = _wait(client, "ch01")
    client.post("/api/runs/ch01/resume", json={"edits": {"author_research_notes": "TIYE IS LEFT-HANDED",
                                                         "research_proposals": _decide_all(s)}})
    s = _wait(client, "ch01")
    assert s["next"] == ["human_gate_outline"]
    assert "Author's notes on the research" in s["values"]["chapter_outline"]
    assert "TIYE IS LEFT-HANDED" in s["values"]["chapter_outline"]
    notes = app_module.runs.run_dir("ch01") / "notes.md"
    assert notes.read_text() == "TIYE IS LEFT-HANDED"

    client.post("/api/runs/ch01/resume", json={"edits": {"author_research_notes": "TIYE SWITCHED HANDS"}})
    s = _wait(client, "ch01")
    assert s["next"] == ["human_gate_final"]
    assert "TIYE SWITCHED HANDS" in s["values"]["draft_prose"]
    assert notes.read_text() == "TIYE SWITCHED HANDS"

    client.post("/api/runs/ch01/resume", json={"edits": {}})
    s = _wait(client, "ch01")
    assert all("characters" in e for e in s["values"]["proposed_ledger"])
    client.post("/api/runs/ch01/resume", json={"edits": {}})
    s = _wait(client, "ch01")
    assert s["values"]["review_status"] == "COMMITTED"
    assert notes.read_text() == "TIYE SWITCHED HANDS"


def test_regenerate_research_clears_proposals(client):
    client.post("/api/runs", json={"id": "r9", "type": "research", "researchers": ["historian"]})
    client.post("/api/runs/r9/start")
    s = _wait(client, "r9")
    s["values"]["research_proposals"][0]["decision"] = "rejected"
    client.post("/api/runs/r9/regenerate", json={"notes": "dig deeper"})
    s = _wait(client, "r9")
    assert s["next"] == ["human_gate_research"]
    assert {p["decision"] for p in s["values"]["research_proposals"]} == {"pending"}
    assert s["values"]["research_proposals_cut"] == []


def test_editor_runs_when_there_are_many_proposals(client):
    client.post("/api/runs", json={"id": "r10", "type": "research", "researchers": ["historian", "psychologist"]})
    client.post("/api/runs/r10/start")
    s = _wait(client, "r10")
    assert s["next"] == ["human_gate_research"]
    assert [u["node"] for u in s["usage"]].count("research_editor") == 1
    assert len(s["values"]["research_proposals"]) == 4  # the fake editor keeps everything
