"""Research editor: cuts the merged proposals down to the few worth the author's time.

The researchers work in parallel and never see each other's proposals, so the
merged list repeats itself and runs long. The editor picks the strongest
distinct ideas (at most config.MAX_PROPOSALS) and names the duplicates of each.
It only points at proposals by id and never rewrites them, so their text and
source numbers stay exactly as the researcher wrote them. Everything it leaves
out goes to `research_proposals_cut`, where the author can bring one back.
"""

from __future__ import annotations

from .. import config, logbus
from ..state import PENDING_RESEARCH_REVIEW, RunState
from .common import build_prompt, call, system_prompt, usage
from .researchers import LABELS, render_research, strip_refs

EDITOR_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["selected"],
    "properties": {
        "selected": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "duplicates", "reason"],
                "properties": {
                    "id": {"type": "string"},
                    "duplicates": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                },
            },
        },
    },
}


def render_candidates(proposals: list[dict]) -> str:
    out = []
    for p in proposals:
        out += [f"### [id: {p['id']}] {p['title']}",
                f"From: {LABELS.get(p['researcher'], p['researcher']).split(':')[0]}"]
        if p.get("affects"):
            out.append(f"Affects: {', '.join(p['affects'])}")
        out += [f"**{pt['label'].capitalize()}**: {strip_refs(pt.get('text', ''))}" for pt in p.get("parts") or []]
        out.append("")
    return "\n".join(out).strip()


def apply_selection(proposals: list[dict], selected: list[dict], limit: int) -> tuple[list[dict], list[dict]]:
    """Split proposals into (kept, cut) by the editor's selection. Unknown and repeated ids are ignored."""
    by_id = {p["id"]: p for p in proposals}
    kept, used = [], set()
    for s in selected:
        p = by_id.get(s.get("id"))
        if not p or p["id"] in used or len(kept) >= limit:
            continue
        used.add(p["id"])
        also = []
        for d in s.get("duplicates") or []:
            dup = by_id.get(d)
            if dup and d not in used:
                used.add(d)
                if dup["researcher"] != p["researcher"] and dup["researcher"] not in also:
                    also.append(dup["researcher"])
        kept.append({**p, "also_from": also})
    kept_ids = {p["id"] for p in kept}
    return kept, [p for p in proposals if p["id"] not in kept_ids]


async def research_editor(state: RunState) -> dict:
    proposals = state.get("research_proposals") or []
    limit = config.MAX_PROPOSALS
    prompt = build_prompt(
        state, ("Proposals from the researchers", render_candidates(proposals)),
        task=f"Select at most {limit} of these proposals for the author to review, strongest first.",
    )
    result = await call("research_editor", state, prompt, sys_prompt=system_prompt("research_editor"),
                        output_schema=EDITOR_SCHEMA)
    out = result.structured_output if isinstance(result.structured_output, dict) else {}
    kept, cut = apply_selection(proposals, out.get("selected") or [], limit)
    if not kept:
        # No usable selection: show the author everything rather than nothing.
        logbus.log(state.get("run_id"), "research_editor: no usable selection; kept every proposal", kind="warn")
        kept, cut = proposals, []
    else:
        logbus.log(state.get("run_id"), f"research_editor: kept {len(kept)} of {len(proposals)} proposals")
    return {
        "research_proposals": kept,
        "research_proposals_cut": cut,
        "research_notes": render_research(state.get("research_background") or [], kept),
        "review_status": PENDING_RESEARCH_REVIEW,
        "usage": usage("research_editor", result),
    }
