import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { AppConfig, NewRunPrefill, RunMeta, RunState, RunType, StoryEvent } from "../types";
import { GATE_LABELS, RESEARCHER_LABELS, RUN_TYPE_LABELS, slug } from "../util";

interface Props {
  config: AppConfig | null;
  runs: RunMeta[];
  selected: string | null;
  onSelect: (id: string | null) => void;
  runState: RunState | null;
  act: (fn: () => Promise<unknown>, after?: (r: unknown) => void) => Promise<void>;
  notify: (m: string) => void;
  getEdits: () => Record<string, unknown>;
  prefill: NewRunPrefill | null;
  clearPrefill: () => void;
}

const DEFAULT_RESEARCHERS: Record<RunType, string[]> = {
  chapter: ["antiquarian", "psychologist"],
  research: ["antiquarian", "historian", "mythographer", "psychologist"],
  plan_arc: ["historian", "psychologist"],
  lore: ["antiquarian", "psychologist"],
};

export default function ControlDeck(p: Props) {
  const [creating, setCreating] = useState(false);
  useEffect(() => {
    if (p.prefill) setCreating(true);
  }, [p.prefill]);

  return (
    <>
      <div className="col-title">Control Deck</div>
      <div className="col-body stack">
        <RunPicker {...p} onNew={() => setCreating(true)} />
        {creating && (
          <NewRunForm {...p} onDone={(id) => {
            setCreating(false);
            p.clearPrefill();
            if (id) p.onSelect(id);
          }} />
        )}
        {p.runState && !creating && <RunControls {...p} />}
      </div>
    </>
  );
}

function RunPicker({ runs, selected, onSelect, onNew }: Props & { onNew: () => void }) {
  return (
    <div className="row">
      <select className="grow" value={selected ?? ""} onChange={(e) => onSelect(e.target.value || null)}>
        <option value="">Select a run…</option>
        {(["chapter", "research", "plan_arc", "lore"] as RunType[]).map((t) => {
          const list = runs.filter((r) => r.type === t);
          return list.length ? (
            <optgroup key={t} label={RUN_TYPE_LABELS[t]}>
              {list.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.id} · {r.title} [{r.status}{r.running ? ", running" : ""}]
                </option>
              ))}
            </optgroup>
          ) : null;
        })}
      </select>
      <button className="primary" onClick={onNew}>+ New run</button>
    </div>
  );
}

