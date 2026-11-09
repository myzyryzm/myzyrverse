"""Canned node outputs for FAKE_LLM=1 (UI and graph testing without usage).

Each fake echoes the start of the prompt it received, so you can confirm in the
UI that edits made at a gate are what the next node actually saw.
"""

from __future__ import annotations

import os

from .runner import AgentResult

# Set FAKE_CRITIC_FAIL=N to make the fake critic fail the first N drafts.
_critic_calls: dict[str, int] = {}


def _echo(prompt: str) -> str:
    """Show the first line of each input section the node received."""
    lines = []
    for section in prompt.split("\n\n---\n\n")[1:]:  # skip the canon block
        head, _, body = section.strip().partition("\n")
        first = body.strip().replace("\n", " ")[:160]
        lines.append(f"- **{head.lstrip('# ')}**: {first}")
    return "\n\n<details><summary>inputs this node saw (fake mode)</summary>\n\n" + "\n".join(lines) + "\n</details>"


def fake_result(node: str, prompt: str, schema: dict | None) -> AgentResult:
    if node in ("antiquarian", "historian", "mythographer", "psychologist"):
        return AgentResult(text="", structured_output={
            "background": [{"heading": f"{node} context", "refs": [1],
                            "body": f"- ({node}) placeholder finding one [1]\n- ({node}) placeholder finding two" + _echo(prompt)}],
            "proposals": [
                {"title": f"{node} proposal A", "pitch": f"({node}) placeholder pitch A [1]", "affects": ["Tiye"],
                 "parts": [{"label": "characterization", "text": "Placeholder characterization [1]", "refs": [1]},
                           {"label": "integration", "text": "Placeholder integration", "refs": []}],
                 "questions": [f"({node}) who pays for this?"]},
                {"title": f"{node} proposal B", "pitch": f"({node}) placeholder pitch B", "affects": [],
                 "parts": [{"label": "plot", "text": "Placeholder plot turn", "refs": []}], "questions": []},
            ],
            "sources": [{"n": 1, "title": "Placeholder source", "url": "https://example.org/source"}],
        })
    if node == "weaver":
        return AgentResult(text="### Scene 1\n- Beat: placeholder\n\n### Scene 2\n- Beat: placeholder" + _echo(prompt))
    if node == "loremaster":
        return AgentResult(text="# Placeholder lore document\n\n## Origins\nPlaceholder background." + _echo(prompt))
    if node == "writer":
        return AgentResult(text="The lamps guttered in the harem corridor. (fake prose)" + _echo(prompt))
    if node == "grand_critic":
        fails = int(os.environ.get("FAKE_CRITIC_FAIL", "0"))
        key = str(hash(prompt[:200]))
        n = _critic_calls.get(key, 0)
        _critic_calls[key] = n + 1
        verdict = "FAILED" if n < fails else "PASSED"
        return AgentResult(text="", structured_output={
            "verdict": verdict, "score": 5 if verdict == "FAILED" else 8, "tone_drift": "none",
            "summary": f"fake critic: {verdict}",
            "notes": [{"issue": "placeholder issue", "quote": "lamps guttered", "fix": "placeholder fix"}],
        })
    if node == "archivist" and "sub_event entry" in prompt:
        return AgentResult(text="", structured_output={
            "summary": "Placeholder arc plan summary.",
            "characters_present": ["Tiye", "Pentawere"],
            "entries": [
                {"kind": "sub_event", "entity": "Grain convoys fail", "change": "1", "detail": "Placeholder milestone", "ref_id": "", "characters": ["Tiye"], "confidence": "medium"},
                {"kind": "sub_event", "entity": "Sherden demand pay", "change": "2", "detail": "Placeholder milestone", "ref_id": "", "characters": [], "confidence": "medium"},
            ],
        })
    if node == "archivist":
        return AgentResult(text="", structured_output={
            "summary": "Placeholder summary of the run.",
            "characters_present": ["Tiye", "Pentawere"],
            "entries": [
                {"kind": "lore", "entity": "Tiye", "change": "status", "detail": "Placeholder lore change", "ref_id": "", "characters": ["Tiye"], "confidence": "medium"},
                {"kind": "new_question", "entity": "Sherden", "change": "question", "detail": "Who pays the Sherden after the coup?", "ref_id": "", "characters": [], "confidence": "medium"},
            ],
        })
    raise ValueError(f"no fake for node {node}")
