import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import type { EventCategory, StoryEvent, TimelinesView } from "../types";
import { errMsg } from "../util";
import { CharChip } from "./Timeline";

const WORLD = "World";
const ORDER = "__order__";
const ADD = "__add__";

const CATEGORY_LABELS: Record<EventCategory, string> = { world: "World events", personal: "Personal events" };

interface Props {
  onClose: () => void;
  bump: () => void;
  notify: (m: string) => void;
}

interface EventDraft {
  title: string;
  description: string;
  scope: StoryEvent["scope"];
}

const EMPTY_DRAFT: EventDraft = { title: "", description: "", scope: "chapter" };

/**
 * A shared bank of events and one timeline (lane) per character.
 *
 * Putting an event on a character's lane means that character takes part in it;
 * the lane order is the order they live through their events. The World lane
 * orders world events. The story order is derived from all lanes together.
 */
export default function ArcPlanner({ onClose, bump, notify }: Props) {
  const [events, setEvents] = useState<StoryEvent[]>([]);
  const [view, setView] = useState<TimelinesView | null>(null);
  const [sel, setSel] = useState<string>(WORLD);
  const [filter, setFilter] = useState("");
  const [popover, setPopover] = useState<number | null>(null);
  const [addingChar, setAddingChar] = useState(false);
  const [newChar, setNewChar] = useState("");
  const [overSlot, setOverSlot] = useState<number | null>(null);
  const dragId = useRef<string | null>(null);

  // Loads on mount and after this modal's own changes only. It deliberately ignores the
  // app-wide version counter: we bump() it after each change, so watching it would refetch twice.
  const load = useCallback(async () => {
    const [e, t] = await Promise.all([api.events(), api.timelines()]);
    setEvents(e);
    setView(t);
  }, []);

  useEffect(() => {
    load().catch((e) => notify(errMsg(e)));
  }, [load, notify]);

  const mutate = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      await load();
      bump();
    } catch (e) {
      notify(errMsg(e));
    }
  };

  // Esc closes the innermost thing first: the slot popover, then the add-character input, then the modal.
  const onEsc = useRef<() => void>(() => {});
  onEsc.current = () => {
    if (popover !== null) setPopover(null);
    else if (addingChar) setAddingChar(false);
    else onClose();
  };
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onEsc.current();
      }
    };
    window.addEventListener("keydown", h);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", h);
      document.body.style.overflow = prev;
    };
  }, []);

  const byId = useMemo(() => new Map(events.map((e) => [e.id, e])), [events]);
  const lanes = useMemo(() => [WORLD, ...(view?.characters ?? [])], [view]);
  const isLane = sel !== ORDER;
  const laneIds = useMemo(() => (isLane ? view?.lanes[sel] ?? [] : []), [view, sel, isLane]);
  const unplacedIds = useMemo(() => (isLane ? view?.unplaced[sel] ?? [] : []), [view, sel, isLane]);
  const onLane = useMemo(() => new Set(laneIds), [laneIds]);

  useEffect(() => {
    if (view && sel !== ORDER && !lanes.includes(sel)) setSel(WORLD);
  }, [view, sel, lanes]);

  const pickLane = (v: string) => {
    setPopover(null);
    if (v === ADD) {
      setAddingChar(true);
      return;
    }
    setAddingChar(false);
    setSel(v);
  };

  const addCharacter = async () => {
    const name = newChar.trim();
    if (!name) return;
    setNewChar("");
    setAddingChar(false);
    if (!lanes.includes(name)) await mutate(() => api.setLane(name, [])); // an empty lane names the character
    setSel(name);
  };

  /** Put an event at a slot of the selected lane (or move it there if it is already on it). */
  const insertAt = (id: string, slot: number) => {
    const ev = byId.get(id);
    if (!ev || !isLane) return;
    const from = laneIds.indexOf(id);
    const ids = laneIds.filter((x) => x !== id);
    const at = from !== -1 && from < slot ? slot - 1 : slot;
    ids.splice(at, 0, id);
    setPopover(null);
    if (from === at) return;
    return mutate(async () => {
      // The World lane holds world events, so placing a personal event there makes it a world event.
      if (sel === WORLD && ev.category !== "world") await api.updateEvent(id, { category: "world" });
      await api.setLane(sel, ids);
    });
  };

  const removeFromLane = (id: string) =>
    mutate(async () => {
      if (sel === WORLD) await api.updateEvent(id, { category: "personal" });
      await api.setLane(sel, laneIds.filter((x) => x !== id));
    });

  /** Take an event that was never placed off this lane: the character stops taking part (World: it becomes personal). */
  const dropUnplaced = (id: string) => {
    const ev = byId.get(id);
    if (!ev) return;
    return mutate(() => sel === WORLD
      ? api.updateEvent(id, { category: "personal" })
      : api.updateEvent(id, { characters: ev.characters.filter((c) => c !== sel) }));
  };

  const createAndInsert = (draft: EventDraft, category: EventCategory, slot: number) =>
    mutate(async () => {
      const ev = await api.addEvent({ ...draft, category, characters: sel === WORLD ? [] : [sel] });
      const ids = [...laneIds];
      ids.splice(slot, 0, ev.id);
      await api.setLane(sel, ids);
      setPopover(null);
    });

  const createInBank = (draft: EventDraft, category: EventCategory) =>
    mutate(() => api.addEvent({ ...draft, category, characters: [] }));

  const toggleCategory = (ev: StoryEvent) =>
    mutate(() => api.updateEvent(ev.id, { category: ev.category === "world" ? "personal" : "world" }));

  const dragStart = (id: string) => (e: React.DragEvent) => {
    e.dataTransfer.setData("text/plain", id); // required for Firefox/Safari to start the drag
    e.dataTransfer.effectAllowed = "move";
    dragId.current = id;
  };
  const dragEnd = () => {
    dragId.current = null;
    setOverSlot(null);
  };

  const q = filter.trim().toLowerCase();
  const matches = (e: StoryEvent) =>
    !q || e.title.toLowerCase().includes(q) || e.description.toLowerCase().includes(q)
    || e.characters.some((c) => c.toLowerCase().includes(q));

  const parentTitle = (e: StoryEvent) => (e.parent_id ? byId.get(e.parent_id)?.title : undefined);

  const slot = (i: number) => (
    <Fragment key={`slot-${i}`}>
      <button
        type="button"
        className={`lane-slot${overSlot === i ? " over" : ""}${popover === i ? " open" : ""}`}
        title="Drop an event here, or click to add one"
        onClick={() => setPopover(popover === i ? null : i)}
        onDragOver={(e) => {
          if (!dragId.current) return;
          e.preventDefault(); // without this the drop never fires
          e.dataTransfer.dropEffect = "move";
          if (overSlot !== i) setOverSlot(i);
        }}
        onDragLeave={() => setOverSlot((o) => (o === i ? null : o))}
        onDrop={(e) => {
          e.preventDefault();
          const id = e.dataTransfer.getData("text/plain") || dragId.current;
          dragEnd();
          if (id) insertAt(id, i);
        }}
      >
        <span>+</span>
      </button>
      {popover === i && (
        <SlotPopover
          lane={sel}
          candidates={events.filter((e) => !onLane.has(e.id))}
          onPick={(id) => insertAt(id, i)}
          onCreate={(d, c) => createAndInsert(d, c, i)}
          onCancel={() => setPopover(null)}
        />
      )}
    </Fragment>
  );

  return (
    <div className="modal-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal" role="dialog" aria-modal="true" aria-label="Arc planner">
        <div className="modal-head">
          <h2>Arc planner</h2>
          <span className="hint">
            Drag events from the bank onto a character's timeline. Being on a timeline means taking part.
          </span>
          <button className="ghost" onClick={onClose} aria-label="Close">✕</button>
        </div>

        <div className="planner">
          <section className="planner-pane bank">
            <input placeholder="Filter events…" value={filter} onChange={(e) => setFilter(e.target.value)} />
            {(["world", "personal"] as EventCategory[]).map((cat) => (
              <BankSection key={cat} category={cat} onCreate={(d) => createInBank(d, cat)}>
                {events.filter((e) => e.category === cat && matches(e)).map((e) => (
                  <div key={e.id} className={`card bank-card${isLane && onLane.has(e.id) ? " dim" : ""}`}
                       draggable onDragStart={dragStart(e.id)} onDragEnd={dragEnd} title={e.description}>
                    <div className="card-head">
                      <span className="tag">{e.scope}</span>
                      {e.status !== "planned" && <span className="tag">{e.status.replace("_", " ")}</span>}
                      <span className="row tight">
                        {isLane && !onLane.has(e.id) && (
                          <button className="ghost small" draggable={false} title={`Add to the end of ${sel}`}
                                  onClick={() => insertAt(e.id, laneIds.length)}>→</button>
                        )}
                        <button className="ghost small" draggable={false}
                                title={`Make this a ${cat === "world" ? "personal" : "world"} event`}
                                onClick={() => toggleCategory(e)}>
                          {cat === "world" ? "→ personal" : "→ world"}
                        </button>
                      </span>
                    </div>
                    <div className="ev-title">{e.title}</div>
                    {parentTitle(e) && <div className="caption">part of: {parentTitle(e)}</div>}
                    {!!e.characters.length && (
                      <div className="chips">{e.characters.map((c) => <CharChip key={c} name={c} />)}</div>
                    )}
                  </div>
                ))}
              </BankSection>
            ))}
          </section>

          <section className="planner-pane lane-pane">
            <div className="row">
              <select value={addingChar ? ADD : sel} onChange={(e) => pickLane(e.target.value)}>
                <optgroup label="Timelines">
                  {lanes.map((l) => <option key={l} value={l}>{l === WORLD ? "World (world events)" : l}</option>)}
                </optgroup>
                <option value={ADD}>+ add character…</option>
                <option value={ORDER}>Story order (derived)</option>
              </select>
              {addingChar && (
                <>
                  <input autoFocus placeholder="character name" value={newChar}
                         onChange={(e) => setNewChar(e.target.value)}
                         onKeyDown={(e) => e.key === "Enter" && addCharacter()} />
                  <button className="primary" disabled={!newChar.trim()} onClick={addCharacter}>Add</button>
                </>
              )}
            </div>

            {!view && <p className="muted">Loading…</p>}

            {view && isLane && (
              <div className="lane-chain">
                <div className="lane-end">Start{sel !== WORLD && <> · <CharChip name={sel} pov /></>}</div>
                {laneIds.map((id, i) => {
                  const e = byId.get(id);
                  if (!e) return null;
                  const others = e.characters.filter((c) => c !== sel);
                  return (
                    <Fragment key={id}>
                      {slot(i)}
                      <div className={`card lane-node${e.scope === "arc" ? " arc" : ""}`}
                           draggable onDragStart={dragStart(id)} onDragEnd={dragEnd}>
                        <div className="card-head">
                          <span className="tag">{e.scope}</span>
                          <span className={`tag ${e.category}`}>{e.category}</span>
                          <button className="ghost small danger" draggable={false}
                                  title={sel === WORLD ? "Remove from the world timeline (makes it a personal event)"
                                    : `Remove ${sel} from this event`}
                                  onClick={(ev) => { ev.stopPropagation(); removeFromLane(id); }}>×</button>
                        </div>
                        <div className="ev-title">{e.title}</div>
                        {parentTitle(e) && <div className="caption">part of: {parentTitle(e)}</div>}
                        {e.description && <div className="ev-desc clamp">{e.description}</div>}
                        {!!others.length && (
                          <div className="chips">
                            <span className="caption">with</span>
                            {others.map((c) => <CharChip key={c} name={c} />)}
                          </div>
                        )}
                      </div>
                    </Fragment>
                  );
                })}
                {slot(laneIds.length)}
                <div className="lane-end">End</div>
                {!!unplacedIds.length && (
                  <div className="unplaced stack tight">
                    <h4>Not placed yet</h4>
                    <p className="hint">
                      {sel === WORLD ? "World events" : `Events ${sel} takes part in`} that aren't on the timeline
                      yet. Drag one onto a + to put it in order. Until then it doesn't affect story order.
                    </p>
                    {unplacedIds.map((id) => {
                      const e = byId.get(id);
                      if (!e) return null;
                      return (
                        <div key={id} className="card unplaced-card" draggable onDragStart={dragStart(id)}
                             onDragEnd={dragEnd} title={e.description}>
                          <div className="card-head">
                            <span className="tag">{e.scope}</span>
                            <span className="ev-title small">{e.title}</span>
                            <span className="row tight">
                              <button className="ghost small" draggable={false} title="Add to the end of the timeline"
                                      onClick={() => insertAt(id, laneIds.length)}>↑ place at end</button>
                              <button className="ghost small danger" draggable={false}
                                      title={sel === WORLD ? "Make this a personal event" : `${sel} doesn't take part`}
                                      onClick={() => dropUnplaced(id)}>×</button>
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {view && sel === ORDER && <StoryOrderView view={view} byId={byId} />}
          </section>
        </div>
      </div>
    </div>
  );
}

function BankSection({ category, onCreate, children }: {
  category: EventCategory; onCreate: (d: EventDraft) => Promise<void>; children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<EventDraft>(EMPTY_DRAFT);
  const submit = async () => {
    if (!draft.title.trim()) return;
    await onCreate(draft);
    setDraft(EMPTY_DRAFT);
    setOpen(false);
  };
  return (
    <div className="bank-section stack">
      <div className="row spread">
        <h4>{CATEGORY_LABELS[category]}</h4>
        <button className="ghost small" onClick={() => setOpen(!open)}>{open ? "cancel" : "+ New event"}</button>
      </div>
      {open && <EventForm draft={draft} setDraft={setDraft} onSubmit={submit} submitLabel="Add to bank" />}
      {children}
    </div>
  );
}

function EventForm({ draft, setDraft, onSubmit, submitLabel, extra }: {
  draft: EventDraft; setDraft: (d: EventDraft) => void; onSubmit: () => void; submitLabel: string;
  extra?: React.ReactNode;
}) {
  return (
    <div className="stack tight">
      <input autoFocus placeholder="title, e.g. Jon arrives at Knossos" value={draft.title}
             onChange={(e) => setDraft({ ...draft, title: e.target.value })}
             onKeyDown={(e) => e.key === "Enter" && onSubmit()} />
      <textarea placeholder="what happens (optional)" value={draft.description}
                onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
      <div className="row">
        <select value={draft.scope} onChange={(e) => setDraft({ ...draft, scope: e.target.value as EventDraft["scope"] })}>
          <option value="chapter">single event</option>
          <option value="arc">arc (multi-chapter)</option>
        </select>
        {extra}
        <button className="primary" disabled={!draft.title.trim()} onClick={onSubmit}>{submitLabel}</button>
      </div>
    </div>
  );
}

function SlotPopover({ lane, candidates, onPick, onCreate, onCancel }: {
  lane: string;
  candidates: StoryEvent[];
  onPick: (id: string) => void;
  onCreate: (d: EventDraft, c: EventCategory) => void;
  onCancel: () => void;
}) {
  const [mode, setMode] = useState<"bank" | "new">(candidates.length ? "bank" : "new");
  const [pick, setPick] = useState("");
  const [draft, setDraft] = useState<EventDraft>(EMPTY_DRAFT);
  const [category, setCategory] = useState<EventCategory>(lane === WORLD ? "world" : "personal");
  const grouped = (["world", "personal"] as EventCategory[])
    .map((c) => [c, candidates.filter((e) => e.category === c)] as const)
    .filter(([, list]) => list.length);

  return (
    <div className="slot-popover stack">
      <div className="seg">
        <button className={mode === "bank" ? "active" : ""} disabled={!candidates.length}
                onClick={() => setMode("bank")}>Add from bank</button>
        <button className={mode === "new" ? "active" : ""} onClick={() => setMode("new")}>New event</button>
      </div>
      {mode === "bank" ? (
        <div className="row">
          <select autoFocus value={pick} onChange={(e) => setPick(e.target.value)}>
            <option value="">Choose an event…</option>
            {grouped.map(([c, list]) => (
              <optgroup key={c} label={CATEGORY_LABELS[c]}>
                {list.map((e) => <option key={e.id} value={e.id}>{e.title}</option>)}
              </optgroup>
            ))}
          </select>
          <button className="primary" disabled={!pick} onClick={() => onPick(pick)}>Add here</button>
        </div>
      ) : (
        <EventForm draft={draft} setDraft={setDraft} submitLabel="Create here"
                   onSubmit={() => draft.title.trim() && onCreate(draft, category)}
                   extra={lane === WORLD ? undefined : (
                     <select value={category} onChange={(e) => setCategory(e.target.value as EventCategory)}>
                       <option value="personal">personal</option>
                       <option value="world">world</option>
                     </select>
                   )} />
      )}
      <button className="ghost small" onClick={onCancel}>cancel</button>
    </div>
  );
}

function StoryOrderView({ view, byId }: { view: TimelinesView; byId: Map<string, StoryEvent> }) {
  const { levels, cycle } = view.story_order;
  const card = (id: string) => {
    const e = byId.get(id);
    if (!e) return null;
    return (
      <div key={id} className={`card order-card${e.scope === "arc" ? " arc" : ""}`} title={e.description}>
        <div className="ev-title">{e.title}</div>
        <div className="chips">
          <span className={`tag ${e.category}`}>{e.category}</span>
          {e.characters.map((c) => <CharChip key={c} name={c} />)}
        </div>
      </div>
    );
  };
  return (
    <div className="stack">
      <p className="hint">
        Built from every timeline together. An event comes after everything that comes before it on any
        character's timeline. Events in the same row are not ordered relative to each other yet.
      </p>
      {cycle && (
        <div className="error-box">
          The timelines contradict each other (one puts A before B, another B before A). These could not be
          ordered: {cycle.map((id) => byId.get(id)?.title ?? id).join(", ")}
        </div>
      )}
      {!levels.length && !cycle && <p className="muted">Nothing placed yet.</p>}
      {levels.map((lvl, i) => (
        <div key={i} className="order-level">
          <span className="lvl">{i + 1}</span>
          <div className="order-cards">{lvl.map(card)}</div>
        </div>
      ))}
    </div>
  );
}
