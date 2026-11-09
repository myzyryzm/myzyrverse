"""Graph state for one run (a chapter, a research session, an arc plan, or a lore document).

Each node returns a partial dict; LangGraph merges it field by field. Fields
annotated with operator.add append instead of overwrite, so the draft history
and the per-node usage records accumulate across the critique loop.
"""

from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

RunType = Literal["chapter", "research", "plan_arc", "lore"]

# review_status values, in pipeline order
RESEARCHING = "RESEARCHING"
PENDING_RESEARCH_REVIEW = "PENDING_RESEARCH_REVIEW"
RESEARCH_APPROVED = "RESEARCH_APPROVED"
PENDING_OUTLINE_REVIEW = "PENDING_OUTLINE_REVIEW"
OUTLINE_APPROVED = "OUTLINE_APPROVED"
PENDING_FINAL_REVIEW = "PENDING_FINAL_REVIEW"
FINAL_APPROVED = "FINAL_APPROVED"
PENDING_LEDGER_REVIEW = "PENDING_LEDGER_REVIEW"
LEDGER_APPROVED = "LEDGER_APPROVED"
COMMITTED = "COMMITTED"


class RunState(TypedDict, total=False):
    # inputs
    run_id: str
    run_type: RunType
    title: str
    brief: str
    pov: str
    researchers: list[str]
    target_event_id: str
    canon: dict  # prehistory, present_lore, open_questions, events, previous_summaries

    # research: each researcher's structured output (background, proposals, sources)
    antiquarian_research: dict
    historian_research: dict
    mythographer_research: dict
    psychologist_research: dict
    research_complete: bool
    # merged by join_research; proposals carry the author's decisions and notes from the research gate
    research_background: list[dict]
    research_proposals: list[dict]
    research_sources: list[dict]
    # rendered from background + proposals (no sources); what every later node reads
    research_notes: str

    # outline / arc plan / lore document
    chapter_outline: str
    arc_plan: str
    lore_doc: str

    # prose + critique loop
    draft_prose: str
    draft_history: Annotated[list[str], operator.add]
    revision_count: int
    critique_verdict: str  # PASSED | FAILED | ""
    critique_notes: str

    # ledger
    proposed_ledger: list[dict]
    summary: str
    characters_present: list[str]

    # author steering for a regenerate (consumed by the next node that runs)
    author_notes: str
    # the author's own notes on the research: never cleared, fed to every later step
    author_research_notes: str

    # control
    next_steps: str | list[str]
    review_status: str
    usage: Annotated[list[dict], operator.add]
