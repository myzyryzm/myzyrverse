"""Prompt assembly shared by every LLM node."""

from __future__ import annotations

from functools import lru_cache

from .. import config
from ..runner import AgentResult, run_agent
from ..state import RunState


@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    return (config.PROMPTS_DIR / f"{name}.md").read_text().strip()


def system_prompt(node_prompt: str, *, tone: bool = False) -> str:
    parts = [load_prompt("canon_rules"), load_prompt(node_prompt)]
    if tone:
        parts.append(load_prompt("tone"))
    return "\n\n---\n\n".join(parts)


def _render_events(events: list[dict]) -> list[str]:
    by_parent: dict = {}
    for e in events:
        by_parent.setdefault(e.get("parent_id"), []).append(e)
    lines: list[str] = []

    def walk(parent, depth):
        for e in sorted(by_parent.get(parent, []), key=lambda x: x.get("order") or 0):
            target = f"; targets {e['target_run']}" if e.get("target_run") else ""
            chars = f"; characters: {', '.join(e['characters'])}" if e.get("characters") else ""
            lines.append(f"{'  ' * depth}- [{e['id']}] ({e.get('scope', 'arc')}, {e.get('status', 'planned')}) "
                         f"**{e.get('title', '')}**: {e.get('description', '')}{chars}{target}")
            walk(e["id"], depth + 1)

    walk(None, 0)
    known = {e["id"] for e in events}
    for e in events:  # orphans whose parent was deleted
        if e.get("parent_id") and e["parent_id"] not in known:
            lines.append(f"- [{e['id']}] ({e.get('status', 'planned')}) **{e.get('title', '')}**: {e.get('description', '')}")
    return lines


def render_canon(canon: dict) -> str:
    out = ["# Canon", "", "## Prehistory (author's seed canon)"]
    prehistory = canon.get("prehistory") or {}
    if not any(t.strip() for t in prehistory.values()):
        out.append("(empty)")
    for name, text in prehistory.items():
        out += [f"### {name}", text.strip() or "(empty)", ""]

    out += ["## Present (changes since the story began; overrides prehistory)", canon.get("present_lore") or "(none)", ""]

    questions = canon.get("open_questions") or []
    out.append("## Open questions")
    if not questions:
        out.append("(none)")
    for q in questions:
        about = f" (about {q['about']})" if q.get("about") else ""
        if q.get("status") == "answered":
            out.append(f"- [{q['id']}] answered{about}: {q['question']} -> {q.get('answer', '')}")
        else:
            out.append(f"- [{q['id']}] OPEN{about}: {q['question']}")
    out.append("")

    out.append("## Planned events (author's steering)")
    out += _render_events(canon.get("events") or []) or ["(none)"]
    out.append("")

    summaries = canon.get("previous_summaries") or []
    out.append("## Story so far")
    if not summaries:
        out.append("(this is the first chapter)")
    for s in summaries:
        out += [f"### Chapter {s.get('order')}: {s.get('title')} (POV: {s.get('pov') or '?'})", s.get("summary") or "(no summary)", ""]
    return "\n".join(out).strip()


def render_run(state: RunState) -> str:
    lines = ["# This run", f"- type: {state.get('run_type')}", f"- title: {state.get('title') or state.get('run_id')}"]
    if state.get("pov"):
        lines.append(f"- POV character: {state['pov']}")
    if state.get("target_event_id"):
        lines.append(f"- target event: {state['target_event_id']}")
    lines += ["", "## Author's brief", state.get("brief") or "(no brief)"]
    return "\n".join(lines)


def build_prompt(state: RunState, *sections: tuple[str, str], task: str) -> str:
    parts = [render_canon(state.get("canon") or {}), render_run(state)]
    for title, body in sections:
        if body and body.strip():
            parts.append(f"# {title}\n\n{body.strip()}")
    if state.get("author_notes"):
        parts.append(f"# Author's notes for this pass (highest priority)\n\n{state['author_notes'].strip()}")
    parts.append(f"## Your task\n\n{task.strip()}")
    return "\n\n---\n\n".join(parts)


async def call(node: str, state: RunState, prompt: str, *, sys_prompt: str,
               output_schema: dict | None = None, research: bool = False) -> AgentResult:
    kwargs = {}
    if research:
        config.SOURCES_DIR.mkdir(parents=True, exist_ok=True)
        kwargs["cwd"] = config.SOURCES_DIR
    return await run_agent(prompt, node=node, system_prompt=sys_prompt, run_id=state.get("run_id"),
                           output_schema=output_schema, **kwargs)


def usage(node: str, result: AgentResult) -> list[dict]:
    return [result.usage_record(node, config.NODE_SETTINGS[node]["model"])]
