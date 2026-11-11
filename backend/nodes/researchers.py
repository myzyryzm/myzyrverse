"""The four parallel researchers and the join node.

Maestro returns the list of researchers ticked for this run; LangGraph runs
them in one superstep, and each has a static edge to join_research, which
therefore runs once after all of them finish.

Each researcher returns structured output (RESEARCH_SCHEMA): background
(context only), proposals (each one idea of one kind for this story, reviewed
one by one at the research gate) and sources. join_research merges them, numbers
the sources across the whole run, and renders `research_notes`, the markdown
every later node reads. The research editor then cuts the proposals down, and
the research gate re-renders the notes with the author's decisions.
"""

from __future__ import annotations

import re

from .. import config, logbus
from ..state import PENDING_RESEARCH_EDIT, PENDING_RESEARCH_REVIEW, RunState
from .common import build_prompt, call, system_prompt, usage

TASKS = {
    "antiquarian": "Research the Bronze Age grounding the author needs for this brief. Check the local source folder first, then the web.",
    "historian": "Find the strongest historical analogues from any era for this brief and show how each could be transformed into this universe.",
    "mythographer": "Find the most useful analogues from fiction, myth and drama for this brief and show how to transform or subvert them.",
    "psychologist": "Map the inner lives and frictions of the characters this brief touches.",
}

LABELS = {
    "antiquarian": "Antiquarian: Bronze Age grounding",
    "historian": "Historian: historical analogues",
    "mythographer": "Mythographer: fictional analogues",
    "psychologist": "Psychologist: character friction",
}

# A proposal is one idea of one kind. Stored proposals also carry `parts` (the idea itself, then
# how it fits canon) so the review card and render_research read old multi-part proposals too.
KINDS = ["characterization", "plot", "world"]
MAX_QUESTIONS = 2
# join_research sends the proposals to the research editor only when there are more than this.
EDIT_ABOVE = 3

_REFS = {"type": "array", "items": {"type": "integer"}}

RESEARCH_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["background", "proposals", "sources"],
    "properties": {
        "background": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["heading", "body", "refs"],
                "properties": {"heading": {"type": "string"}, "body": {"type": "string"}, "refs": _REFS},
            },
        },
        "proposals": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "kind", "text", "canon_fit", "affects", "refs", "questions"],
                "properties": {
                    "title": {"type": "string"},
                    "kind": {"type": "string", "enum": KINDS},
                    "text": {"type": "string"},
                    "canon_fit": {"type": "string"},
                    "affects": {"type": "array", "items": {"type": "string"}},
                    "refs": _REFS,
                    "questions": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["n", "title", "url"],
                "properties": {"n": {"type": "integer"}, "title": {"type": "string"}, "url": {"type": "string"}},
            },
        },
    },
}


def make_researcher(name: str):
    async def researcher(state: RunState) -> dict:
        prompt = build_prompt(state, task=TASKS[name])
        result = await call(name, state, prompt, sys_prompt=system_prompt(name, research=True), research=True,
                            output_schema=RESEARCH_SCHEMA)
        out = result.structured_output if isinstance(result.structured_output, dict) else None
        if not out:
            logbus.log(state.get("run_id"), f"{name}: no structured output; kept the text as background", kind="warn")
            out = {"background": [{"heading": "Notes", "body": result.text, "refs": []}], "proposals": [], "sources": []}
        return {f"{name}_research": out, "usage": usage(name, result)}

    researcher.__name__ = name
    return researcher


_REF_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


def _renumber(text: str, mapping: dict[int, int]) -> str:
    """Rewrite a researcher's local [n] markers to the run-wide source numbers."""
    def sub(m: re.Match) -> str:
        nums = [mapping.get(int(x)) for x in m.group(1).split(",")]
        nums = [n for n in nums if n]
        return f"[{', '.join(map(str, nums))}]" if nums else ""
    return _REF_RE.sub(sub, text or "")


