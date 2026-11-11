import { useEffect, useState } from "react";
import type { LedgerEntry } from "../types";

export interface LedgerGroup {
  id: string;
  /** Button and popup title, e.g. "Lore". */
  label: string;
  /** What one row is called, e.g. "question". */
  noun: string;
  kinds: LedgerEntry["kind"][];
}

/** The ledger popups, one per group. Rows of other kinds are not shown here. */
export const LEDGER_GROUPS: LedgerGroup[] = [
  { id: "lore", label: "Lore", noun: "lore entry", kinds: ["lore"] },
  { id: "questions", label: "Questions", noun: "question", kinds: ["new_question"] },
  { id: "hooks", label: "Hooks", noun: "hook", kinds: ["hook"] },
  { id: "answers", label: "Answers", noun: "answer", kinds: ["answer"] },
  { id: "events", label: "Events", noun: "event", kinds: ["event_update", "sub_event"] },
];

const KIND_LABELS: Record<LedgerEntry["kind"], string> = {
  lore: "lore",
  answer: "answer",
  new_question: "open question",
  hook: "hook (not canon)",
  event_update: "event progress",
  sub_event: "milestone",
};

const DETAIL_LABEL: Partial<Record<LedgerEntry["kind"], string>> = {
  lore: "What is now true",
  answer: "Answer",
  new_question: "Question",
  hook: "Hook",
  event_update: "What happened",
  sub_event: "Description",
};

const ENTITY_LABEL: Partial<Record<LedgerEntry["kind"], string>> = {
  lore: "Entity",
  sub_event: "Milestone title",
};

interface Props {
  group: LedgerGroup;
  /** The whole ledger; the popup shows only this group's rows and hands back the whole ledger on change. */
  entries: LedgerEntry[];
  editable: boolean;
  onChange: (next: LedgerEntry[]) => void;
  onClose: () => void;
}

