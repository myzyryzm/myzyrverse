"""Two-layer lore.

PREHISTORY: free-form markdown files in lore/prehistory/, written only by you.
PRESENT: everything that has changed since the story began. It is never stored
as one file. It is derived by folding the ledgers of committed runs in commit
order (event sourcing, like replaying git commits). Reverting a run just marks
it reverted, and the next fold leaves its entries out, so its lore changes,
answered questions, new questions and event progress all disappear together.

Open questions and planned events work the same way: the JSON files hold what
you created by hand (base items) plus your manual edits (overrides). Runs add
to them through ledger entries. The effective view is base -> ledgers -> overrides,
so your manual edits always win.

TIMELINES: lore/timelines.json orders events per character ("lanes"). Who takes
part in an event is still event.characters; a lane only says in what order that
character lives through their events. The global story order is derived from
all lanes together (a partial order), never stored.
"""

from __future__ import annotations

import json
import re
import uuid
from collections import OrderedDict, defaultdict

from . import config, runs

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]{0,63}$")


def _manual_file():
    return config.LORE_DIR / "present_manual.json"


# ---------- prehistory ----------

def _prehistory_path(name: str):
    name = name.removesuffix(".md")
    if not NAME_RE.match(name):
        raise ValueError(f"invalid prehistory file name {name!r}")
    return config.PREHISTORY_DIR / f"{name}.md"


def list_prehistory() -> list[str]:
    config.PREHISTORY_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(p.stem for p in config.PREHISTORY_DIR.glob("*.md"))


def read_prehistory(name: str) -> str:
    p = _prehistory_path(name)
    return p.read_text() if p.exists() else ""


