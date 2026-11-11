"""Loremaster: turns approved research into a lore document (backstory, profile).

The body states only what is established (canon, accepted proposals, the author's
notes and answers); gaps become proposed open questions and loose ideas become
hooks. At the ledger gate both lists arrive as ticked rows (archivist.doc_entries).

It plays the weaver's role in lore runs. Its output is a proposal: the author
reviews it at the outline gate and may adopt it into a prehistory file
afterwards (POST /api/runs/{id}/adopt). The AI never writes prehistory itself.
"""

from __future__ import annotations

import re

from ..state import PENDING_OUTLINE_REVIEW, RunState
from .common import build_prompt, call, system_prompt, usage


def doc_list(doc: str, heading: str) -> list[str]:
    """The bullets under `## <heading>` in a lore document, with bold markers removed.

    Indented lines (wrapped text or sub-bullets) join the bullet above them. The list
    ends at the next heading or at the first unindented line that is not a bullet.
    """
    items: list[str] = []
    inside = False
    for line in (doc or "").splitlines():
        s = line.strip()
        if s.startswith("#"):
            inside = s.lstrip("#").strip().lower() == heading.lower()
            continue
        if not inside or not s:
            continue
        if line[:1] in (" ", "\t") and items:
            items[-1] += " " + s.lstrip("-* ").strip()
        elif s.startswith(("- ", "* ")):
            items.append(s[2:].strip())
        else:
            inside = False
    return [t for t in (re.sub(r"\*\*|__", "", i).strip() for i in items) if t]


async def loremaster(state: RunState) -> dict:
    prompt = build_prompt(state, ("Approved research", state.get("research_notes", "")),
                          task="Write the lore document the author's brief asks for.")
    result = await call("loremaster", state, prompt, sys_prompt=system_prompt("loremaster"))
    return {"lore_doc": result.text, "review_status": PENDING_OUTLINE_REVIEW,
            "author_notes": "", "usage": usage("loremaster", result)}