/** One card per ledger row: read the full text, keep or drop it, and click ✎ to edit. */
export default function LedgerReview({ group, entries, editable, onChange, onClose }: Props) {
  const idxs = entries.map((e, i) => (group.kinds.includes(e.kind) ? i : -1)).filter((i) => i >= 0);
  const n = idxs.length;
  const [pos, setPos] = useState(0);
  const [editing, setEditing] = useState(false);
  const at = Math.min(pos, Math.max(n - 1, 0));
  const i = idxs[at];
  const e = i === undefined ? undefined : entries[i];
  const kept = (x: LedgerEntry) => x.accepted !== false;
  const answered = (x: LedgerEntry) => x.kind === "new_question" && !!x.answer?.trim();

  const go = (d: number) => { if (n) { setPos((at + d + n) % n); setEditing(false); } };
  const patch = (change: Partial<LedgerEntry>) => onChange(entries.map((x, j) => (j === i ? { ...x, ...change } : x)));

  const decide = (accepted: boolean) => {
    patch({ accepted });
    if (at < n - 1) { setPos(at + 1); setEditing(false); }
  };

  const add = () => {
    onChange([...entries, {
      kind: group.kinds[0], entity: "", change: "", detail: "", ref_id: "", characters: [], source: "user", accepted: true,
    }]);
    setPos(n);
    setEditing(true);
  };

  const remove = () => {
    onChange(entries.filter((_, j) => j !== i));
    setEditing(false);
  };

  const setAll = (accepted: boolean) =>
    onChange(entries.map((x) => (group.kinds.includes(x.kind) ? { ...x, accepted } : x)));

  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      const typing = ev.target instanceof HTMLElement && ev.target.closest("input, textarea, select");
      if (ev.key === "Escape") { if (typing) (ev.target as HTMLElement).blur(); else onClose(); return; }
      if (typing || ev.metaKey || ev.ctrlKey || ev.altKey) return;
      if (ev.key === "ArrowLeft") go(-1);
      if (ev.key === "ArrowRight") go(1);
      if (!editable || !e) return;
      const key = ev.key.toLowerCase();
      if (key === "k") decide(true);
      if (key === "d") decide(false);
      if (key === "e") { ev.preventDefault(); setEditing((x) => !x); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const keptCount = idxs.filter((j) => kept(entries[j])).length;
  const answeredCount = idxs.filter((j) => kept(entries[j]) && answered(entries[j])).length;
  const canEdit = editable && editing;

  return (
    <div className="modal-overlay" onMouseDown={(ev) => { if (ev.target === ev.currentTarget) onClose(); }}>
      <div className="modal review" role="dialog" aria-modal="true" aria-label={`Review ${group.label.toLowerCase()}`}>
        <div className="modal-head">
          <h2>{group.label}</h2>
          <span className="hint">
            {editable ? `${keptCount} of ${n} kept${group.id === "questions" ? `, ${answeredCount} answered` : ""} · K keep, D drop, E edit, ← → to move, Esc to close`
              : "read-only: the ledger is edited at the ledger gate"}
          </span>
          {editable && n > 0 && (
            <>
              <button className="small" onClick={() => setAll(true)}>Keep all</button>
              <button className="small" onClick={() => setAll(false)}>Drop all</button>
            </>
          )}
          {editable && <button className="small" onClick={add}>+ Add {group.noun}</button>}
          <button className="ghost" onClick={onClose} aria-label="Close">✕</button>
        </div>

        {!e ? (
          <div className="review-body empty-state">
            <p className="muted">No {group.noun}s in this run.{editable ? ` Use + Add ${group.noun} to write one.` : ""}</p>
          </div>
        ) : (
          <>
            <div className="review-nav">
              <button className="ghost" onClick={() => go(-1)} aria-label="Previous">←</button>
              <div className="review-dots">
                {idxs.map((j, k) => (
                  <button key={j} className={`dot ${!kept(entries[j]) ? "rejected" : answered(entries[j]) ? "answered" : "accepted"}${k === at ? " current" : ""}`}
                          title={`${k + 1}. ${entries[j].entity || entries[j].detail.slice(0, 60)}`}
                          onClick={() => { setPos(k); setEditing(false); }} />
                ))}
              </div>
              <span className="review-count">{at + 1} / {n}</span>
              <button className="ghost" onClick={() => go(1)} aria-label="Next">→</button>
            </div>

            <div className={`review-body${kept(e) ? "" : " rejected"}`}>
              <div className="review-title">
                <span className="tag">{KIND_LABELS[e.kind] ?? e.kind}</span>
                <span className={`tag ${e.source ?? "ai"}`}>{e.source ?? "ai"}{e.confidence ? ` · ${e.confidence}` : ""}</span>
                <span className={`decision-chip ${kept(e) ? "accepted" : "rejected"}`}>
                  {!kept(e) ? "Dropped" : answered(e) ? "Kept, answered" : "Kept"}
                </span>
                {editable && (
                  <button className={`ghost small pencil${editing ? " on" : ""}`} onClick={() => setEditing(!editing)}
                          title={editing ? "Stop editing" : "Edit this row"} aria-pressed={editing}>
                    {editing ? "✓ Done" : "✎ Edit"}
                  </button>
                )}
              </div>
              {!kept(e) && (
                <div className="rejected-banner">
                  Dropped. Commit will not write this {group.noun}.
                  {editable && <button className="small" onClick={() => patch({ accepted: true })}>Undo</button>}
                </div>
              )}

              {canEdit && group.kinds.length > 1 && (
                <label className="field">
                  <span>Kind</span>
                  <select value={e.kind} onChange={(ev) => patch({ kind: ev.target.value as LedgerEntry["kind"] })}>
                    {group.kinds.map((k) => <option key={k} value={k}>{KIND_LABELS[k]}</option>)}
                  </select>
                </label>
              )}

              <Field label={ENTITY_LABEL[e.kind] ?? "About"} value={e.entity} editing={canEdit}
                     onChange={(entity) => patch({ entity })} />
              {(e.kind === "lore" || e.kind === "event_update" || e.kind === "sub_event" || (canEdit && e.change)) && (
                <Field label={e.kind === "lore" ? "Change" : e.kind === "sub_event" ? "Order" : "Status"} value={e.change}
                       editing={canEdit} onChange={(change) => patch({ change })} />
              )}
              {(e.kind === "answer" || e.kind === "event_update") && (
                <Field label={e.kind === "answer" ? "Question id" : "Event id"} value={e.ref_id} editing={canEdit}
                       onChange={(ref_id) => patch({ ref_id })} />
              )}

              <div className="field">
                <span>{DETAIL_LABEL[e.kind] ?? "Detail"}</span>
                {canEdit
                  ? <textarea className="ledger-detail" value={e.detail} autoFocus onChange={(ev) => patch({ detail: ev.target.value })} />
                  : <div className="ledger-text">{e.detail || <span className="muted">(empty)</span>}</div>}
              </div>

              {e.kind === "new_question" && (editable || answered(e)) && (
                <label className="field">
                  <span>Your answer</span>
                  <textarea className="ledger-answer" value={e.answer ?? ""} readOnly={!editable}
                            placeholder="Leave blank to keep it open. An answer is committed with the question and becomes canon."
                            onChange={(ev) => patch({ answer: ev.target.value, accepted: true })} />
                </label>
              )}

              {(e.kind === "sub_event" || (e.characters?.length ?? 0) > 0) && (
                <div className="field">
                  <span>{e.kind === "sub_event" ? "Characters on whose timelines this lands" : "Characters"}</span>
                  {canEdit
                    ? <CharactersInput key={i} value={e.characters ?? []} onChange={(characters) => patch({ characters })} />
                    : <div className="chips">{(e.characters ?? []).length
                        ? (e.characters ?? []).map((c) => <span key={c} className="tag">{c}</span>)
                        : <span className="muted">none</span>}</div>}
                </div>
              )}
            </div>

            {editable && (
              <div className="review-foot">
                <div className="row decisions">
                  <button className={`decide accepted${kept(e) ? " on" : ""}`} onClick={() => decide(true)}>Keep</button>
                  <button className={`decide rejected${kept(e) ? "" : " on"}`} onClick={() => decide(false)}>Drop</button>
                  {editing && <button className="ghost small danger" onClick={remove}>Delete row</button>}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function Field({ label, value, editing, onChange }: {
  label: string; value: string; editing: boolean; onChange: (v: string) => void;
}) {
  if (!editing && !value) return null;
  return (
    <label className="field">
      <span>{label}</span>
      {editing ? <input value={value} onChange={(ev) => onChange(ev.target.value)} />
        : <div className="ledger-value">{value}</div>}
    </label>
  );
}

/** Comma-separated names; keeps the raw text while typing so commas and spaces are not swallowed. */
function CharactersInput({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const [text, setText] = useState(value.join(", "));
  return (
    <input placeholder="comma separated" value={text}
           onChange={(ev) => {
             setText(ev.target.value);
             onChange(ev.target.value.split(",").map((x) => x.trim()).filter(Boolean));
           }} />
  );
}
