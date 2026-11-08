"""Run directories on disk: runs/<id>/{meta.json, brief.md, research.md, ...}.

A run is one pass of the graph: a chapter, a research session, or an arc plan.
The LangGraph checkpoint holds in-flight state; the run dir holds the
human-readable artifacts and, once committed, the ledger that feeds "present".
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from . import config

RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

ARTIFACTS = {
    "brief": "brief.md",
    "research": "research.md",
    "outline": "outline.md",
    "plan": "plan.md",
    "lore": "lore.md",
    "prose": "prose.md",
    "critique": "critique.md",
    "summary": "summary.md",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_dir(run_id: str):
    if not RUN_ID_RE.match(run_id):
        raise ValueError(f"invalid run id {run_id!r}: use lowercase letters, digits, - and _")
    return config.RUNS_DIR / run_id


def exists(run_id: str) -> bool:
    return (run_dir(run_id) / "meta.json").exists()


def read_meta(run_id: str) -> dict:
    return json.loads((run_dir(run_id) / "meta.json").read_text())


def write_meta(run_id: str, meta: dict) -> None:
    d = run_dir(run_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")


def update_meta(run_id: str, **fields) -> dict:
    meta = read_meta(run_id)
    meta.update(fields)
    write_meta(run_id, meta)
    return meta


def list_runs() -> list[dict]:
    if not config.RUNS_DIR.exists():
        return []
    metas = []
    for d in config.RUNS_DIR.iterdir():
        if (d / "meta.json").exists():
            metas.append(json.loads((d / "meta.json").read_text()))
    return sorted(metas, key=lambda m: m.get("created_at", ""))


def next_chapter_order() -> int:
    orders = [m.get("order") or 0 for m in list_runs() if m["type"] == "chapter"]
    return max(orders, default=0) + 1


def create_run(*, run_id: str, run_type: str, title: str, brief: str, pov: str = "",
               researchers: list[str] | None = None, target_event_id: str = "") -> dict:
    if exists(run_id):
        raise FileExistsError(f"run {run_id} already exists")
    meta = {
        "id": run_id,
        "type": run_type,
        "title": title or run_id,
        "pov": pov,
        "researchers": list(researchers or []),
        "target_event_id": target_event_id,
        "characters_present": [pov] if pov else [],
        "order": next_chapter_order() if run_type == "chapter" else None,
        "status": "draft",
        "created_at": now_iso(),
        "committed_at": None,
    }
    write_meta(run_id, meta)
    write_artifact(run_id, "brief", brief)
    return meta


def write_artifact(run_id: str, name: str, text: str) -> None:
    d = run_dir(run_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / ARTIFACTS[name]).write_text(text or "")


def read_artifact(run_id: str, name: str) -> str:
    p = run_dir(run_id) / ARTIFACTS[name]
    return p.read_text() if p.exists() else ""


def read_ledger(run_id: str) -> list[dict]:
    p = run_dir(run_id) / "ledger.json"
    return json.loads(p.read_text()) if p.exists() else []


def write_ledger(run_id: str, entries: list[dict]) -> None:
    (run_dir(run_id) / "ledger.json").write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n")


def committed_runs() -> list[dict]:
    """Committed (not reverted) runs in the order their ledgers apply."""
    return sorted((m for m in list_runs() if m["status"] == "committed"),
                  key=lambda m: m.get("committed_at") or "")


def committed_chapters() -> list[dict]:
    return sorted((m for m in list_runs() if m["type"] == "chapter" and m["status"] == "committed"),
                  key=lambda m: m.get("order") or 0)


def compile_manuscript() -> None:
    parts = []
    for m in committed_chapters():
        prose = read_artifact(m["id"], "prose").strip()
        if prose:
            parts.append(f"<!-- {m['id']} -->\n\n{prose}\n")
    config.MANUSCRIPT_FILE.write_text("\n\n---\n\n".join(parts) + ("\n" if parts else ""))


def timeline() -> list[dict]:
    chapters = [m for m in list_runs() if m["type"] == "chapter" and m["status"] != "reverted"]
    chapters.sort(key=lambda m: m.get("order") or 0)
    return [
        {"run_id": m["id"], "order": m.get("order"), "title": m.get("title"), "pov": m.get("pov"),
         "characters_present": m.get("characters_present") or [], "status": m["status"]}
        for m in chapters
    ]
