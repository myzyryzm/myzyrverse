import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { LedgerEntry, OpenQuestion, RunMeta, StoryEvent } from "../types";
import { errMsg } from "../util";

type Tab = "prehistory" | "present" | "questions" | "events";

interface Props {
  version: number;
  runs: RunMeta[];
  bump: () => void;
  notify: (m: string) => void;
  onPlanArc: (ev: StoryEvent) => void;
  onOpenPlanner: () => void;
}

export default function Canon(props: Props) {
  const [tab, setTab] = useState<Tab>("prehistory");
  return (
    <>
      <div className="col-title">The Canon</div>
      <nav className="tabs">
        {(["prehistory", "present", "questions", "events"] as Tab[]).map((t) => (
          <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>
            {{ prehistory: "Prehistory", present: "Present", questions: "Open questions", events: "Events" }[t]}
          </button>
        ))}
      </nav>
      <div className="col-body">
        {tab === "prehistory" && <Prehistory {...props} />}
        {tab === "present" && <Present {...props} />}
        {tab === "questions" && <Questions {...props} />}
        {tab === "events" && <Events {...props} />}
      </div>
    </>
  );
}

function Prehistory({ version, notify }: Props) {
  const [files, setFiles] = useState<Record<string, string>>({});
  const [current, setCurrent] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [newName, setNewName] = useState("");

  useEffect(() => {
    api.prehistory().then((f) => {
      setFiles(f);
      setCurrent((c) => (c && c in f ? c : Object.keys(f)[0] ?? null));
    }).catch((e) => notify(errMsg(e)));
  }, [version, notify]);

  useEffect(() => {
    setDraft(current ? files[current] ?? "" : "");
  }, [current, files]);

  const dirty = current !== null && draft !== (files[current] ?? "");

  const save = async () => {
    if (!current) return;
    try {
      await api.savePrehistory(current, draft);
      setFiles({ ...files, [current]: draft });
    } catch (e) {
      notify(errMsg(e));
    }
  };

  const create = async () => {
    const name = newName.trim();
    if (!name) return;
    try {
      await api.savePrehistory(name, `# ${name}\n\n`);
      setFiles({ ...files, [name]: `# ${name}\n\n` });
      setCurrent(name);
      setNewName("");
    } catch (e) {
      notify(errMsg(e));
    }
  };

  const remove = async () => {
    if (!current || !window.confirm(`Delete prehistory file "${current}"?`)) return;
    await api.deletePrehistory(current);
    const { [current]: _, ...rest } = files;
    setFiles(rest);
    setCurrent(Object.keys(rest)[0] ?? null);
  };

  return (
    <div className="stack">
      <p className="hint">Your seed canon. Only you edit these files; every agent reads all of them. Write freely: open questions go in their own tab.</p>
      <div className="pills">
        {Object.keys(files).map((n) => (
          <button key={n} className={`pill${n === current ? " active" : ""}`} onClick={() => setCurrent(n)}>{n}</button>
        ))}
      </div>
      {current && (
        <>
          <textarea className="editor tall" value={draft} onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === "s") { e.preventDefault(); save(); } }} />
          <div className="row">
            <button className="primary" disabled={!dirty} onClick={save}>{dirty ? "Save" : "Saved"}</button>
            <button className="ghost danger" onClick={remove}>Delete file</button>
          </div>
        </>
      )}
      <div className="row">
        <input placeholder="new file, e.g. characters" value={newName} onChange={(e) => setNewName(e.target.value)}
               onKeyDown={(e) => e.key === "Enter" && create()} />
        <button onClick={create}>Add file</button>
      </div>
    </div>
  );
}