function NewRunForm({ config, runs, prefill, act, onDone }: Props & { onDone: (id: string | null) => void }) {
  const [type, setType] = useState<RunType>(prefill?.type ?? "chapter");
  const [title, setTitle] = useState(prefill?.title ?? "");
  const [id, setId] = useState("");
  const [idTouched, setIdTouched] = useState(false);
  const [pov, setPov] = useState("");
  const [brief, setBrief] = useState(prefill?.brief ?? "");
  const [researchers, setResearchers] = useState<string[]>(DEFAULT_RESEARCHERS[prefill?.type ?? "chapter"]);
  const [targetEvent, setTargetEvent] = useState(prefill?.target_event_id ?? "");
  const [events, setEvents] = useState<StoryEvent[]>([]);

  useEffect(() => {
    api.events().then(setEvents).catch(() => setEvents([]));
  }, []);

  useEffect(() => {
    if (idTouched) return;
    const n = runs.filter((r) => r.type === "chapter").length + 1;
    if (type === "chapter") setId(`ch${String(n).padStart(2, "0")}`);
    else setId(`${{ research: "r", plan_arc: "arc", lore: "lore" }[type]}-${slug(title) || "untitled"}`);
  }, [type, title, runs, idTouched]);

  const changeType = (t: RunType) => {
    setType(t);
    setResearchers(DEFAULT_RESEARCHERS[t]);
  };

  const submit = () =>
    act(() => api.createRun({ id, type, title, brief, pov: type === "chapter" ? pov : "",
                              researchers, target_event_id: type === "plan_arc" ? targetEvent : "" }),
        (meta) => onDone((meta as RunMeta).id));

  const briefHint = {
    chapter: "What should this chapter do? Who, where, what must happen, what you're unsure about.",
    research: "A question or a need, e.g. 'The Sherden should behave like a praetorian guard. How did those guards gain and abuse power?' or 'Give X a backstory.'",
    plan_arc: "Constraints for the arc: what must stay true, characters to use, roughly how many chapters.",
    lore: "What document do you want? e.g. 'Write Tiye's backstory: her family, how she entered the harem, what she owes and to whom.' or 'Profile the Sherden guard as a faction.'",
  }[type];

  return (
    <fieldset className="new-run">
      <legend>New run</legend>
      <div className="seg">
        {(["chapter", "research", "plan_arc", "lore"] as RunType[]).map((t) => (
          <button key={t} className={type === t ? "active" : ""} onClick={() => changeType(t)}>{RUN_TYPE_LABELS[t]}</button>
        ))}
      </div>
      <p className="hint">
        {type === "chapter" && "Research → outline → prose with critique loop → lore ledger → commit."}
        {type === "research" && "Research only, then propose lore changes and answers. No prose. Use it for lore questions and backstories."}
        {type === "plan_arc" && "Propose the chain of milestones leading to a major event. Approved milestones become sub-events."}
        {type === "lore" && "Research → a lore document (backstory, profile, proposal) → lore ledger → commit. Adopt the approved document into prehistory with one click."}
      </p>
      <input placeholder="title" value={title} onChange={(e) => setTitle(e.target.value)} />
      <input placeholder="run id" value={id} onChange={(e) => { setId(e.target.value); setIdTouched(true); }} />
      {type === "chapter" && <input placeholder="POV character" value={pov} onChange={(e) => setPov(e.target.value)} />}
      {type === "plan_arc" && (
        <select value={targetEvent} onChange={(e) => setTargetEvent(e.target.value)}>
          <option value="">Target event…</option>
          {events.filter((e) => e.scope === "arc").map((e) => <option key={e.id} value={e.id}>{e.title}</option>)}
        </select>
      )}
      <textarea className="brief" placeholder={briefHint} value={brief} onChange={(e) => setBrief(e.target.value)} />
      <div className="checks">
        <span className="muted">Researchers (run in parallel; none skips research):</span>
        {(config?.researchers ?? Object.keys(RESEARCHER_LABELS)).map((r) => (
          <label key={r}>
            <input type="checkbox" checked={researchers.includes(r)}
                   onChange={(e) => setResearchers(e.target.checked ? [...researchers, r] : researchers.filter((x) => x !== r))} />
            {RESEARCHER_LABELS[r] ?? r}
          </label>
        ))}
      </div>
      <div className="row">
        <button className="primary" disabled={!id || (type === "plan_arc" && !targetEvent)} onClick={submit}>Create</button>
        <button className="ghost" onClick={() => onDone(null)}>Cancel</button>
      </div>
    </fieldset>
  );
}

