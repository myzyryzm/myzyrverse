"""The structured arc plan: what the arcmaster returns and the author edits at the outline gate.

    {"overview": str, "milestones": [{"title", "description", "characters", "follows_from"}], "risks": [str]}

Milestones are in story order. The archivist turns each one into a sub_event ledger row
directly (milestone_entries), so none is dropped or reworded on the way to the ledger.
Plain imports only: metrics, app and the nodes all use this module.
"""

from __future__ import annotations

ARC_PLAN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["overview", "milestones", "risks"],
    "properties": {
        "overview": {"type": "string"},
        "milestones": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "description", "characters", "follows_from"],
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "characters": {"type": "array", "items": {"type": "string"}},
                    "follows_from": {"type": "string"},
                },
            },
        },
        "risks": {"type": "array", "items": {"type": "string"}},
    },
}


def _s(v) -> str:
    return v.strip() if isinstance(v, str) else ""


def clean_plan(raw) -> dict:
    """A well-formed plan from model output or a gate edit. Milestones without a title are dropped.

    A string (a plan from before plans were structured) becomes the overview.
    """
    if isinstance(raw, str):
        return {"overview": raw.strip(), "milestones": [], "risks": []}
    raw = raw if isinstance(raw, dict) else {}
    milestones = []
    for m in raw.get("milestones") or []:
        if not isinstance(m, dict) or not _s(m.get("title")):
            continue
        chars = [c.strip() for c in m.get("characters") or [] if isinstance(c, str) and c.strip()]
        milestones.append({"title": _s(m.get("title")), "description": _s(m.get("description")),
                           "characters": list(dict.fromkeys(chars)), "follows_from": _s(m.get("follows_from"))})
    risks = [_s(r) for r in raw.get("risks") or [] if _s(r)]
    return {"overview": _s(raw.get("overview")), "milestones": milestones, "risks": risks}


def render_plan(plan) -> str:
    """Markdown for prompts, the plan.md artifact and edit metrics."""
    if not plan:
        return ""
    p = clean_plan(plan)
    out = [p["overview"] or "(no overview)", "", "## Milestones"]
    if not p["milestones"]:
        out.append("(none)")
    for n, m in enumerate(p["milestones"], 1):
        out.append(f"{n}. **{m['title']}**: {m['description'] or '(no description)'}")
        if m["characters"]:
            out.append(f"   - Involved: {', '.join(m['characters'])}")
        if m["follows_from"]:
            out.append(f"   - Follows from: {m['follows_from']}")
    out += ["", "## Risks"]
    out += [f"- {r}" for r in p["risks"]] or ["(none)"]
    return "\n".join(out).strip()


def milestone_entries(plan, target_event_id: str) -> list[dict]:
    """Each milestone as a sub_event ledger row under the target event, ticked by default."""
    return [{"kind": "sub_event", "entity": m["title"], "change": str(n), "detail": m["description"],
             "ref_id": target_event_id or "", "characters": m["characters"], "confidence": "medium",
             "source": "ai", "accepted": True}
            for n, m in enumerate(clean_plan(plan)["milestones"], 1)]
