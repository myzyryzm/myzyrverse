"""Run metrics: an append-only event log per run, runs/<id>/metrics.json.

Events (each has "kind" and "t"):
  llm_call     one agent call: cost, time, turns, tokens, web searches
  segment      one stretch of graph execution between launch and pause/finish/error
  gate_review  what the author decided when resuming past a human gate
  regenerate   the author pressed Regenerate (Force rewrite at the final gate)
  critic       one Grand Critic verdict

Everything the Metrics view shows is derived from these events by summarize().
Runs from before this file existed are backfilled once from the checkpoint and
the run's artifacts; whatever cannot be recovered stays null.
"""

from __future__ import annotations

import difflib
import json
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from . import runs

FILE = "metrics.json"
TOKEN_KEYS = ("input", "output", "cache_read", "cache_write")
DECISIONS = ("accepted", "maybe", "rejected")
DOC_FIELDS = {"plan_arc": "arc_plan", "lore": "lore_doc"}  # anything else: chapter_outline


# ---------------- storage ----------------

def _path(run_id: str):
    return runs.run_dir(run_id) / FILE


def load(run_id: str) -> dict | None:
    p = _path(run_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return None


def _save(run_id: str, data: dict) -> None:
    p = _path(run_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def init(run_id: str) -> None:
    """A new run has nothing to backfill."""
    if load(run_id) is None:
        _save(run_id, {"backfilled": False, "backfill_checked": True, "events": []})


def record(run_id: str | None, kind: str, **fields: Any) -> None:
    """Append one event. Synchronous on purpose: parallel nodes share one event loop, so writes can't interleave."""
    if not run_id or not runs.exists(run_id):
        return
    data = load(run_id) or {"backfilled": False, "backfill_checked": False, "events": []}
    data["events"].append({"kind": kind, "t": runs.now_iso(), **fields})
    _save(run_id, data)


def record_call(run_id: str | None, node: str, model: str, result) -> None:
    t = result.tokens or {}
    record(run_id, "llm_call", node=node, model=model, session_id=result.session_id,
           cost_usd=result.cost_usd, duration_ms=result.duration_ms, duration_api_ms=result.duration_api_ms,
           num_turns=result.num_turns, web_searches=t.get("web_searches"),
           **{f"{k}_tokens": t.get(k) for k in TOKEN_KEYS})


# ---------------- gate reviews ----------------

def _edit_stats(before: str, after: str) -> dict:
    before, after = before or "", after or ""
    edited = before != after
    return {"edited": edited, "chars_before": len(before), "chars_after": len(after),
            "similarity": round(difflib.SequenceMatcher(None, before, after, autojunk=False).ratio(), 3)
            if edited and before and after else (1.0 if not edited else 0.0)}


def research_counts(proposals: list[dict], cut: int | None = None) -> dict:
    out: dict[str, Any] = {d: 0 for d in DECISIONS}
    out["accepted_with_notes"] = 0
    by_researcher: dict[str, Counter] = defaultdict(Counter)
    by_kind: dict[str, Counter] = defaultdict(Counter)
    for p in proposals:
        d = p.get("decision") or "pending"
        if d == "modified":  # legacy: accepted with changes
            d = "accepted"
            out["accepted_with_notes"] += 1
        elif d == "accepted" and (p.get("note") or "").strip():
            out["accepted_with_notes"] += 1
        if d not in DECISIONS:
            continue
        out[d] += 1
        by_researcher[p.get("researcher") or "unknown"][d] += 1
        if p.get("kind"):
            by_kind[p["kind"]][d] += 1
    out["total"] = sum(out[d] for d in DECISIONS)
    out["cut_by_editor"] = cut
    out["by_researcher"] = {k: dict(v) for k, v in by_researcher.items()}
    out["by_kind"] = {k: dict(v) for k, v in by_kind.items()}
    return out


def ledger_counts(before: list[dict], after: list[dict]) -> dict:
    """Keep/drop of the AI-proposed rows. Rows deleted outright count as dropped."""
    by_kind: dict[str, Counter] = defaultdict(Counter)
    ai_after = [e for e in after if e.get("source", "ai") != "user"]
    for e in ai_after:
        by_kind[e.get("kind") or "other"]["kept" if e.get("accepted", True) else "dropped"] += 1
    if before:
        lost = Counter(e.get("kind") or "other" for e in before if e.get("source", "ai") != "user")
        lost.subtract(Counter(e.get("kind") or "other" for e in ai_after))
        for kind, n in lost.items():
            if n > 0:
                by_kind[kind]["dropped"] += n
    answered = sum(1 for e in after if e.get("kind") == "new_question" and (e.get("answer") or "").strip()
                   and e.get("accepted", True))
    return {
        "kept": sum(c["kept"] for c in by_kind.values()),
        "dropped": sum(c["dropped"] for c in by_kind.values()),
        "added_by_user": sum(1 for e in after if e.get("source") == "user" and e.get("accepted", True)),
        "answered": answered,
        "by_kind": {k: {"kept": v["kept"], "dropped": v["dropped"]} for k, v in by_kind.items()},
    }


def gate_review(gate: str, run_type: str, before: dict, edits: dict) -> dict | None:
    """One gate_review event's fields, from the checkpoint values and the edits sent with Resume."""
    after = {**before, **edits}
    if gate == "human_gate_research":
        proposals = after.get("research_proposals") or []
        if not proposals:
            return None
        return research_counts(proposals, len(after.get("research_proposals_cut") or []))
    if gate == "human_gate_outline":
        field = DOC_FIELDS.get(run_type, "chapter_outline")
        return {"doc": field, **_edit_stats(before.get(field, ""), after.get(field, ""))}
    if gate == "human_gate_final":
        return {"doc": "draft_prose", **_edit_stats(before.get("draft_prose", ""), after.get("draft_prose", ""))}
    if gate == "human_gate_ledger":
        return ledger_counts(before.get("proposed_ledger") or [], after.get("proposed_ledger") or [])
    return None


def record_gate_review(run_id: str, gate: str, run_type: str, before: dict, edits: dict) -> None:
    fields = gate_review(gate, run_type, before, edits)
    if fields is not None:
        record(run_id, "gate_review", gate=gate, **fields)


# ---------------- backfill ----------------

def needs_backfill(run_id: str) -> bool:
    data = load(run_id)
    return data is None or not data.get("backfill_checked")


def backfill(run_id: str, meta: dict, values: dict) -> None:
    """Recover what older runs left behind: checkpoint usage, proposals.json, the final proposed_ledger.

    Idempotent: calls already logged (same session_id) and gates already reviewed are skipped.
    """
    data = load(run_id) or {"backfilled": False, "events": []}
    events = data["events"]
    added: list[dict] = []
    seen = {e.get("session_id") for e in events if e["kind"] == "llm_call" and e.get("session_id")}
    for u in values.get("usage") or []:
        if u.get("session_id") and u["session_id"] in seen:
            continue
        added.append({"kind": "llm_call", "t": None, "node": u.get("node"), "model": u.get("model"),
                      "session_id": u.get("session_id"), "cost_usd": u.get("cost_usd"),
                      "duration_ms": u.get("duration_ms"), "duration_api_ms": None,
                      "num_turns": u.get("num_turns"), "web_searches": None,
                      **{f"{k}_tokens": None for k in TOKEN_KEYS}})
    reviewed = {e.get("gate") for e in events if e["kind"] == "gate_review"}
    if "human_gate_research" not in reviewed:
        proposals = []
        raw = runs.read_artifact(run_id, "proposals")
        if raw.strip():
            try:
                proposals = json.loads(raw)
            except json.JSONDecodeError:
                proposals = []
        if proposals and not any((p.get("decision") or "pending") == "pending" for p in proposals):
            added.append({"kind": "gate_review", "t": None, "gate": "human_gate_research",
                          **research_counts(proposals, len(values.get("research_proposals_cut") or []) or None)})
    if "human_gate_ledger" not in reviewed and meta.get("status") in ("committed", "reverted"):
        ledger = values.get("proposed_ledger") or []
        if ledger:
            added.append({"kind": "gate_review", "t": None, "gate": "human_gate_ledger", **ledger_counts([], ledger)})
    data["events"] = added + events
    data["backfilled"] = bool(data.get("backfilled") or added)
    data["backfill_checked"] = True
    _save(run_id, data)


# ---------------- summaries ----------------

def _ms_between(a: str | None, b: str | None) -> int | None:
    if not a or not b:
        return None
    try:
        return int((datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() * 1000)
    except ValueError:
        return None


def _add(a: float | int | None, b: float | int | None):
    if b is None:
        return a
    return (a or 0) + b


def _call_rollup() -> dict:
    return {"calls": 0, "cost_usd": None, "duration_ms": None, "num_turns": None, "web_searches": None,
            **{k: None for k in TOKEN_KEYS}}


def _add_call(acc: dict, e: dict) -> None:
    acc["calls"] += 1
    for k in ("cost_usd", "duration_ms", "num_turns", "web_searches"):
        acc[k] = _add(acc[k], e.get(k))
    for k in TOKEN_KEYS:
        acc[k] = _add(acc[k], e.get(f"{k}_tokens"))


def _merge(acc: dict, part: dict) -> None:
    acc["calls"] += part["calls"]
    for k, v in part.items():
        if k not in ("calls", "node", "model"):
            acc[k] = _add(acc.get(k), v)


def summarize(run_id: str, meta: dict) -> dict:
    data = load(run_id) or {"backfilled": False, "events": []}
    events = data["events"]

    usage = _call_rollup()
    nodes: dict[tuple[str, str], dict] = {}
    for e in events:
        if e["kind"] != "llm_call":
            continue
        _add_call(usage, e)
        key = (e.get("node") or "?", e.get("model") or "?")
        _add_call(nodes.setdefault(key, {"node": key[0], "model": key[1], **_call_rollup()}), e)

    segments = [e for e in events if e["kind"] == "segment"]
    active = waiting = None
    for i, s in enumerate(segments):
        active = _add(active, s.get("duration_ms"))
        if str(s.get("outcome", "")).startswith("paused") and i + 1 < len(segments):
            waiting = _add(waiting, _ms_between(s.get("ended"), segments[i + 1].get("started")))
    if segments:
        elapsed = _ms_between(segments[0].get("started"), segments[-1].get("ended"))
    else:
        elapsed = _ms_between(meta.get("created_at"), meta.get("committed_at"))

    def last_review(gate: str) -> dict | None:
        found = [e for e in events if e["kind"] == "gate_review" and e.get("gate") == gate]
        return found[-1] if found else None

    def strip(e: dict | None) -> dict | None:
        return {k: v for k, v in e.items() if k not in ("kind", "t", "gate")} if e else None

    regens = Counter(e.get("gate") for e in events if e["kind"] == "regenerate")
    outline_reviews = [e for e in events if e["kind"] == "gate_review" and e.get("gate") == "human_gate_outline"]
    last_outline = outline_reviews[-1] if outline_reviews else None
    doc = None
    if last_outline or regens["human_gate_outline"]:
        doc = {"doc": (last_outline or {}).get("doc") or DOC_FIELDS.get(meta.get("type"), "chapter_outline"),
               "regenerations": regens["human_gate_outline"],
               "approved": last_outline is not None,
               **{k: (last_outline or {}).get(k) for k in ("edited", "similarity", "chars_before", "chars_after")}}

    critics = [{"verdict": e.get("verdict"), "score": e.get("score"), "tone_drift": e.get("tone_drift"),
                "draft": e.get("draft")} for e in events if e["kind"] == "critic"]
    final = last_review("human_gate_final")
    prose = None
    if critics or final or regens["human_gate_final"]:
        scores = [c["score"] for c in critics if c.get("score")]
        prose = {"critic": critics,
                 "passed": sum(c["verdict"] == "PASSED" for c in critics),
                 "failed": sum(c["verdict"] == "FAILED" for c in critics),
                 "avg_score": round(sum(scores) / len(scores), 2) if scores else None,
                 "force_rewrites": regens["human_gate_final"],
                 "approved": final is not None,
                 **{k: (final or {}).get(k) for k in ("edited", "similarity", "chars_before", "chars_after")}}

    return {
        "id": run_id, "title": meta.get("title") or run_id, "type": meta.get("type"), "status": meta.get("status"),
        "created_at": meta.get("created_at"), "committed_at": meta.get("committed_at"),
        "backfilled": bool(data.get("backfilled")),
        "usage": usage,
        "nodes": sorted(nodes.values(), key=lambda n: -(n["cost_usd"] or 0)),
        "time": {"active_ms": active, "waiting_ms": waiting, "elapsed_ms": elapsed},
        "research": strip(last_review("human_gate_research")),
        "research_regenerations": regens["human_gate_research"],
        "doc": doc,
        "prose": prose,
        "ledger": strip(last_review("human_gate_ledger")),
        "ledger_regenerations": regens["human_gate_ledger"],
    }


def _sum_counts(dicts: list[dict], keys) -> dict:
    return {k: sum(d.get(k) or 0 for d in dicts) for k in keys}


def _sum_nested(dicts: list[dict], keys) -> dict:
    out: dict[str, dict] = {}
    for d in dicts:
        for name, counts in (d or {}).items():
            acc = out.setdefault(name, {k: 0 for k in keys})
            for k in keys:
                acc[k] += counts.get(k) or 0
    return out


def summarize_all(summaries: list[dict]) -> dict:
    usage = _call_rollup()
    nodes: dict[str, dict] = {}
    models: dict[str, dict] = {}
    for s in summaries:
        _merge(usage, s["usage"])
        for n in s["nodes"]:
            _merge(nodes.setdefault(n["node"], {"node": n["node"], **_call_rollup()}), n)
            _merge(models.setdefault(n["model"], {"model": n["model"], **_call_rollup()}), n)

    time: dict[str, Any] = {"active_ms": None, "waiting_ms": None}
    for s in summaries:
        for k in time:
            time[k] = _add(time[k], s["time"][k])

    research = [s["research"] for s in summaries if s["research"]]
    ledger = [s["ledger"] for s in summaries if s["ledger"]]
    docs: dict[str, dict] = {}
    for s in summaries:
        d = s["doc"]
        if not d:
            continue
        acc = docs.setdefault(d["doc"], {"doc": d["doc"], "runs": 0, "approved": 0, "edited": 0, "regenerations": 0})
        acc["runs"] += 1
        acc["approved"] += int(bool(d["approved"]))
        acc["edited"] += int(bool(d["edited"]))
        acc["regenerations"] += d["regenerations"]
    prose = [s["prose"] for s in summaries if s["prose"]]
    scores = [c["score"] for p in prose for c in p["critic"] if c.get("score")]

    return {
        "runs": len(summaries),
        "partial_runs": sum(s["backfilled"] for s in summaries),
        "usage": usage,
        "time": time,
        "nodes": sorted(nodes.values(), key=lambda n: -(n["cost_usd"] or 0)),
        "models": sorted(models.values(), key=lambda n: -(n["cost_usd"] or 0)),
        "research": {
            "runs": len(research),
            **_sum_counts(research, (*DECISIONS, "accepted_with_notes", "total", "cut_by_editor")),
            "by_researcher": _sum_nested([r["by_researcher"] for r in research], DECISIONS),
            "by_kind": _sum_nested([r["by_kind"] for r in research], DECISIONS),
            "regenerations": sum(s["research_regenerations"] for s in summaries),
        },
        "docs": sorted(docs.values(), key=lambda d: d["doc"]),
        "prose": {
            "runs": len(prose),
            "critic_rounds": sum(len(p["critic"]) for p in prose),
            "passed": sum(p["passed"] for p in prose),
            "failed": sum(p["failed"] for p in prose),
            "avg_score": round(sum(scores) / len(scores), 2) if scores else None,
            "force_rewrites": sum(p["force_rewrites"] for p in prose),
            "approved": sum(bool(p["approved"]) for p in prose),
            "edited": sum(bool(p["edited"]) for p in prose),
        },
        "ledger": {
            "runs": len(ledger),
            **_sum_counts(ledger, ("kept", "dropped", "added_by_user", "answered")),
            "by_kind": _sum_nested([l["by_kind"] for l in ledger], ("kept", "dropped")),
            "regenerations": sum(s["ledger_regenerations"] for s in summaries),
        },
    }
