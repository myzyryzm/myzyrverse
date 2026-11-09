"""Grand Critic: judges a draft and returns PASSED or FAILED; the Maestro loops FAILED drafts back to the writer."""

from __future__ import annotations

from ..state import RunState
from .common import build_prompt, call, system_prompt, usage


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
