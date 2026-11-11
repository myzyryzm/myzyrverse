"""Merging and rendering structured research, and the research editor's selection."""

from backend import config
from backend.nodes.archivist import doc_entries
from backend.nodes.loremaster import doc_list
from backend.nodes.research_editor import apply_selection
from backend.nodes.researchers import merge_research, render_research


def _out(src_url, title="T"):
    return {
        "background": [{"heading": "Context", "body": "A fact [1]. Another [2].", "refs": [1, 2]}],
        "proposals": [{"title": title, "kind": "plot", "text": "She acts [1, 2].", "canon_fit": "Fits [2].",
                       "affects": ["Tiye"], "refs": [1, 2], "questions": ["Who knows?", "  ", "Q2", "Q3"]}],
        "sources": [{"n": 1, "title": "Shared", "url": "https://x.org/a/"},
                    {"n": 2, "title": "Own", "url": src_url}],
    }


def test_merge_numbers_sources_across_researchers():
    bg, props, sources = merge_research(["historian", "mythographer"],
                                        {"historian": _out("https://h.org"), "mythographer": _out("https://m.org")})
    assert [s["n"] for s in sources] == [1, 2, 3]
    assert sources[0]["researchers"] == ["historian", "mythographer"]
    # mythographer's local [2] is run-wide source 3
    assert bg[1]["body"] == "A fact [1]. Another [3]." and bg[1]["refs"] == [1, 3]
    assert props[1]["kind"] == "plot"
    assert [(pt["label"], pt["text"]) for pt in props[1]["parts"]] == [("plot", "She acts [1, 3]."),
                                                                      ("integration", "Fits [3].")]
    assert props[1]["parts"][0]["refs"] == [1, 3]
    assert props[1]["questions"] == [{"q": "Who knows?", "answer": ""}, {"q": "Q2", "answer": ""}]  # capped at 2
    assert props[1]["id"] == "mythographer-1" and props[1]["decision"] == "pending"


def test_merge_caps_proposals_per_researcher():
    out = _out("https://h.org")
    out["proposals"] = [{**out["proposals"][0], "title": f"P{i}"} for i in range(6)]
    _, props, _ = merge_research(["historian"], {"historian": out})
    assert [p["title"] for p in props] == [f"P{i}" for i in range(config.MAX_PROPOSALS_PER_RESEARCHER)]


def test_render_applies_decisions_and_drops_refs():
    bg, props, _ = merge_research(["historian"], {"historian": {**_out("https://h.org"), "proposals": [
        _out("")["proposals"][0], {**_out("")["proposals"][0], "title": "GONE"}]}})
    props[0].update(decision="accepted", note="change X")
    props[0]["parts"][0]["note"] = "part note"
    props[0]["questions"][0]["answer"] = "the vizier"
    props[1]["decision"] = "rejected"
    text = render_research(bg, props)
    assert "GONE" not in text and "1 proposal(s) were rejected" in text
    assert "ACCEPTED WITH CHANGES" in text and "change X" in text and "part note" in text
    assert "Who knows? -> Author's answer: the vizier" in text
    assert "[1]" not in text and "A fact. Another." in text


def test_render_status_lines():
    _, props, _ = merge_research(["historian"], {"historian": {**_out("https://h.org"), "proposals": [
        {**_out("")["proposals"][0], "title": t} for t in ("PLAIN", "MAYBE", "LEGACY")]}})
    props[0]["decision"] = "accepted"
    props[1]["decision"] = "maybe"
    props[2]["decision"] = "modified"  # old runs: still reads as accepted with changes
    text = render_research([], props)
    plain, maybe, legacy = text.split("### ")[1:]
    assert "Status: ACCEPTED by the author" in plain
    assert "Status: MAYBE" in maybe and "ACCEPTED" not in maybe
    assert "ACCEPTED WITH CHANGES" in legacy
    assert "rejected" not in text


def _p(pid, researcher):
    return {"id": pid, "researcher": researcher, "title": pid, "parts": []}


def test_editor_selection_keeps_order_merges_duplicates_and_cuts_the_rest():
    props = [_p("historian-1", "historian"), _p("historian-2", "historian"),
             _p("mythographer-1", "mythographer"), _p("psychologist-1", "psychologist")]
    kept, cut = apply_selection(props, [
        {"id": "mythographer-1", "duplicates": ["historian-2", "nope"], "reason": ""},
        {"id": "historian-2", "duplicates": [], "reason": ""},  # already merged into the first
        {"id": "ghost", "duplicates": [], "reason": ""},
        {"id": "historian-1", "duplicates": [], "reason": ""},
    ], limit=8)
    assert [p["id"] for p in kept] == ["mythographer-1", "historian-1"]
    assert kept[0]["also_from"] == ["historian"] and kept[1]["also_from"] == []
    assert [p["id"] for p in cut] == ["historian-2", "psychologist-1"]


def test_editor_selection_respects_the_limit():
    props = [_p(f"historian-{i}", "historian") for i in range(5)]
    kept, cut = apply_selection(props, [{"id": p["id"], "duplicates": [], "reason": ""} for p in props], limit=2)
    assert len(kept) == 2 and len(cut) == 3


def test_render_without_proposals_is_background_only():
    text = render_research([{"researcher": "psychologist", "heading": "", "body": "plain notes"}], [])
    assert "plain notes" in text and "## Proposals" not in text


DOC = """# Guild

## Summary
- not a hook

## Proposed open questions
- Did the beds ever **fail**?
- How many nodes exist?

## Hooks
- Tyre holds the autumn run,
  and the guild bends.
  - a sub-point
* Jon finds the tanks.
Trailing prose ends the list.
- not a hook either
"""


def test_doc_list_reads_one_section():
    assert doc_list(DOC, "Proposed open questions") == ["Did the beds ever fail?", "How many nodes exist?"]
    assert doc_list(DOC, "Hooks") == ["Tyre holds the autumn run, and the guild bends. a sub-point", "Jon finds the tanks."]
    assert doc_list(DOC, "Missing") == []


def test_doc_entries_are_ticked_rows_and_skip_known_questions():
    rows = doc_entries(DOC, "Purple guild", {"how many nodes exist?"})
    assert [(r["kind"], r["detail"]) for r in rows] == [
        ("new_question", "Did the beds ever fail?"),
        ("hook", "Tyre holds the autumn run, and the guild bends. a sub-point"),
        ("hook", "Jon finds the tanks."),
    ]
    assert all(r["accepted"] and r["entity"] == "Purple guild" for r in rows)
