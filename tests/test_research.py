"""Merging and rendering structured research."""

from backend.nodes.researchers import merge_research, render_research


def _out(src_url, title="T"):
    return {
        "background": [{"heading": "Context", "body": "A fact [1]. Another [2].", "refs": [1, 2]}],
        "proposals": [{"title": title, "pitch": "Do it [2]", "affects": ["Tiye"],
                       "parts": [{"label": "plot", "text": "She acts [1, 2].", "refs": [1, 2]}],
                       "questions": ["Who knows?", "  "]}],
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
    assert props[1]["parts"][0]["text"] == "She acts [1, 3]."
    assert props[1]["questions"] == [{"q": "Who knows?", "answer": ""}]
    assert props[1]["id"] == "mythographer-1" and props[1]["decision"] == "pending"


def test_render_applies_decisions_and_drops_refs():
    bg, props, _ = merge_research(["historian"], {"historian": {**_out("https://h.org"), "proposals": [
        _out("")["proposals"][0], {**_out("")["proposals"][0], "title": "GONE"}]}})
    props[0].update(decision="modified", note="change X")
    props[0]["parts"][0]["note"] = "part note"
    props[0]["questions"][0]["answer"] = "the vizier"
    props[1]["decision"] = "rejected"
    text = render_research(bg, props)
    assert "GONE" not in text and "1 proposal(s) were rejected" in text
    assert "ACCEPTED WITH CHANGES" in text and "change X" in text and "part note" in text
    assert "Who knows? -> Author's answer: the vizier" in text
    assert "[1]" not in text and "A fact. Another." in text


def test_render_without_proposals_is_background_only():
    text = render_research([{"researcher": "psychologist", "heading": "", "body": "plain notes"}], [])
    assert "plain notes" in text and "## Proposals" not in text
