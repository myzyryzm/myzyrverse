"""Weaver (outline or arc plan), Maester writer, and Grand Critic."""

from __future__ import annotations

from ..state import PENDING_OUTLINE_REVIEW, RunState
from .common import build_prompt, call, system_prompt, usage


async def weaver(state: RunState) -> dict:
    research = ("Approved research", state.get("research_notes", ""))
    if state.get("run_type") == "plan_arc":
        prompt = build_prompt(
            state, research,
            task=(f"Plan the arc toward target event {state.get('target_event_id') or '(see brief)'}. "
                  "Write markdown: a short causal overview, then a numbered list of milestones. For each milestone give "
                  "a bold title, what happens, who is involved, and why it follows from the previous one. "
                  "End with a `## Risks` section."),
        )
        result = await call("weaver", state, prompt, sys_prompt=system_prompt("weaver_arc"))
        return {"arc_plan": result.text, "review_status": PENDING_OUTLINE_REVIEW,
                "author_notes": "", "usage": usage("weaver", result)}

    prompt = build_prompt(state, research, task="Write the beat sheet for this chapter.")
    result = await call("weaver", state, prompt, sys_prompt=system_prompt("weaver"))
    return {"chapter_outline": result.text, "review_status": PENDING_OUTLINE_REVIEW,
            "author_notes": "", "usage": usage("weaver", result)}


async def writer(state: RunState) -> dict:
    history = state.get("draft_history") or []
    sections = [
        ("Approved research (use for texture, not lectures)", state.get("research_notes", "")),
        ("Approved chapter outline", state.get("chapter_outline", "")),
    ]
    if history:
        sections += [("Previous draft", history[-1]), ("Critique of the previous draft", state.get("critique_notes", ""))]
        task = ("Revise the previous draft into a stronger chapter. Fix every issue in the critique and any author notes. "
                "Keep what works. Output the full revised chapter.")
    else:
        task = f"Write the chapter from {state.get('pov') or 'the POV character'}'s point of view, following the outline."
    prompt = build_prompt(state, *sections, task=task)
    result = await call("writer", state, prompt, sys_prompt=system_prompt("writer", tone=True))
    return {"draft_prose": result.text, "author_notes": "", "usage": usage("writer", result)}


CRITIC_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict", "score", "tone_drift", "summary", "notes"],
    "properties": {
        "verdict": {"type": "string", "enum": ["PASSED", "FAILED"]},
        "score": {"type": "integer", "minimum": 1, "maximum": 10},
        "tone_drift": {"type": "string", "enum": ["none", "sanitized", "nihilist"]},
        "summary": {"type": "string"},
        "notes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["issue", "quote", "fix"],
                "properties": {"issue": {"type": "string"}, "quote": {"type": "string"}, "fix": {"type": "string"}},
            },
        },
    },
}


def render_critique(c: dict, attempt: int) -> str:
    lines = [f"**Critic verdict: {c['verdict']}** (score {c['score']}/10, tone drift: {c['tone_drift']}, draft {attempt})",
             "", c.get("summary", ""), ""]
    for i, n in enumerate(c.get("notes") or [], 1):
        lines.append(f"{i}. **{n['issue']}**")
        if n.get("quote"):
            lines.append(f"   > {n['quote']}")
        lines.append(f"   Fix: {n['fix']}")
    return "\n".join(lines).strip()


async def grand_critic(state: RunState) -> dict:
    prompt = build_prompt(
        state,
        ("Approved chapter outline", state.get("chapter_outline", "")),
        ("Draft chapter", state.get("draft_prose", "")),
        task="Judge the draft chapter against your checklist and return your verdict.",
    )
    result = await call("grand_critic", state, prompt, sys_prompt=system_prompt("grand_critic", tone=True),
                        output_schema=CRITIC_SCHEMA)
    c = result.structured_output
    if not isinstance(c, dict) or c.get("verdict") not in ("PASSED", "FAILED"):
        # The CLI could not produce schema-valid JSON; don't loop on garbage, escalate to the human.
        c = {"verdict": "PASSED", "score": 0, "tone_drift": "none", "notes": [],
             "summary": "Critic returned no structured verdict; sending to human review.\n\n" + (result.text or "")}
    return {
        "critique_verdict": c["verdict"],
        "critique_notes": render_critique(c, state.get("revision_count", 0) + 1),
        "usage": usage("grand_critic", result),
    }
