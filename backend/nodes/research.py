"""The four parallel researchers and the join node.

Maestro returns the list of researchers ticked for this run; LangGraph runs
them in one superstep, and each has a static edge to join_research, which
therefore runs once after all of them finish.
"""

from __future__ import annotations

from .. import logbus
from ..state import PENDING_RESEARCH_REVIEW, RunState
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


def make_researcher(name: str):
    async def researcher(state: RunState) -> dict:
        prompt = build_prompt(state, task=TASKS[name])
        result = await call(name, state, prompt, sys_prompt=system_prompt(name), research=True)
        return {f"{name}_notes": result.text, "usage": usage(name, result)}

    researcher.__name__ = name
    return researcher


async def join_research(state: RunState) -> dict:
    sections = []
    for name in state.get("researchers") or []:
        notes = (state.get(f"{name}_notes") or "").strip()
        if notes:
            sections.append(f"## {LABELS.get(name, name)}\n\n{notes}")
    logbus.log(state.get("run_id"), "join_research: merged " + ", ".join(state.get("researchers") or []))
    return {
        "research_notes": "\n\n".join(sections),
        "research_complete": True,
        "review_status": PENDING_RESEARCH_REVIEW,
        "author_notes": "",
    }