function RunControls({ runState, act, getEdits, config, onSelect }: Props) {
  const s = runState!;
  const id = s.meta.id;
  const gate = !s.running ? s.next[0] : undefined;
  const [notes, setNotes] = useState("");
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [s.log.length]);

  let status: { text: string; cls: string };
  if (s.running) status = { text: "Working…", cls: "running" };
  else if (s.error) status = { text: "Error", cls: "error" };
  else if (gate) status = { text: `Paused · ${GATE_LABELS[gate] ?? gate}`, cls: "gate" };
  else if (!s.started) status = { text: "Not started", cls: "idle" };
  else status = { text: s.meta.status === "reverted" ? "Reverted" : "Committed", cls: s.meta.status };

  const resumeLabel = gate === "human_gate_ledger" ? "Commit run" : gate === "human_gate_final" ? "Approve prose" : "Resume pipeline";

  return (
    <div className="stack">
      <div className="run-head">
        <div>
          <div className="run-title">{s.meta.title}</div>
          <div className="muted small-text">
            {RUN_TYPE_LABELS[s.meta.type]} · {id}{s.meta.pov ? ` · POV ${s.meta.pov}` : ""}
          </div>
        </div>
        <span className={`status-badge ${status.cls}`}>{status.text}</span>
      </div>
      {s.values.review_status && <div className="muted small-text">state: {s.values.review_status}
        {typeof s.values.revision_count === "number" && s.values.revision_count > 0 ? ` · revisions ${s.values.revision_count}/${config?.max_revisions ?? 3}` : ""}</div>}

      {s.error && <div className="error-box">{s.error}</div>}

      <div className="actions">
        {!s.started && <button className="primary big" onClick={() => act(() => api.start(id))}>Start</button>}
        {gate && (
          <button className="primary big" onClick={() => act(() => api.resume(id, getEdits()))}>{resumeLabel}</button>
        )}
        {s.error && !s.running && <button className="big" onClick={() => act(() => api.retry(id))}>Retry failed step</button>}
        {s.running && <button className="ghost" onClick={() => act(() => api.cancel(id))}>Cancel</button>}
      </div>

      {gate && (
        <fieldset>
          <legend>{gate === "human_gate_final" ? "Force rewrite" : "Regenerate this step"}</legend>
          <textarea placeholder={gate === "human_gate_final"
            ? "Direction for the rewrite, e.g. 'the Prince betrays his mother in scene 3, not later'"
            : "Optional direction, e.g. 'focus on the Sherden's pay and loyalty'"}
                    value={notes} onChange={(e) => setNotes(e.target.value)} />
          <button onClick={() => act(() => api.regenerate(id, notes), () => setNotes(""))}>
            {gate === "human_gate_final" ? "Force rewrite" : "Regenerate"}
          </button>
          <p className="hint">Discards unsaved edits in the sandbox for this step.</p>
        </fieldset>
      )}

      <div className="row">
        {s.meta.status === "committed" && (
          <button className="ghost danger" onClick={() => {
            if (window.confirm(`Revert ${id}? Its lore changes, answers, events and prose are removed from the present.`))
              act(() => api.revert(id), (r) => {
                const w = (r as { warnings: string[] }).warnings;
                if (w.length) window.alert("Later runs touched the same entities:\n\n" + w.join("\n"));
              });
          }}>Revert run</button>
        )}
        {s.meta.status === "reverted" && <button className="ghost" onClick={() => act(() => api.restore(id))}>Restore run</button>}
        {s.meta.status !== "committed" && (
          <button className="ghost danger" onClick={() => {
            if (window.confirm(`Delete ${id} and its checkpoint?`)) act(() => api.deleteRun(id), () => onSelect(null));
          }}>Delete run</button>
        )}
      </div>

      <div className="usage">
        <div className="row spread"><b>Usage</b><span>{s.cost_usd ? `$${s.cost_usd.toFixed(2)} equiv.` : "—"}</span></div>
        {s.usage.map((u, i) => (
          <div key={i} className="small-text row spread">
            <span>{u.node} <span className="muted">{u.model.replace("claude-", "")}</span></span>
            <span className="muted">{u.duration_ms ? `${Math.round(u.duration_ms / 1000)}s` : ""}{u.num_turns ? ` · ${u.num_turns}t` : ""}</span>
          </div>
        ))}
      </div>

      <div className="log" ref={logRef}>
        {s.log.map((l, i) => (
          <div key={i} className={`log-line ${l.kind}`}>
            <span className="muted">{new Date(l.t * 1000).toLocaleTimeString()}</span> {l.msg}
          </div>
        ))}
        {!s.log.length && <div className="muted">Log appears here while the run works.</div>}
      </div>
    </div>
  );
}
