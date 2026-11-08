"""One async entry point for every LLM call: run_agent().

It drives the Claude Agent SDK, which spawns the local `claude` CLI and
authenticates with your Claude Code login, so usage bills to the subscription
rather than an API key. This replaces the old LangChain/subprocess wrapper:
LangGraph nodes are plain async functions, so they can await this directly.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any

from . import config, logbus

# Built-ins that could change the filesystem or spawn work; nodes only read.
DISALLOWED_BUILTINS = [
    "Bash", "BashOutput", "KillShell", "Write", "Edit", "MultiEdit",
    "NotebookEdit", "Task", "TodoWrite", "ExitPlanMode",
]


@dataclass
class AgentResult:
    text: str
    structured_output: Any = None
    cost_usd: float | None = None
    duration_ms: int | None = None
    num_turns: int | None = None
    session_id: str | None = None
    usage: dict = field(default_factory=dict)

    def usage_record(self, node: str, model: str) -> dict:
        return {
            "node": node,
            "model": model,
            "cost_usd": self.cost_usd,
            "duration_ms": self.duration_ms,
            "num_turns": self.num_turns,
            "session_id": self.session_id,
        }


class AgentError(RuntimeError):
    pass


async def run_agent(
    prompt: str,
    *,
    node: str,
    system_prompt: str,
    run_id: str | None = None,
    output_schema: dict | None = None,
    cwd: str | os.PathLike | None = None,
    add_dirs: list[str | os.PathLike] | None = None,
    max_turns: int = 80,
) -> AgentResult:
    settings = config.NODE_SETTINGS[node]
    if config.FAKE_LLM:
        from .fakes import fake_result

        logbus.log(run_id, f"{node}: FAKE_LLM response")
        await asyncio.sleep(0.3)
        return fake_result(node, prompt, output_schema)

    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        TextBlock,
        ToolUseBlock,
        query,
    )

    # The CLI subprocess inherits os.environ. If an API key is set (e.g. in .env),
    # the CLI would silently bill the API instead of the subscription login.
    os.environ.pop("ANTHROPIC_API_KEY", None)

    tools = list(settings["tools"])
    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        model=settings["model"],
        effort=settings["effort"],
        allowed_tools=tools,
        tools=tools,
        disallowed_tools=DISALLOWED_BUILTINS,
        permission_mode="default",  # fail closed: only allow-listed tools run
        setting_sources=[],  # don't inherit user/project CLAUDE.md or settings
        max_turns=max_turns,
        cwd=str(cwd or config.ROOT),
        add_dirs=[str(d) for d in (add_dirs or [])],
        output_format={"type": "json_schema", "schema": output_schema} if output_schema else None,
    )

    logbus.log(run_id, f"{node}: started ({settings['model']}, effort {settings['effort']})")
    text_parts: list[str] = []
    result: ResultMessage | None = None
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    text_parts.append(block.text)
                elif isinstance(block, ToolUseBlock):
                    detail = block.input.get("query") or block.input.get("url") or block.input.get("pattern") or block.input.get("file_path") or ""
                    logbus.log(run_id, f"{node}: {block.name} {str(detail)[:120]}", kind="tool")
        elif isinstance(message, ResultMessage):
            result = message

    if result is None:
        raise AgentError(f"{node}: CLI ended without a result message")
    if result.is_error:
        raise AgentError(f"{node}: {result.subtype} {result.errors or result.result or ''}".strip())

    text = (result.result or "".join(text_parts)).strip()
    cost = f"${result.total_cost_usd:.3f}" if result.total_cost_usd is not None else "n/a"
    logbus.log(run_id, f"{node}: done in {result.duration_ms / 1000:.0f}s, {result.num_turns} turns, {cost}")
    return AgentResult(
        text=text,
        structured_output=result.structured_output,
        cost_usd=result.total_cost_usd,
        duration_ms=result.duration_ms,
        num_turns=result.num_turns,
        session_id=result.session_id,
        usage=result.usage or {},
    )