function Present({ version, runs, bump, notify }: Props) {
  const [entries, setEntries] = useState<LedgerEntry[]>([]);
  const [form, setForm] = useState({ entity: "", change: "", detail: "", run_id: "" });

  useEffect(() => {
    api.present().then((p) => setEntries(p.entries)).catch((e) => notify(errMsg(e)));
  }, [version, notify]);

  const grouped = useMemo(() => {
    const m = new Map<string, LedgerEntry[]>();
    for (const e of entries) {
      const k = e.entity || "General";
      m.set(k, [...(m.get(k) ?? []), e]);
    }
    return [...m.entries()];
  }, [entries]);

  const committed = runs.filter((r) => r.status === "committed");

  const add = async () => {
    if (!form.detail.trim()) return;
    try {
      await api.addPresent({ ...form, run_id: form.run_id || null });
      setForm({ entity: "", change: "", detail: "", run_id: form.run_id });
      bump();
    } catch (e) {
      notify(errMsg(e));
    }
  };

  return (
    <div className="stack">
      <p className="hint">What has changed since the story began, rebuilt from committed runs in order. Reverting a run removes its entries.</p>
      {!grouped.length && <p className="muted">Nothing yet. Commit a run or add a note.</p>}
      {grouped.map(([entity, list]) => (
        <div key={entity} className="entity">
          <h4>{entity}</h4>
          <ul>
            {list.map((e) => (
              <li key={e.id}>
                <span className={`tag ${e.source}`}>{e.run_id ?? "manual"} · {e.source}</span>
                {e.change && <b>{e.change}: </b>}{e.detail}
              </li>
            ))}
          </ul>
        </div>
      ))}
      <fieldset>
        <legend>Add a note</legend>
        <input placeholder="entity (character, faction, place)" value={form.entity}
               onChange={(e) => setForm({ ...form, entity: e.target.value })} />
        <input placeholder="change (e.g. allegiance, wounded)" value={form.change}
               onChange={(e) => setForm({ ...form, change: e.target.value })} />
        <textarea placeholder="what is now true" value={form.detail}
                  onChange={(e) => setForm({ ...form, detail: e.target.value })} />
        <select value={form.run_id} onChange={(e) => setForm({ ...form, run_id: e.target.value })}>
          <option value="">General (not tied to a run, never reverted)</option>
          {committed.map((r) => <option key={r.id} value={r.id}>Attach to {r.id}: {r.title}</option>)}
        </select>
        <button className="primary" onClick={add}>Add note</button>
      </fieldset>
    </div>
  );
}

function Questions({ version, bump, notify }: Props) {
  const [items, setItems] = useState<OpenQuestion[]>([]);
  const [filter, setFilter] = useState<"open" | "answered" | "all">("open");
  const [q, setQ] = useState({ question: "", about: "" });
  const [answering, setAnswering] = useState<Record<string, string>>({});

  useEffect(() => {
    api.questions().then(setItems).catch((e) => notify(errMsg(e)));
  }, [version, notify]);

  const shown = items.filter((i) => filter === "all" || i.status === filter);

  const run = (fn: () => Promise<unknown>) => fn().then(bump).catch((e) => notify(errMsg(e)));

  return (
    <div className="stack">
      <p className="hint">Things the universe has not settled yet. Agents see them and may propose answers or new questions at the ledger gate.</p>
      <div className="pills">
        {(["open", "answered", "all"] as const).map((f) => (
          <button key={f} className={`pill${filter === f ? " active" : ""}`} onClick={() => setFilter(f)}>
            {f} ({items.filter((i) => f === "all" || i.status === f).length})
          </button>
        ))}
      </div>
      {shown.map((i) => (
        <div key={i.id} className={`card q ${i.status}`}>
          <div className="card-head">
            {i.about && <span className="tag">{i.about}</span>}
            <span className={`tag ${i.created_by}`}>{i.source_run ? `from ${i.source_run}` : i.created_by}</span>
            <button className="ghost small danger" onClick={() => run(() => api.deleteQuestion(i.id))}>×</button>
          </div>
          <div className="q-text">{i.question}</div>
          {i.status === "answered" ? (
            <div className="answer">
              <span className="muted">{i.answered_by_run ? `answered in ${i.answered_by_run}` : "answered by you"}:</span> {i.answer}
              <button className="ghost small" onClick={() => run(() => api.updateQuestion(i.id, { status: "open", answer: "" }))}>reopen</button>
            </div>
          ) : (
            <div className="row">
              <input placeholder="answer it yourself" value={answering[i.id] ?? ""}
                     onChange={(e) => setAnswering({ ...answering, [i.id]: e.target.value })} />
              <button disabled={!answering[i.id]?.trim()}
                      onClick={() => run(() => api.updateQuestion(i.id, { answer: answering[i.id] }))}>Answer</button>
            </div>
          )}
        </div>
      ))}
      <fieldset>
        <legend>New question</legend>
        <textarea placeholder="e.g. Tiye is married to X. How did that happen?" value={q.question}
                  onChange={(e) => setQ({ ...q, question: e.target.value })} />
        <input placeholder="about (optional)" value={q.about} onChange={(e) => setQ({ ...q, about: e.target.value })} />
        <button className="primary" disabled={!q.question.trim()}
                onClick={() => run(async () => { await api.addQuestion(q.question, q.about); setQ({ question: "", about: "" }); })}>
          Add question
        </button>
      </fieldset>
    </div>
  );
}