def strip_refs(text: str) -> str:
    text = _REF_RE.sub("", text or "")
    text = re.sub(r"[ \t]+([.,;:])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return re.sub(r"[ \t]+\n", "\n", text).strip()


def merge_research(researchers: list[str], outputs: dict[str, dict]) -> tuple[list, list, list]:
    """Merge per-researcher output into (background, proposals, sources) with run-wide source numbers."""
    background, proposals, sources = [], [], []
    by_key: dict[str, dict] = {}
    for name in researchers:
        out = outputs.get(name) or {}
        mapping: dict[int, int] = {}
        for s in out.get("sources") or []:
            key = (s.get("url") or "").strip().rstrip("/").lower() or (s.get("title") or "").strip().lower()
            if not key:
                continue
            if key not in by_key:
                by_key[key] = {"n": len(sources) + 1, "title": s.get("title") or s.get("url") or "",
                               "url": s.get("url") or "", "researchers": []}
                sources.append(by_key[key])
            src = by_key[key]
            if name not in src["researchers"]:
                src["researchers"].append(name)
            mapping[int(s.get("n") or 0)] = src["n"]

        def refs(xs):
            return sorted({mapping[x] for x in xs or [] if x in mapping})

        for b in out.get("background") or []:
            background.append({"researcher": name, "heading": b.get("heading") or "",
                               "body": _renumber(b.get("body"), mapping), "refs": refs(b.get("refs"))})
        for i, p in enumerate((out.get("proposals") or [])[:config.MAX_PROPOSALS_PER_RESEARCHER], 1):
            kind = p.get("kind") if p.get("kind") in KINDS else "plot"
            parts = [{"label": kind, "text": _renumber(p.get("text"), mapping), "refs": refs(p.get("refs")), "note": ""}]
            if (p.get("canon_fit") or "").strip():
                parts.append({"label": "integration", "text": _renumber(p.get("canon_fit"), mapping), "refs": [], "note": ""})
            questions = [q for q in p.get("questions") or [] if q.strip()][:MAX_QUESTIONS]
            proposals.append({
                "id": f"{name}-{i}", "researcher": name, "kind": kind, "title": p.get("title") or f"Proposal {i}",
                "pitch": "", "affects": p.get("affects") or [], "parts": parts,
                "questions": [{"q": q, "answer": ""} for q in questions],
                "decision": "pending", "note": "",
            })
    return background, proposals, sources


ACCEPTED = "ACCEPTED by the author (treat as settled)"
ACCEPTED_WITH_CHANGES = "ACCEPTED WITH CHANGES by the author (settled once the author's changes below are applied)"
MAYBE = ("MAYBE: an idea the author is keeping open. Not settled. Use it only where it serves the brief; "
         "never record it as canon.")


def has_notes(p: dict) -> bool:
    return bool((p.get("note") or "").strip()) or any((pt.get("note") or "").strip() for pt in p.get("parts") or [])


def status_line(p: dict) -> str:
    """Accepted with a note means accepted with changes. `modified` is the old name for that."""
    if p.get("decision") in ("accepted", "modified"):
        return ACCEPTED_WITH_CHANGES if has_notes(p) or p.get("decision") == "modified" else ACCEPTED
    return MAYBE


def render_research(background: list[dict], proposals: list[dict]) -> str:
    """The markdown later nodes read. No sources or ref markers; rejected proposals are left out."""
    out = []
    if background:
        out.append("## Background (context)")
        current = None
        for b in background:
            if b["researcher"] != current:
                current = b["researcher"]
                out += ["", f"### {LABELS.get(current, current)}"]
            out += ["", f"#### {b['heading']}" if b.get("heading") else "", strip_refs(b.get("body", ""))]
    kept = [p for p in proposals if p.get("decision") != "rejected"]
    if kept:
        out += ["", "## Proposals"]
        for p in kept:
            out += ["", f"### {p['title']} ({LABELS.get(p['researcher'], p['researcher']).split(':')[0]})",
                    f"Status: {status_line(p)}"]
            if p.get("pitch"):
                out.append(strip_refs(p["pitch"]))
            if p.get("affects"):
                out.append(f"Affects: {', '.join(p['affects'])}")
            for pt in p.get("parts") or []:
                out += ["", f"**{pt['label'].capitalize()}**: {strip_refs(pt.get('text', ''))}"]
                if (pt.get("note") or "").strip():
                    out.append(f"Author's note: {pt['note'].strip()}")
            qs = p.get("questions") or []
            if qs:
                out += ["", "Questions this raises:"]
                for q in qs:
                    ans = (q.get("answer") or "").strip()
                    out.append(f"- {q['q']}" + (f" -> Author's answer: {ans}" if ans else " (unanswered)"))
            if (p.get("note") or "").strip():
                out += ["", f"Author's note on this proposal: {p['note'].strip()}"]
    rejected = len(proposals) - len(kept)
    if rejected:
        out += ["", f"({rejected} proposal(s) were rejected by the author and removed. Do not use them.)"]
    return "\n".join(out).strip()


def render_sources(sources: list[dict]) -> str:
    return "\n".join(f"{s['n']}. [{s['title']}]({s['url']})" if s.get("url") else f"{s['n']}. {s['title']}"
                     for s in sources)


async def join_research(state: RunState) -> dict:
    chosen = state.get("researchers") or []
    outputs = {name: state.get(f"{name}_research") or {} for name in chosen}
    background, proposals, sources = merge_research(chosen, outputs)
    logbus.log(state.get("run_id"), "join_research: merged " + ", ".join(chosen)
               + f" ({len(proposals)} proposals, {len(sources)} sources)")
    return {
        "research_background": background,
        "research_proposals": proposals,
        "research_proposals_cut": [],
        "research_sources": sources,
        "research_notes": render_research(background, proposals),
        "research_complete": True,
        "review_status": PENDING_RESEARCH_EDIT if len(proposals) > EDIT_ABOVE else PENDING_RESEARCH_REVIEW,
        "author_notes": "",
    }