def write_prehistory(name: str, text: str) -> None:
    p = _prehistory_path(name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def delete_prehistory(name: str) -> None:
    _prehistory_path(name).unlink(missing_ok=True)


def all_prehistory() -> dict[str, str]:
    return {name: read_prehistory(name) for name in list_prehistory()}


# ---------- base + override stores (open questions, events) ----------

def _load_store(path) -> dict:
    if not path.exists():
        return {"items": [], "overrides": {}}
    data = json.loads(path.read_text())
    if isinstance(data, list):  # tolerate a bare list
        data = {"items": data, "overrides": {}}
    data.setdefault("items", [])
    data.setdefault("overrides", {})
    return data


def _save_store(path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _apply_overrides(items: "OrderedDict[str, dict]", overrides: dict) -> list[dict]:
    for item_id, patch in overrides.items():
        if item_id in items:
            if patch.get("deleted"):
                del items[item_id]
            else:
                items[item_id].update({k: v for k, v in patch.items() if k != "deleted"})
    return list(items.values())


def _fold_ledgers(questions: "OrderedDict[str, dict]", events: "OrderedDict[str, dict]",
                  exclude_run: str | None = None) -> None:
    for meta in runs.committed_runs():
        if meta["id"] == exclude_run:
            continue
        for entry in runs.read_ledger(meta["id"]):
            kind = entry.get("kind")
            if kind == "new_question":
                questions[entry["id"]] = {
                    "id": entry["id"], "question": entry.get("detail", ""), "about": entry.get("entity", ""),
                    "status": "open", "answer": "", "answered_by_run": None,
                    "created_by": entry.get("source", "ai"), "source_run": meta["id"],
                }
            elif kind == "answer" and entry.get("ref_id") in questions:
                questions[entry["ref_id"]].update(
                    status="answered", answer=entry.get("detail", ""), answered_by_run=meta["id"])
            elif kind == "event_update" and entry.get("ref_id") in events:
                status = entry.get("change") if entry.get("change") in ("planned", "in_progress", "resolved") else "in_progress"
                ev = events[entry["ref_id"]]
                ev["status"] = status
                ev.setdefault("progress", []).append({"run_id": meta["id"], "detail": entry.get("detail", "")})
            elif kind == "sub_event":
                parent = meta.get("target_event_id") or entry.get("ref_id") or None
                try:
                    order = int(entry.get("change") or 0)
                except ValueError:
                    order = 0
                events[entry["id"]] = {
                    "id": entry["id"], "title": entry.get("entity", ""), "description": entry.get("detail", ""),
                    "scope": "chapter", "parent_id": parent, "characters": entry.get("characters") or [],
                    "category": "personal" if entry.get("characters") else "world",
                    "target_run": "", "order": order, "status": "planned",
                    "created_by": entry.get("source", "ai"), "source_run": meta["id"],
                }


def _effective(exclude_run: str | None = None) -> tuple[list[dict], list[dict]]:
    qstore, estore = _load_store(config.OPEN_QUESTIONS_FILE), _load_store(config.EVENTS_FILE)
    questions = OrderedDict((q["id"], {**q}) for q in qstore["items"])
    events = OrderedDict((e["id"], {**e}) for e in estore["items"])
    _fold_ledgers(questions, events, exclude_run)
    evs = _apply_overrides(events, estore["overrides"])
    for e in evs:
        e.setdefault("category", "world")
        e["characters"] = list(e.get("characters") or [])
    return _apply_overrides(questions, qstore["overrides"]), evs


def open_questions(exclude_run: str | None = None) -> list[dict]:
    return _effective(exclude_run)[0]


def events(exclude_run: str | None = None) -> list[dict]:
    return _effective(exclude_run)[1]


def create_question(question: str, about: str = "") -> dict:
    store = _load_store(config.OPEN_QUESTIONS_FILE)
    item = {"id": _new_id("q"), "question": question, "about": about, "status": "open", "answer": "",
            "answered_by_run": None, "created_by": "user", "source_run": None, "created_at": runs.now_iso()}
    store["items"].append(item)
    _save_store(config.OPEN_QUESTIONS_FILE, store)
    return item


def create_event(title: str, description: str = "", scope: str = "arc", parent_id: str | None = None,
                 characters: list[str] | None = None, target_run: str = "", category: str = "world") -> dict:
    store = _load_store(config.EVENTS_FILE)
    item = {"id": _new_id("ev"), "title": title, "description": description, "scope": scope,
            "category": category, "parent_id": parent_id, "characters": characters or [], "target_run": target_run,
            "order": 0, "status": "planned", "created_by": "user", "source_run": None,
            "created_at": runs.now_iso()}
    store["items"].append(item)
    _save_store(config.EVENTS_FILE, store)
    return item


def _patch(path, item_id: str, patch: dict) -> None:
    """User edits go to overrides (applied after ledgers, so they always win).
    Deleting a base item removes it outright; deleting a run-created item hides it."""
    _patch_many(path, {item_id: patch})


def _patch_many(path, patches: dict[str, dict]) -> None:
    store = _load_store(path)
    for item_id, patch in patches.items():
        if patch.get("deleted") and any(i["id"] == item_id for i in store["items"]):
            store["items"] = [i for i in store["items"] if i["id"] != item_id]
            store["overrides"].pop(item_id, None)
            if path == config.EVENTS_FILE:
                _drop_from_lanes(item_id)
        else:
            store["overrides"].setdefault(item_id, {}).update(patch)
    _save_store(path, store)


def update_question(item_id: str, patch: dict) -> None:
    if patch.get("answer") and "status" not in patch:
        patch = {**patch, "status": "answered", "answered_by_run": None}
    _patch(config.OPEN_QUESTIONS_FILE, item_id, patch)


def update_event(item_id: str, patch: dict) -> None:
    _patch(config.EVENTS_FILE, item_id, patch)


def delete_question(item_id: str) -> None:
    _patch(config.OPEN_QUESTIONS_FILE, item_id, {"deleted": True})


def delete_event(item_id: str) -> None:
    _patch(config.EVENTS_FILE, item_id, {"deleted": True})


# ---------- character timelines (lanes) and derived story order ----------

WORLD = "World"


def _load_timelines() -> dict:
    p = config.TIMELINES_FILE
    data = json.loads(p.read_text()) if p.exists() else {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("lanes", {})
    return data


def _save_timelines(data: dict) -> None:
    _save_store(config.TIMELINES_FILE, data)


def _drop_from_lanes(event_id: str) -> None:
    data = _load_timelines()
    if any(event_id in ids for ids in data["lanes"].values()):
        data["lanes"] = {k: [i for i in ids if i != event_id] for k, ids in data["lanes"].items()}
        _save_timelines(data)


def _lane_name(name: str) -> str:
    name = (name or "").strip()
    if not NAME_RE.match(name):
        raise ValueError(f"invalid lane name {name!r}")
    return name


def _dedupe(ids) -> list[str]:
    return list(OrderedDict.fromkeys(ids))


def characters(evs: list[dict] | None = None) -> list[str]:
    """Everyone the universe knows about: event participants, run POVs and people present, named lanes."""
    evs = events() if evs is None else evs
    names: set[str] = set()
    for e in evs:
        names.update(e.get("characters") or [])
    for m in runs.list_runs():
        if m.get("pov"):
            names.add(m["pov"])
        names.update(m.get("characters_present") or [])
    names.update(_load_timelines()["lanes"])
    names.discard(WORLD)
    return sorted(n.strip() for n in names if n and n.strip())


def _in_lane(name: str, e: dict) -> bool:
    if name == WORLD:
        return e.get("category", "world") == "world"
    return name in (e.get("characters") or [])


def effective_lanes(evs: list[dict] | None = None) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """(placed, unplaced) per lane.

    placed: the stored order, restricted to events that still belong on the lane.
    unplaced: events that belong on the lane (the character takes part, or it is a
    world event) but that the author has not put in order yet. Only placed events
    create story order.

    The stored list is never pruned on read, so an event that disappears with a
    reverted run comes back at the same place when the run is restored.
    """
    evs = events() if evs is None else evs
    by_id = {e["id"]: e for e in evs}
    raw = _load_timelines()["lanes"]
    placed: dict[str, list[str]] = {}
    unplaced: dict[str, list[str]] = {}
    for name in [WORLD, *characters(evs)]:
        stored = [i for i in _dedupe(raw.get(name, [])) if i in by_id and _in_lane(name, by_id[i])]
        on = set(stored)
        rest = sorted((e for e in evs if e["id"] not in on and _in_lane(name, e)),
                      key=lambda e: (e.get("order") or 0, e.get("created_at") or ""))
        placed[name] = stored
        unplaced[name] = [e["id"] for e in rest]
    return placed, unplaced


def story_order(lanes: dict[str, list[str]]) -> dict:
    """The partial order implied by every lane, as levels (Kahn's algorithm, one level at a time).

    Events in the same level are unordered relative to each other. If lanes
    contradict each other, the events that could not be placed (the cycle and
    everything after it) are returned in "cycle" instead of raising.
    """
    first_seen: dict[str, int] = {}
    succ: dict[str, set[str]] = defaultdict(set)
    indeg: dict[str, int] = defaultdict(int)
    for ids in lanes.values():
        ids = _dedupe(ids)
        for i in ids:
            first_seen.setdefault(i, len(first_seen))
        for a, b in zip(ids, ids[1:]):
            if b not in succ[a]:
                succ[a].add(b)
                indeg[b] += 1
    ready = sorted((n for n in first_seen if indeg[n] == 0), key=first_seen.get)
    levels: list[list[str]] = []
    while ready:
        levels.append(ready)
        nxt = []
        for n in ready:
            for m in succ[n]:
                indeg[m] -= 1
                if indeg[m] == 0:
                    nxt.append(m)
        ready = sorted(nxt, key=first_seen.get)
    placed = {n for lvl in levels for n in lvl}
    stuck = sorted((n for n in first_seen if n not in placed), key=first_seen.get)
    return {"levels": levels, "cycle": stuck or None}


def timelines_view(exclude_run: str | None = None, evs: list[dict] | None = None) -> dict:
    evs = events(exclude_run) if evs is None else evs
    lanes, unplaced = effective_lanes(evs)
    return {"characters": characters(evs), "lanes": lanes, "unplaced": unplaced, "story_order": story_order(lanes)}


def set_lane(name: str, ids: list[str]) -> dict:
    """Replace a lane's placed order. On a character lane this also sets who takes part:
    events placed on the lane gain the character, events taken off the placed lane lose them.
    Events the character takes part in but that were never placed are left alone."""
    name = _lane_name(name)
    all_evs = events()
    evs = {e["id"]: e for e in all_evs}
    ids = _dedupe(ids)
    unknown = [i for i in ids if i not in evs]
    if unknown:
        raise ValueError(f"unknown event ids {unknown}")
    if name != WORLD:
        before = set(effective_lanes(all_evs)[0].get(name, []))
        after = set(ids)
        patches = {}
        for i in after:
            if name not in evs[i]["characters"]:
                patches[i] = {"characters": [*evs[i]["characters"], name]}
        for i in before - after:
            patches[i] = {"characters": [c for c in evs[i]["characters"] if c != name]}
        if patches:
            _patch_many(config.EVENTS_FILE, patches)
    store = _load_timelines()
    store["lanes"][name] = ids
    _save_timelines(store)
    return timelines_view()


# ---------- present (lore ledger) ----------

def _manual_present() -> list[dict]:
    return json.loads(_manual_file().read_text()) if _manual_file().exists() else []


def present_entries(exclude_run: str | None = None) -> list[dict]:
    """All accepted 'lore' entries from committed runs, in commit order, plus run-less manual notes."""
    out = []
    for meta in runs.committed_runs():
        if meta["id"] == exclude_run:
            continue
        for entry in runs.read_ledger(meta["id"]):
            if entry.get("kind") == "lore":
                out.append({**entry, "run_id": meta["id"], "run_title": meta.get("title")})
    out.extend({**e, "run_id": None, "run_title": "manual"} for e in _manual_present())
    return out


def materialize_present(exclude_run: str | None = None) -> str:
    grouped: "OrderedDict[str, list[dict]]" = OrderedDict()
    for e in present_entries(exclude_run):
        grouped.setdefault(e.get("entity") or "General", []).append(e)
    if not grouped:
        return "(nothing has changed yet)"
    lines = []
    for entity, entries in grouped.items():
        lines.append(f"### {entity}")
        for e in entries:
            tag = f"{e['run_id'] or 'manual'} · {e.get('source', 'ai')}"
            change = f"{e['change']}: " if e.get("change") else ""
            lines.append(f"- [{tag}] {change}{e.get('detail', '')}")
        lines.append("")
    return "\n".join(lines).strip()


def add_manual_entry(entry: dict, run_id: str | None = None) -> dict:
    clean = {
        "kind": entry.get("kind", "lore"),
        "entity": entry.get("entity", ""),
        "change": entry.get("change", ""),
        "detail": entry.get("detail", ""),
        "ref_id": entry.get("ref_id", ""),
        "source": "user",
        "created_at": runs.now_iso(),
    }
    if run_id:
        ledger = runs.read_ledger(run_id)
        clean["id"] = f"{run_id}-u{len(ledger) + 1}"
        ledger.append(clean)
        runs.write_ledger(run_id, ledger)
    else:
        manual = _manual_present()
        clean["id"] = _new_id("m")
        manual.append(clean)
        _manual_file().write_text(json.dumps(manual, indent=2, ensure_ascii=False) + "\n")
    return clean


# ---------- revert / restore ----------

def _later_conflicts(run_id: str) -> list[str]:
    target = runs.read_meta(run_id)
    entities = {e.get("entity") for e in runs.read_ledger(run_id) if e.get("entity")}
    warnings = []
    for meta in runs.committed_runs():
        if meta["id"] == run_id or (meta.get("committed_at") or "") <= (target.get("committed_at") or ""):
            continue
        for e in runs.read_ledger(meta["id"]):
            if e.get("entity") in entities:
                warnings.append(f"{meta['id']} also changed {e['entity']}: {e.get('change', '')} {e.get('detail', '')}".strip())
    return warnings


def revert_run(run_id: str) -> list[str]:
    meta = runs.read_meta(run_id)
    if meta["status"] != "committed":
        raise ValueError(f"run {run_id} is {meta['status']}, only committed runs can be reverted")
    warnings = _later_conflicts(run_id)
    runs.update_meta(run_id, status="reverted")
    runs.compile_manuscript()
    return warnings


def restore_run(run_id: str) -> None:
    meta = runs.read_meta(run_id)
    if meta["status"] != "reverted":
        raise ValueError(f"run {run_id} is {meta['status']}, not reverted")
    runs.update_meta(run_id, status="committed")
    runs.compile_manuscript()


# ---------- canon bundle handed to every node ----------

def build_canon(run_id: str) -> dict:
    chapters = [m for m in runs.committed_chapters() if m["id"] != run_id]
    questions, evs = _effective(exclude_run=run_id)
    return {
        "prehistory": all_prehistory(),
        "present_lore": materialize_present(exclude_run=run_id),
        "open_questions": questions,
        "events": evs,
        "timelines": timelines_view(run_id, evs),
        "previous_summaries": [
            {"run_id": m["id"], "order": m.get("order"), "title": m.get("title"), "pov": m.get("pov"),
             "summary": runs.read_artifact(m["id"], "summary")}
            for m in chapters
        ],
    }