function Events({ version, runs, bump, notify, onPlanArc, onOpenPlanner }: Props) {
  const [items, setItems] = useState<StoryEvent[]>([]);
  const [form, setForm] = useState({ title: "", description: "", scope: "arc", category: "world", parent_id: "",
                                     characters: "", target_run: "" });

  useEffect(() => {
    api.events().then(setItems).catch((e) => notify(errMsg(e)));
  }, [version, notify]);

  const run = (fn: () => Promise<unknown>) => fn().then(bump).catch((e) => notify(errMsg(e)));
  const children = (pid: string | null) =>
    items.filter((e) => (e.parent_id ?? null) === pid).sort((a, b) => (a.order || 0) - (b.order || 0));
  const chapters = runs.filter((r) => r.type === "chapter");

  const render = (ev: StoryEvent, depth: number): React.ReactNode => (
    <div key={ev.id} className={`card ev ${ev.status}`} style={{ marginLeft: depth * 14 }}>
      <div className="card-head">
        <span className="tag">{ev.scope}</span>
        <select className="small" value={ev.category} title="world or personal event"
                onChange={(e) => run(() => api.updateEvent(ev.id, { category: e.target.value as StoryEvent["category"] }))}>
          <option value="world">world</option>
          <option value="personal">personal</option>
        </select>
        {ev.created_by === "ai" && <span className="tag ai">from {ev.source_run}</span>}
        {ev.target_run && <span className="tag">→ {ev.target_run}</span>}
        <select className="small" value={ev.status}
                onChange={(e) => run(() => api.updateEvent(ev.id, { status: e.target.value as StoryEvent["status"] }))}>
          <option value="planned">planned</option>
          <option value="in_progress">in progress</option>
          <option value="resolved">resolved</option>
        </select>
        <button className="ghost small danger" onClick={() => run(() => api.deleteEvent(ev.id))}>×</button>
      </div>
      <div className="ev-title">{ev.title}</div>
      {ev.description && <div className="ev-desc">{ev.description}</div>}
      {!!ev.characters?.length && <div className="muted small-text">{ev.characters.join(", ")}</div>}
      {ev.progress?.map((p, i) => <div key={i} className="small-text">· {p.run_id}: {p.detail}</div>)}
      <div className="row">
        {ev.scope === "arc" && <button className="small" onClick={() => onPlanArc(ev)}>Plan arc with AI…</button>}
        <select className="small" value={ev.target_run}
                onChange={(e) => run(() => api.updateEvent(ev.id, { target_run: e.target.value }))}>
          <option value="">no target chapter</option>
          {chapters.map((c) => <option key={c.id} value={c.id}>target {c.id}</option>)}
        </select>
      </div>
      {children(ev.id).map((c) => render(c, depth + 1))}
    </div>
  );

  const add = () =>
    run(async () => {
      await api.addEvent({
        title: form.title, description: form.description, scope: form.scope as StoryEvent["scope"],
        category: form.category as StoryEvent["category"],
        parent_id: form.parent_id || null, target_run: form.target_run,
        characters: form.characters.split(",").map((s) => s.trim()).filter(Boolean),
      });
      setForm({ ...form, title: "", description: "", characters: "" });
    });

  const roots = items.filter((e) => !e.parent_id || !items.some((p) => p.id === e.parent_id));

  return (
    <div className="stack">
      <p className="hint">Where you want the story to go. Arcs span chapters; chapter events must happen in their target chapter. The Weaver steers toward both.</p>
      <button onClick={onOpenPlanner}>Open arc planner (character timelines)…</button>
      {roots.map((e) => render(e, 0))}
      <fieldset>
        <legend>New event</legend>
        <input placeholder="title, e.g. War between Egypt and Hatti" value={form.title}
               onChange={(e) => setForm({ ...form, title: e.target.value })} />
        <textarea placeholder="what should happen" value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })} />
        <div className="row">
          <select value={form.scope} onChange={(e) => setForm({ ...form, scope: e.target.value })}>
            <option value="arc">arc (multi-chapter)</option>
            <option value="chapter">chapter (single event)</option>
          </select>
          <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
            <option value="world">world event</option>
            <option value="personal">personal event</option>
          </select>
          <select value={form.parent_id} onChange={(e) => setForm({ ...form, parent_id: e.target.value })}>
            <option value="">no parent</option>
            {items.map((e) => <option key={e.id} value={e.id}>under: {e.title}</option>)}
          </select>
        </div>
        <input placeholder="characters, comma separated" value={form.characters}
               onChange={(e) => setForm({ ...form, characters: e.target.value })} />
        <select value={form.target_run} onChange={(e) => setForm({ ...form, target_run: e.target.value })}>
          <option value="">no target chapter</option>
          {chapters.map((c) => <option key={c.id} value={c.id}>target {c.id}: {c.title}</option>)}
        </select>
        <button className="primary" disabled={!form.title.trim()} onClick={add}>Add event</button>
      </fieldset>
    </div>
  );
}
