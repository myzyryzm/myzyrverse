"""Paths, per-node model settings, and runtime flags.

Every LLM node looks up its settings here, so swapping a model or effort level
is a one-line change. FAKE_LLM=1 makes runner.run_agent return canned output so
the graph and UI can be exercised without spending subscription usage.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# Where lore, runs, checkpoints and the manuscript live. Point MYZYRVERSE_WORKSPACE at
# another folder to experiment (e.g. with FAKE_LLM) without touching the real universe.
WORKSPACE = Path(os.environ.get("MYZYRVERSE_WORKSPACE") or ROOT).expanduser().resolve()

LORE_DIR = WORKSPACE / "lore"
PREHISTORY_DIR = LORE_DIR / "prehistory"
SOURCES_DIR = LORE_DIR / "sources"
OPEN_QUESTIONS_FILE = LORE_DIR / "open_questions.json"
EVENTS_FILE = LORE_DIR / "events.json"
TIMELINES_FILE = LORE_DIR / "timelines.json"
RUNS_DIR = WORKSPACE / "runs"
MANUSCRIPT_FILE = WORKSPACE / "manuscript.md"
DATA_DIR = WORKSPACE / "data"
CHECKPOINT_DB = DATA_DIR / "checkpoints.sqlite"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
FRONTEND_DIST = ROOT / "frontend" / "dist"

FAKE_LLM = os.environ.get("FAKE_LLM", "").lower() in ("1", "true", "yes")

MAX_REVISIONS = int(os.environ.get("MAX_REVISIONS", "3"))

RESEARCHERS = ("antiquarian", "historian", "mythographer", "psychologist")

RESEARCH_TOOLS = ["WebSearch", "WebFetch", "Read", "Grep", "Glob"]

OPUS = "claude-opus-5-5"
FABLE = "claude-fable-5-1"

# model / effort / tools per node. Override any model with e.g. MODEL_WRITER=claude-opus-5-5
NODE_SETTINGS: dict[str, dict] = {
    "antiquarian": {"model": OPUS, "effort": "high", "tools": RESEARCH_TOOLS},
    "historian": {"model": OPUS, "effort": "high", "tools": RESEARCH_TOOLS},
    "mythographer": {"model": OPUS, "effort": "high", "tools": RESEARCH_TOOLS},
    "psychologist": {"model": OPUS, "effort": "high", "tools": ["Read", "Grep", "Glob"]},
    "weaver": {"model": OPUS, "effort": "high", "tools": []},
    "loremaster": {"model": OPUS, "effort": "high", "tools": []},
    "writer": {"model": FABLE, "effort": "high", "tools": []},
    "grand_critic": {"model": OPUS, "effort": "high", "tools": []},
    "archivist": {"model": OPUS, "effort": "high", "tools": []},
}
for _name, _s in NODE_SETTINGS.items():
    _s["model"] = os.environ.get(f"MODEL_{_name.upper()}", _s["model"])
    _s["effort"] = os.environ.get(f"EFFORT_{_name.upper()}", _s["effort"])
