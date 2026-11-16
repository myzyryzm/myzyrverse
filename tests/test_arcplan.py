"""The structured arc plan helpers."""

from backend.arcplan import clean_plan, milestone_entries, render_plan

PLAN = {
    "overview": " Hunger drives the coup. ",
    "milestones": [
        {"title": "Grain convoys fail", "description": "The Nile is low.", "characters": ["Tiye", "Tiye", ""],
         "follows_from": "The drought"},
        {"title": "", "description": "dropped", "characters": [], "follows_from": ""},
        {"title": "Sherden demand pay", "description": "", "characters": [], "follows_from": ""},
    ],
    "risks": ["Too fast", " "],
}


def test_clean_plan_normalizes():
    p = clean_plan(PLAN)
    assert p["overview"] == "Hunger drives the coup."
    assert [m["title"] for m in p["milestones"]] == ["Grain convoys fail", "Sherden demand pay"]
    assert p["milestones"][0]["characters"] == ["Tiye"]
    assert p["risks"] == ["Too fast"]


def test_clean_plan_accepts_legacy_text_and_junk():
    assert clean_plan("old markdown plan") == {"overview": "old markdown plan", "milestones": [], "risks": []}
    assert clean_plan(None) == {"overview": "", "milestones": [], "risks": []}
    assert clean_plan({"milestones": ["nope", {"title": "Ok", "characters": [3, "A"]}]})["milestones"] == [
        {"title": "Ok", "description": "", "characters": ["A"], "follows_from": ""}]


def test_render_plan():
    md = render_plan(PLAN)
    assert md.startswith("Hunger drives the coup.")
    assert "1. **Grain convoys fail**: The Nile is low.\n   - Involved: Tiye\n   - Follows from: The drought" in md
    assert "2. **Sherden demand pay**: (no description)" in md
    assert md.endswith("## Risks\n- Too fast")
    assert render_plan({}) == "" and render_plan(None) == ""


def test_milestone_entries():
    rows = milestone_entries(PLAN, "ev-1")
    assert [(r["kind"], r["entity"], r["change"], r["ref_id"], r["characters"]) for r in rows] == [
        ("sub_event", "Grain convoys fail", "1", "ev-1", ["Tiye"]),
        ("sub_event", "Sherden demand pay", "2", "ev-1", []),
    ]
    assert all(r["accepted"] and r["source"] == "ai" for r in rows)
